from fastapi.testclient import TestClient

from app.main import DemoLimiter, app, runs
from app.schemas import (
    AssessmentMode,
    AssessmentReport,
    ChallengeAction,
    ChallengeDecision,
    CohortResult,
    ReleaseState,
    TrialRecord,
)

client = TestClient(app)


def test_public_pages_and_health_render() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200
    assert client.get("/").status_code == 200
    evaluation = client.get("/evaluation")
    assert evaluation.status_code == 200
    assert "7/7" in evaluation.text


def test_invalid_form_stops_before_external_calls() -> None:
    response = client.post(
        "/api/v1/assess",
        data={"nct_id": "not-an-id", "mode": "prospective"},
    )
    assert response.status_code == 422
    assert "Enter NCT followed by eight digits" in response.text


def test_oversized_body_is_rejected() -> None:
    response = client.post(
        "/api/v1/assess",
        data={"nct_id": "NCT01234567", "mode": "prospective", "padding": "x" * 4_096},
    )
    assert response.status_code == 413


def test_daily_live_limit_resets_on_utc_day_boundary() -> None:
    limiter = DemoLimiter(requests_per_minute=1, daily_live_limit=1)
    assert limiter.allow_live_run(0)
    assert not limiter.allow_live_run(1)
    assert limiter.allow_live_run(86_400)


def test_checked_report_page_renders() -> None:
    report = AssessmentReport(
        run_id="render-test",
        mode=AssessmentMode.PROSPECTIVE,
        trial=TrialRecord(
            nct_id="NCT01234567",
            title="Example trial",
            phase=["PHASE2"],
            conditions=["Example condition"],
            intervention_types=["DRUG"],
            status="RECRUITING",
            source_url="https://clinicaltrials.gov/study/NCT01234567",
        ),
        cohort=CohortResult(
            filters={"condition": "Example condition"},
            status_counts={"RECRUITING": 1},
            records_retrieved=1,
            pagination_complete=True,
        ),
        challenge=ChallengeDecision(
            action=ChallengeAction.APPROVE,
            summary="The bounded report is supported.",
        ),
        release_state=ReleaseState.FULL,
    )
    runs[report.run_id] = report
    response = client.get(f"/runs/{report.run_id}")
    assert response.status_code == 200
    assert "Example trial" in response.text
    assert "Approved for review" in response.text
