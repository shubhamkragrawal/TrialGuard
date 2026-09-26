"""FastAPI entrypoint for TrialGuard's public demonstration."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.config import Settings
from app.orchestration import AssessmentService
from app.registry import RegistryError
from app.schemas import AssessmentReport, AssessRequest
from eval.run_eval import run_all, summarize

settings = Settings.from_env()
app = FastAPI(
    title="TrialGuard",
    version="0.1.0",
    description="Evidence-grounded clinical-trial operations review",
    docs_url="/api/docs",
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=Path("app/static")), name="static")
templates = Jinja2Templates(directory=Path("app/templates"))


class DemoLimiter:
    """Small in-memory guard for a bounded public hackathon service."""

    def __init__(self, requests_per_minute: int, daily_live_limit: int) -> None:
        self.requests_per_minute = max(1, requests_per_minute)
        self.daily_live_limit = max(0, daily_live_limit)
        self._requests: Dict[str, Deque[float]] = defaultdict(deque)
        self.live_runs = 0
        self._live_day = ""

    def allow_request(self, client: str, now: float) -> bool:
        window = self._requests[client]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= self.requests_per_minute:
            return False
        window.append(now)
        return True

    def allow_live_run(self, now: float) -> bool:
        live_day = datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()
        if live_day != self._live_day:
            self._live_day = live_day
            self.live_runs = 0
        if self.live_runs >= self.daily_live_limit:
            return False
        self.live_runs += 1
        return True


limiter = DemoLimiter(
    settings.rate_limit_requests_per_minute,
    settings.daily_live_run_limit,
)
runs: dict[str, AssessmentReport] = {}
MAX_STORED_RUNS = 25
MAX_REQUEST_BODY_BYTES = 4_096
assessment_slots = asyncio.Semaphore(2)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "active_page": "home",
            "runtime": _runtime_context(),
            "demo_ids": [
                {
                    "nct_id": "NCT06860815",
                    "mode": "prospective",
                    "label": "Active Phase 2 example",
                    "description": "Public breast-cancer study",
                },
                {
                    "nct_id": "NCT06513364",
                    "mode": "retrospective",
                    "label": "Stopped Phase 2 example",
                    "description": "Registry-listed recruitment issue",
                },
            ],
        },
    )


@app.post("/api/v1/assess")
async def assess(request: Request):
    client = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc).timestamp()
    if not limiter.allow_request(client, now):
        raise HTTPException(status_code=429, detail="Public demo rate limit reached.")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Request body is too large.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length.") from exc
    if len(await request.body()) > MAX_REQUEST_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body is too large.")

    wants_json = "application/json" in request.headers.get("content-type", "")
    try:
        if wants_json:
            payload = await request.json()
        else:
            form = await request.form()
            payload = {"nct_id": form.get("nct_id"), "mode": form.get("mode")}
        assessment_request = AssessRequest.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        if wants_json:
            raise HTTPException(status_code=422, detail="Invalid NCT ID or mode.") from exc
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "active_page": "home",
                "runtime": _runtime_context(),
                "form_error": "Enter NCT followed by eight digits.",
                "form_values": payload,
            },
            status_code=422,
        )

    request_settings = settings
    if settings.bedrock_ready and not limiter.allow_live_run(now):
        request_settings = replace(settings, live_bedrock_enabled=False)

    try:
        async with assessment_slots:
            report = await asyncio.wait_for(
                AssessmentService(request_settings).assess(assessment_request),
                timeout=request_settings.report_timeout_seconds,
            )
    except asyncio.TimeoutError as exc:
        if wants_json:
            raise HTTPException(
                status_code=504,
                detail="Assessment timed out.",
            ) from exc
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "active_page": "home",
                "runtime": _runtime_context(),
                "error": {
                    "code": "Assessment timeout",
                    "title": "The checked review did not finish in time.",
                    "message": "Try the prepared example again in a moment.",
                },
            },
            status_code=504,
        )
    except RegistryError as exc:
        if wants_json:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "active_page": "home",
                "runtime": _runtime_context(),
                "error": {
                    "code": "Registry unavailable",
                    "title": "The public trial record could not be loaded.",
                    "message": str(exc),
                },
            },
            status_code=502,
        )

    _remember(report)
    if wants_json:
        return JSONResponse(report.model_dump(mode="json"))
    return RedirectResponse(f"/runs/{report.run_id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def report_page(request: Request, run_id: str) -> HTMLResponse:
    report = runs.get(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Checked report not found.")
    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "active_page": "runs",
            "runtime": _runtime_context(),
            "report": _report_context(report),
        },
    )


@app.get("/api/v1/runs/{run_id}")
async def report_api(run_id: str) -> dict[str, Any]:
    report = runs.get(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Checked report not found.")
    return report.model_dump(mode="json")


@app.get("/evaluation", response_class=HTMLResponse)
async def evaluation_page(request: Request) -> HTMLResponse:
    evaluation = _evaluation_context()
    return templates.TemplateResponse(
        request,
        "evaluation.html",
        {
            "active_page": "evaluation",
            "runtime": _runtime_context(),
            "evaluation": evaluation,
        },
    )


@app.get("/api/v1/runtime")
async def runtime_api() -> dict[str, Any]:
    return {
        "provider": "bedrock" if settings.bedrock_ready else "checked_offline_demo",
        "region": settings.aws_region,
        "model_id": settings.bedrock_model_id if settings.bedrock_ready else None,
        "guardrail_configured": bool(settings.bedrock_guardrail_id),
        "model_call_limit": settings.model_call_limit,
        "report_timeout_seconds": settings.report_timeout_seconds,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    return {
        "status": "ready",
        "registry_configured": settings.registry_base_url
        == "https://clinicaltrials.gov",
        "runtime": "bedrock" if settings.bedrock_ready else "offline",
    }


def _remember(report: AssessmentReport) -> None:
    runs[report.run_id] = report
    while len(runs) > MAX_STORED_RUNS:
        runs.pop(next(iter(runs)))


def _runtime_context() -> dict[str, str]:
    if settings.bedrock_ready:
        return {"status": "live", "label": "Bedrock live"}
    return {"status": "offline", "label": "Checked demo mode"}


def _report_context(report: AssessmentReport) -> dict[str, Any]:
    context = report.model_dump(mode="json")
    context["model_call_count"] = report.usage.model_calls
    context["check_summary"] = {
        "passed": sum(check.status.value == "passed" for check in report.checks),
        "total": len(report.checks),
    }
    context["is_cached"] = report.trial.cache_hit
    return context


def _evaluation_context() -> dict[str, Any]:
    summary = summarize(run_all())
    cases = []
    for result in summary["results"]:
        cases.append(
            {
                "name": result["title"],
                "fixture_type": "Synthetic offline fixture",
                "boundary": "Checks one documented release behavior.",
                "expected": result["expected_release"].title(),
                "status": "passed" if result["matched"] else "failed",
                "notes": ", ".join(result["observed_failed_checks"]) or "No failed checks",
            }
        )
    return {
        "status": "complete",
        "passed": summary["matched"],
        "total": summary["total"],
        "pass_percentage": round(summary["matched"] / summary["total"] * 100),
        "executed_at_display": "Current application build",
        "metrics": [
            {
                "label": "Expected behaviors matched",
                "value": f"{summary['matched']}/{summary['total']}",
                "unit": "",
                "note": "Synthetic offline release-gate fixtures",
            }
        ],
        "cases": cases,
        "known_limitations": [
            "These fixtures test software behavior, not clinical performance.",
            "Semantic support still requires manual review of real reports.",
            "Live Bedrock latency and cost depend on the enabled model and traffic.",
        ],
    }
