from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


class _SchemaModel:
    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)

    def model_dump(self) -> dict[str, Any]:
        return dict(self.__dict__)


try:
    import app.schemas  # noqa: F401
except ModuleNotFoundError:
    schema_stub = ModuleType("app.schemas")
    for model_name in ("TrialRecord", "EvidenceItem", "CohortResult", "NumericFact"):
        setattr(schema_stub, model_name, type(model_name, (_SchemaModel,), {}))
    sys.modules["app.schemas"] = schema_stub


from app.registry.cohort import (  # noqa: E402
    build_cohort,
    cohort_numeric_facts,
    derive_cohort_filters,
)
from app.registry.normalize import normalize_study  # noqa: E402
from app.registry.rank import rank_precedents, similarity_features  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "registry"
OBSERVED_AT = datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _records() -> tuple[Any, list[Any]]:
    target = normalize_study(_fixture("target.json"), retrieved_at=OBSERVED_AT)
    studies = (
        _fixture("cohort_page_1.json")["studies"]
        + _fixture("cohort_page_2.json")["studies"]
    )
    records = [
        normalize_study(study, retrieved_at=OBSERVED_AT) for study in studies
    ]
    return target, records


def test_complete_cohort_has_correct_counts_and_rate() -> None:
    target, records = _records()
    cohort = build_cohort(
        records,
        filters=derive_cohort_filters(target),
        pagination_complete=True,
        records_retrieved=6,
        retrieved_at=OBSERVED_AT,
    )
    assert cohort.status_counts == {
        "COMPLETED": 2,
        "RECRUITING": 1,
        "SUSPENDED": 1,
        "TERMINATED": 1,
        "WITHDRAWN": 1,
    }
    assert cohort.status_counts["TERMINATED"] + cohort.status_counts["WITHDRAWN"] == 2
    assert cohort.denominator == 4
    assert cohort.resolved_stop_rate == 0.5
    assert cohort.pagination_complete is True
    assert cohort.records_retrieved == 6
    assert any(
        fact.fact_id == "cohort.resolved_stop_rate"
        and fact.numerator == 2
        and fact.denominator == 4
        for fact in cohort_numeric_facts(cohort)
    )


def test_incomplete_cohort_omits_stop_rate() -> None:
    target, records = _records()
    cohort = build_cohort(
        records[:3],
        filters=derive_cohort_filters(target),
        pagination_complete=False,
        records_retrieved=3,
        retrieved_at=OBSERVED_AT,
    )
    assert cohort.resolved_stop_rate is None
    assert all(
        fact.fact_id != "cohort.resolved_stop_rate"
        for fact in cohort_numeric_facts(cohort)
    )
    assert any("incomplete" in limitation.casefold() for limitation in cohort.limitations)


def test_cohort_filters_exclude_wrong_condition_or_intervention_type() -> None:
    target, records = _records()
    wrong = records[0]
    wrong.conditions = ["Melanoma"]
    wrong.intervention_types = ["DEVICE"]
    cohort = build_cohort(
        records,
        filters=derive_cohort_filters(target),
        pagination_complete=True,
        retrieved_at=OBSERVED_AT,
    )
    assert cohort.records_retrieved == 5
    assert cohort.status_counts.get("TERMINATED", 0) == 0


def test_precedent_ranking_is_deterministic_and_uses_stated_reasons() -> None:
    target, records = _records()
    evidence = rank_precedents(target, reversed(records), limit=5)
    assert [item.nct_id for item in evidence] == [
        "NCT00000002",
        "NCT00000004",
    ]
    assert evidence[0].source_passage == "Enrollment was slower than planned."
    assert evidence[0].field_path == "protocolSection.statusModule.whyStopped"
    assert evidence[0].source_url.endswith("/NCT00000002")
    assert (
        evidence[0].relevance_features["score"]
        > evidence[1].relevance_features["score"]
    )
    assert similarity_features(target, records[0])["score"] == 1.0
