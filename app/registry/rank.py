"""Deterministic ranking of sourced stopped-trial precedents."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ._schema import (
    construct_schema,
    normalized_set,
    read_field,
    string_list,
)
from .cohort import STOPPED_STATUSES
from .normalize import STOP_REASON_FIELD


def rank_precedents(
    target: Any,
    candidates: Iterable[Any],
    *,
    limit: int = 5,
) -> list[Any]:
    """Rank stopped trials by inspectable features and stable tie-breaking."""

    if limit < 0:
        raise ValueError("limit must be non-negative")

    target_id = str(read_field(target, "nct_id", default=""))
    ranked: list[tuple[float, str, Any]] = []
    for candidate in candidates:
        nct_id = str(read_field(candidate, "nct_id", default=""))
        status = str(
            read_field(candidate, "status", "overall_status", default="")
        ).upper()
        stop_reason = read_field(candidate, "stop_reason", "why_stopped")
        if (
            not nct_id
            or nct_id == target_id
            or status not in STOPPED_STATUSES
            or not isinstance(stop_reason, str)
            or not stop_reason.strip()
        ):
            continue

        features = similarity_features(target, candidate)
        score = float(features["score"])
        source_url = str(
            read_field(candidate, "source_url", "registry_url", default="")
        )
        retrieved_at = read_field(
            candidate, "retrieved_at", "retrieval_time", default=None
        )
        evidence = construct_schema(
            "EvidenceItem",
            {
                "evidence_id": f"registry:{nct_id}:why_stopped",
                "nct_id": nct_id,
                "title": read_field(candidate, "title", default=None),
                "phase": list(string_list(candidate, "phase", "phases")),
                "conditions": list(string_list(candidate, "conditions")),
                "field_path": read_field(
                    candidate,
                    "stop_reason_field",
                    "source_field",
                    default=STOP_REASON_FIELD,
                )
                or STOP_REASON_FIELD,
                "source_passage": stop_reason.strip(),
                "stop_reason": stop_reason.strip(),
                "source_url": source_url,
                "relevance_features": features,
                "similarity_score": score,
                "relevance_summary": _relevance_summary(features),
                "retrieved_at": retrieved_at,
            },
        )
        ranked.append((score, nct_id, evidence))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [evidence for _, _, evidence in ranked[:limit]]


def similarity_features(target: Any, candidate: Any) -> dict[str, float]:
    """Return weighted, deterministic features used for ranking."""

    phase_score = _overlap(
        string_list(target, "phases", "phase"),
        string_list(candidate, "phases", "phase"),
    )
    condition_score = _overlap(
        string_list(target, "conditions"),
        string_list(candidate, "conditions"),
    )
    intervention_score = _overlap(
        string_list(target, "intervention_types"),
        string_list(candidate, "intervention_types"),
    )

    target_study_type = str(read_field(target, "study_type", default="")).casefold()
    candidate_study_type = str(
        read_field(candidate, "study_type", default="")
    ).casefold()
    study_type_match = float(
        bool(target_study_type)
        and bool(candidate_study_type)
        and target_study_type == candidate_study_type
    )
    design_score = _design_similarity(
        read_field(target, "design", default={}),
        read_field(candidate, "design", default={}),
    )
    score = (
        0.35 * phase_score
        + 0.30 * condition_score
        + 0.20 * intervention_score
        + 0.10 * study_type_match
        + 0.05 * design_score
    )
    return {
        "score": round(score, 6),
        "phase_overlap": round(phase_score, 6),
        "condition_overlap": round(condition_score, 6),
        "intervention_type_overlap": round(intervention_score, 6),
        "study_type_match": study_type_match,
        "design_match": round(design_score, 6),
    }


def _overlap(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = normalized_set(left)
    right_set = normalized_set(right)
    union = left_set | right_set
    intersection = left_set & right_set
    score = len(intersection) / len(union) if union else 0.0
    return score


def _design_similarity(left: Any, right: Any) -> float:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return 0.0
    keys = ("allocation", "intervention_model", "primary_purpose", "masking")
    comparable = 0
    matches = 0
    for key in keys:
        left_value = str(left.get(key, "")).casefold()
        right_value = str(right.get(key, "")).casefold()
        if left_value and right_value:
            comparable += 1
            matches += int(left_value == right_value)
    return matches / comparable if comparable else 0.0


def _relevance_summary(features: Mapping[str, float]) -> str:
    matches = [
        label
        for label, key in (
            ("phase", "phase_overlap"),
            ("condition", "condition_overlap"),
            ("intervention type", "intervention_type_overlap"),
            ("study type", "study_type_match"),
        )
        if features.get(key, 0) > 0
    ]
    if not matches:
        return "Included from the bounded stopped-study cohort."
    return "Matched on " + ", ".join(matches) + "."
