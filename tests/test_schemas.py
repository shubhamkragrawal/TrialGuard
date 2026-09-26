from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import AssessRequest, ChatRequest, CohortResult, TrialRecord


def test_assess_request_normalizes_nct_id() -> None:
    request = AssessRequest(nct_id=" nct01234567 ")
    assert request.nct_id == "NCT01234567"


@pytest.mark.parametrize(
    "value",
    ["", "NCT123", "https://clinicaltrials.gov/study/NCT01234567", "NCT0123456A"],
)
def test_assess_request_rejects_non_ids(value: str) -> None:
    with pytest.raises(ValidationError):
        AssessRequest(nct_id=value)


def test_chat_request_is_trimmed_and_bounded() -> None:
    assert ChatRequest(message="  explain the evidence  ").message == (
        "explain the evidence"
    )
    with pytest.raises(ValidationError):
        ChatRequest(message=" ")
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 501)


def test_incomplete_cohort_cannot_publish_rate() -> None:
    with pytest.raises(ValidationError):
        CohortResult(
            filters={"condition": "breast cancer"},
            status_counts={"COMPLETED": 2, "TERMINATED": 1},
            records_retrieved=3,
            pagination_complete=False,
            denominator=3,
            resolved_stop_rate=1 / 3,
        )


def test_trial_record_rejects_contact_fields() -> None:
    record = TrialRecord(
        nct_id="NCT01234567",
        title="Example study",
        phase=["PHASE2"],
        conditions=["Example condition"],
        intervention_types=["DRUG"],
        status="RECRUITING",
        source_url="https://clinicaltrials.gov/study/NCT01234567",
        retrieved_at=datetime.now(timezone.utc),
    )
    payload = record.model_dump()
    assert "contacts" not in payload
    assert "email" not in payload
