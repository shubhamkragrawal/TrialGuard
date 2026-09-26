"""Allowlisted normalization for ClinicalTrials.gov API v2 studies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from ._schema import construct_schema
from .client import validate_nct_id

REGISTRY_URL_TEMPLATE = "https://clinicaltrials.gov/study/{nct_id}"
STOP_REASON_FIELD = "protocolSection.statusModule.whyStopped"


def normalize_study(
    payload: Mapping[str, Any],
    *,
    retrieved_at: datetime | None = None,
) -> Any:
    """Return an allowlisted ``TrialRecord`` from an API v2 study payload.

    Contact, investigator, location, responsible-party, and arbitrary registry
    sections are intentionally never traversed or copied.
    """

    protocol = _mapping(payload.get("protocolSection", payload))
    identification = _mapping(protocol.get("identificationModule"))
    status_module = _mapping(protocol.get("statusModule"))
    design_module = _mapping(protocol.get("designModule"))
    conditions_module = _mapping(protocol.get("conditionsModule"))
    interventions_module = _mapping(protocol.get("armsInterventionsModule"))

    nct_id = validate_nct_id(_text(identification.get("nctId")))
    title = _text(
        identification.get("briefTitle") or identification.get("officialTitle")
    )
    phases = _unique_strings(design_module.get("phases"))
    conditions = _unique_strings(conditions_module.get("conditions"))
    interventions = interventions_module.get("interventions")
    if not isinstance(interventions, list):
        interventions = []
    intervention_types = _unique_strings(
        _mapping(intervention).get("type") for intervention in interventions
    )

    status = _text(status_module.get("overallStatus")).upper()
    stop_reason = _optional_text(status_module.get("whyStopped"))
    study_type = _text(design_module.get("studyType")).upper()
    design_info = _mapping(design_module.get("designInfo"))
    masking_info = _mapping(design_info.get("maskingInfo"))
    enrollment_info = _mapping(design_module.get("enrollmentInfo"))

    design = {
        "allocation": _optional_text(design_info.get("allocation")),
        "intervention_model": _optional_text(design_info.get("interventionModel")),
        "primary_purpose": _optional_text(design_info.get("primaryPurpose")),
        "masking": _optional_text(masking_info.get("masking")),
        "enrollment_count": _number(enrollment_info.get("count")),
        "enrollment_type": _optional_text(enrollment_info.get("type")),
        "start_date": _date_value(status_module.get("startDateStruct")),
        "completion_date": _date_value(status_module.get("completionDateStruct")),
    }
    design = {key: value for key, value in design.items() if value is not None}

    missing_fields: list[str] = []
    for field_name, value in (
        ("title", title),
        ("phases", phases),
        ("conditions", conditions),
        ("intervention_types", intervention_types),
        ("status", status),
        ("study_type", study_type),
    ):
        if not value:
            missing_fields.append(field_name)
    if status in {"TERMINATED", "WITHDRAWN"} and not stop_reason:
        missing_fields.append("stop_reason")

    observed_at = _aware_utc(retrieved_at or datetime.now(timezone.utc))
    return construct_schema(
        "TrialRecord",
        {
            "nct_id": nct_id,
            "title": title,
            "phases": phases,
            "conditions": conditions,
            "intervention_types": intervention_types,
            "status": status,
            "study_type": study_type,
            "design": design,
            "stop_reason": stop_reason,
            "stop_reason_field": STOP_REASON_FIELD if stop_reason else None,
            "source_url": REGISTRY_URL_TEMPLATE.format(nct_id=nct_id),
            "retrieved_at": observed_at,
            "missing_fields": tuple(missing_fields),
        },
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _unique_strings(values: Any) -> tuple[str, ...]:
    if isinstance(values, str) or values is None:
        values = (values,) if values else ()
    if not isinstance(values, Iterable):
        return ()

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return tuple(result)


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _date_value(value: Any) -> str | None:
    return _optional_text(_mapping(value).get("date"))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
