"""FastAPI entrypoint for TrialGuard's public demonstration."""

from __future__ import annotations

import asyncio
import uuid
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

from app.chat import ChatHistoryTurn, ChatService
from app.config import Settings
from app.observability import (
    CloudWatchLogsPublisher,
    CloudWatchMetricsPublisher,
    build_operational_event,
    emit_json_event,
)
from app.orchestration import AssessmentService
from app.registry import RegistryError
from app.schemas import (
    AssessmentReport,
    AssessRequest,
    ChatRequest,
    TraceEvent,
    UsageSummary,
)
from eval.run_eval import run_all, summarize

settings = Settings.from_env()
metrics_publisher = CloudWatchMetricsPublisher.from_boto3(
    enabled=settings.cloudwatch_metrics_enabled,
    region_name=settings.aws_region,
)
logs_publisher = CloudWatchLogsPublisher.from_boto3(
    enabled=settings.cloudwatch_logs_enabled,
    region_name=settings.aws_region,
)
app = FastAPI(
    title="TrialGuard",
    version="0.1.0",
    description="Evidence-grounded clinical-trial operations review",
    docs_url="/api/docs",
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=Path("app/static")), name="static")
templates = Jinja2Templates(directory=Path("app/templates"))
DEMO_REPORTS_DIR = Path("app/demo_reports")


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
chat_history: dict[str, list[ChatHistoryTurn]] = {}
chat_locks: dict[str, asyncio.Lock] = {}
MAX_STORED_RUNS = 25
MAX_CHAT_TURNS = 5
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
        fallback_report = (
            _checked_demo_report(assessment_request)
            if not settings.bedrock_ready
            else None
        )
        if fallback_report is not None:
            _remember(fallback_report)
            _publish_report_event(fallback_report)
            if wants_json:
                return JSONResponse(fallback_report.model_dump(mode="json"))
            return RedirectResponse(
                f"/runs/{fallback_report.run_id}",
                status_code=303,
            )
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
    _publish_report_event(report)
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


@app.post("/api/v1/runs/{run_id}/chat")
async def report_chat(request: Request, run_id: str) -> dict[str, Any]:
    report = runs.get(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Checked report not found.")

    lock = chat_locks.setdefault(run_id, asyncio.Lock())
    async with lock:
        history = chat_history.setdefault(run_id, [])
        if len(history) >= MAX_CHAT_TURNS:
            raise HTTPException(
                status_code=429,
                detail="Chat turn limit reached for this report.",
            )

        client = request.client.host if request.client else "unknown"
        now = datetime.now(timezone.utc).timestamp()
        if not limiter.allow_request(client, now):
            raise HTTPException(status_code=429, detail="Public demo rate limit reached.")

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Request body is too large.",
                    )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid Content-Length.",
                ) from exc
        body = await request.body()
        if len(body) > MAX_REQUEST_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body is too large.")

        try:
            payload = await request.json()
            chat_request = ChatRequest.model_validate(payload)
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail="Message must contain between 1 and 500 characters.",
            ) from exc

        request_settings = settings
        if settings.bedrock_ready and not limiter.allow_live_run(now):
            request_settings = replace(settings, live_bedrock_enabled=False)

        response = await asyncio.to_thread(
            ChatService(request_settings).answer,
            report=report,
            request=chat_request,
            turn=len(history) + 1,
            history=tuple(history),
        )
        history.append(
            ChatHistoryTurn(
                message=chat_request.message,
                answer=response.answer,
                evidence_ids=tuple(response.evidence_ids),
                numeric_fact_ids=tuple(response.numeric_fact_ids),
                disposition=response.disposition,
            )
        )
        _publish_chat_event(response)
        return response.model_dump(mode="json")


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
        forgotten_run_id = next(iter(runs))
        runs.pop(forgotten_run_id)
        chat_history.pop(forgotten_run_id, None)
        chat_locks.pop(forgotten_run_id, None)


def _checked_demo_report(request: AssessRequest) -> AssessmentReport | None:
    """Load a reviewed public-data replay when a demo host cannot reach the registry."""

    path = DEMO_REPORTS_DIR / f"{request.nct_id}.json"
    if not path.is_file():
        return None
    try:
        frozen = AssessmentReport.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError):
        return None

    replay_limitation = (
        "Registry retrieval was unavailable on this host; this is a reviewed "
        "replay of public registry data, not a new registry or model run."
    )
    return frozen.model_copy(
        update={
            "run_id": uuid.uuid4().hex[:12],
            "trial": frozen.trial.model_copy(update={"cache_hit": True}),
            "trace": [
                TraceEvent(
                    stage="checked_demo_replay",
                    status="passed",
                    cache_hit=True,
                    evidence_ids=[
                        item.evidence_id for item in frozen.precedents
                    ],
                    message=(
                        "Reviewed public-data replay used because registry "
                        "retrieval was unavailable."
                    ),
                )
            ],
            "usage": UsageSummary(
                pricing_basis="Reviewed checked-demo replay; no model call."
            ),
            "limitations": [
                *frozen.limitations,
                replay_limitation,
            ],
            "created_at": datetime.now(timezone.utc),
        }
    )


def _publish_report_event(report: AssessmentReport) -> None:
    event = build_operational_event(
        run_id=report.run_id,
        stage="assessment",
        status=report.release_state.value,
        duration_ms=sum(item.duration_ms for item in report.trace),
        release_state=report.release_state.value,
        model_calls=report.usage.model_calls,
        input_tokens=report.usage.input_tokens,
        output_tokens=report.usage.output_tokens,
        estimated_cost_usd=report.usage.estimated_cost_usd,
    )
    emit_json_event(event)
    metrics_publisher.publish(event)
    logs_publisher.publish(event)


def _publish_chat_event(response: Any) -> None:
    event = build_operational_event(
        run_id=response.run_id,
        stage="report_chat",
        status=response.disposition.value,
        duration_ms=response.trace.duration_ms,
        model_calls=response.usage.model_calls,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        estimated_cost_usd=response.usage.estimated_cost_usd,
    )
    emit_json_event(event)
    metrics_publisher.publish(event)
    logs_publisher.publish(event)


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
