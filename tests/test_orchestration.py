from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.orchestration import AssessmentService
from app.schemas import AssessRequest, ReleaseState

FIXTURES = Path(__file__).parent / "fixtures" / "registry"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_offline_checked_assessment_runs_all_three_roles() -> None:
    target = _fixture("target.json")
    first_page = _fixture("cohort_page_1.json")
    second_page = _fixture("cohort_page_2.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/NCT00000001"):
            return httpx.Response(200, json=target)
        token = request.url.params.get("pageToken")
        return httpx.Response(200, json=second_page if token else first_page)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://clinicaltrials.gov",
    ) as http_client:
        service = AssessmentService(
            Settings(),
            http_client=http_client,
            cohort_limit=10,
        )
        report = await service.assess(AssessRequest(nct_id="NCT00000001"))

    assert report.release_state == ReleaseState.FULL
    assert report.trial.nct_id == "NCT00000001"
    assert len(report.precedents) == 2
    assert len(report.questions) == 2
    assert report.usage.model_calls == 3
    assert [event.stage for event in report.trace] == [
        "registry_retrieval",
        "evidence_agent",
        "coordinator_agent",
        "challenge_agent",
        "deterministic_release_gate",
    ]
    assert all(check.status.value != "failed" for check in report.checks)
