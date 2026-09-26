"""Deterministic cohort filtering, counts, and resolved-study statistics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from ._schema import construct_schema, normalized_set, read_field, string_list
from .client import ClinicalTrialsClient, RegistrySearchResult
from .normalize import normalize_study

STOPPED_STATUSES = frozenset({"TERMINATED", "WITHDRAWN"})
RESOLVED_STATUSES = frozenset({"TERMINATED", "WITHDRAWN", "COMPLETED"})
UNRESOLVED_STATUSES = frozenset(
    {
        "ACTIVE_NOT_RECRUITING",
        "APPROVED_FOR_MARKETING",
        "AVAILABLE",
        "ENROLLING_BY_INVITATION",
        "NO_LONGER_AVAILABLE",
        "NOT_YET_RECRUITING",
        "RECRUITING",
        "SUSPENDED",
        "TEMPORARILY_NOT_AVAILABLE",
        "UNKNOWN",
        "WITHHELD",
    }
)


@dataclass(frozen=True)
class CohortFilters:
    conditions: tuple[str, ...]
    phases: tuple[str, ...]
    intervention_types: tuple[str, ...]
    study_type: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "conditions": list(self.conditions),
            "phases": list(self.phases),
            "intervention_types": list(self.intervention_types),
            "study_type": self.study_type,
        }


@dataclass(frozen=True)
class RetrievedCohort:
    cohort: Any
    records: tuple[Any, ...]
    numeric_facts: tuple[Any, ...]
    search: RegistrySearchResult


def derive_cohort_filters(target: Any) -> CohortFilters:
    return CohortFilters(
        conditions=string_list(target, "conditions"),
        phases=string_list(target, "phases", "phase"),
        intervention_types=string_list(target, "intervention_types"),
        study_type=_optional_upper(read_field(target, "study_type")),
    )


def matches_cohort(record: Any, filters: CohortFilters) -> bool:
    """Apply all available target dimensions using transparent exact overlap."""

    dimensions = (
        (filters.conditions, string_list(record, "conditions")),
        (filters.phases, string_list(record, "phases", "phase")),
        (
            filters.intervention_types,
            string_list(record, "intervention_types"),
        ),
    )
    for expected, observed in dimensions:
        if expected and not (normalized_set(expected) & normalized_set(observed)):
            return False

    observed_study_type = _optional_upper(read_field(record, "study_type"))
    return not (
        filters.study_type
        and observed_study_type
        and observed_study_type != filters.study_type
    )


def build_cohort(
    records: Iterable[Any],
    *,
    filters: CohortFilters,
    pagination_complete: bool,
    records_retrieved: int | None = None,
    retrieved_at: datetime | None = None,
) -> Any:
    """Build a shared ``CohortResult`` using deterministic-only calculations."""

    matched = tuple(record for record in records if matches_cohort(record, filters))
    counts = Counter(
        str(read_field(record, "status", "overall_status", default="UNKNOWN")).upper()
        for record in matched
    )
    status_counts = dict(sorted(counts.items()))
    stopped_count = sum(counts[status] for status in STOPPED_STATUSES)
    denominator = sum(counts[status] for status in RESOLVED_STATUSES)
    stop_rate = (
        stopped_count / denominator
        if pagination_complete and denominator > 0
        else None
    )
    source_count = records_retrieved if records_retrieved is not None else len(matched)
    limitations = [
        "Registry statuses are descriptive and do not establish efficacy or causation.",
        "Resolved-only rates can favor outcomes that resolve sooner.",
    ]
    if not pagination_complete:
        limitations.append(
            "Cohort retrieval was incomplete; the resolved-study stop rate is omitted."
        )
    elif denominator == 0:
        limitations.append(
            "No completed, terminated, or withdrawn studies were available for a rate."
        )

    return construct_schema(
        "CohortResult",
        {
            "filters": filters.as_dict(),
            "status_counts": status_counts,
            "records_retrieved": source_count,
            "pagination_complete": pagination_complete,
            "resolved_denominator": denominator,
            "resolved_stop_rate": stop_rate,
            "limitations": tuple(limitations),
        },
    )


def cohort_numeric_facts(cohort: Any) -> list[Any]:
    """Create exact numeric facts from an already-computed cohort result."""

    status_counts = read_field(cohort, "status_counts", default={})
    if not isinstance(status_counts, Mapping):
        status_counts = {}
    stopped_count = sum(
        int(status_counts.get(status, 0)) for status in STOPPED_STATUSES
    )
    denominator = sum(
        int(status_counts.get(status, 0)) for status in RESOLVED_STATUSES
    )
    records_matched = sum(int(count) for count in status_counts.values())
    stop_rate = read_field(cohort, "resolved_stop_rate", "stop_rate")

    numeric_facts = [
        construct_schema(
            "NumericFact",
            {
                "fact_id": "cohort.records_matched",
                "label": "Matched cohort records",
                "value": records_matched,
                "unit": "studies",
                "numerator": None,
                "denominator": None,
                "derivation": "Count after deterministic cohort filters",
            },
        ),
        construct_schema(
            "NumericFact",
            {
                "fact_id": "cohort.resolved_stopped_count",
                "label": "Terminated or withdrawn studies",
                "value": stopped_count,
                "unit": "studies",
                "numerator": None,
                "denominator": None,
                "derivation": "TERMINATED + WITHDRAWN",
            },
        ),
        construct_schema(
            "NumericFact",
            {
                "fact_id": "cohort.resolved_denominator",
                "label": "Resolved-study denominator",
                "value": denominator,
                "unit": "studies",
                "numerator": None,
                "denominator": None,
                "derivation": "TERMINATED + WITHDRAWN + COMPLETED",
            },
        ),
    ]
    if stop_rate is not None:
        numeric_facts.append(
            construct_schema(
                "NumericFact",
                {
                    "fact_id": "cohort.resolved_stop_rate",
                    "label": "Resolved-study stop rate",
                    "value": stop_rate,
                    "unit": "proportion",
                    "numerator": stopped_count,
                    "denominator": denominator,
                    "derivation": (
                        "(TERMINATED + WITHDRAWN) / "
                        "(TERMINATED + WITHDRAWN + COMPLETED)"
                    ),
                },
            )
        )

    return numeric_facts


async def retrieve_cohort(
    client: ClinicalTrialsClient,
    target: Any,
    *,
    max_records: int | None = None,
) -> RetrievedCohort:
    """Fetch, normalize, filter, and calculate a target's bounded cohort."""

    filters = derive_cohort_filters(target)
    if not filters.conditions:
        raise ValueError("target must have at least one condition")

    search = await client.search_studies(
        condition=filters.conditions[0],
        max_records=max_records,
    )
    normalized = tuple(
        normalize_study(study, retrieved_at=search.retrieved_at)
        for study in search.studies
    )
    matched = tuple(record for record in normalized if matches_cohort(record, filters))
    cohort = build_cohort(
        matched,
        filters=filters,
        pagination_complete=search.pagination_complete,
        records_retrieved=len(matched),
        retrieved_at=search.retrieved_at,
    )
    return RetrievedCohort(
        cohort=cohort,
        records=matched,
        numeric_facts=tuple(cohort_numeric_facts(cohort)),
        search=search,
    )


def _optional_upper(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None
