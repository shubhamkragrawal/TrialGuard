"""Small compatibility helpers for the shared schema module.

The registry workstream deliberately does not own ``app.schemas``.  These
helpers keep field-name compatibility explicit while that shared contract is
being integrated.
"""

from __future__ import annotations

from importlib import import_module
from inspect import Parameter, signature
from typing import Any, Iterable, Mapping

_FIELD_ALIASES = {
    "phase": ("phases",),
    "phases": ("phase",),
    "status": ("overall_status",),
    "overall_status": ("status",),
    "registry_url": ("source_url",),
    "source_url": ("registry_url",),
    "retrieval_time": ("retrieved_at",),
    "retrieved_at": ("retrieval_time",),
    "source_field": ("stop_reason_field", "field_path"),
    "stop_reason_field": ("source_field", "field_path"),
    "field_path": ("source_field", "stop_reason_field"),
    "why_stopped": ("stop_reason",),
    "stop_reason": ("why_stopped",),
    "retrieval_timestamp": ("retrieved_at", "retrieval_time"),
    "total_retrieved": ("records_retrieved",),
    "records_retrieved": ("total_retrieved",),
    "complete": ("pagination_complete",),
    "pagination_complete": ("complete",),
    "denominator": ("resolved_denominator",),
    "resolved_denominator": ("denominator",),
    "stop_rate": ("resolved_stop_rate",),
    "resolved_stop_rate": ("stop_rate",),
}


def construct_schema(model_name: str, values: Mapping[str, Any]) -> Any:
    """Construct a shared schema, accepting the documented naming variants."""

    model = getattr(import_module("app.schemas"), model_name)
    field_names = _accepted_fields(model)
    if field_names is None:
        return model(**dict(values))

    kwargs: dict[str, Any] = {}
    for field_name in field_names:
        if field_name in values:
            kwargs[field_name] = values[field_name]
            continue
        for alias in _FIELD_ALIASES.get(field_name, ()):
            if alias in values:
                kwargs[field_name] = values[alias]
                break
    return model(**kwargs)


def read_field(record: Any, *names: str, default: Any = None) -> Any:
    """Read a value from a Pydantic model, dataclass, or mapping."""

    for name in names:
        if isinstance(record, Mapping) and name in record:
            return record[name]
        if hasattr(record, name):
            return getattr(record, name)
    return default


def string_list(record: Any, *names: str) -> tuple[str, ...]:
    value = read_field(record, *names, default=())
    if value is None:
        return ()
    if isinstance(value, str):
        value = (value,)
    return tuple(str(item) for item in value if item is not None and str(item))


def normalized_set(values: Iterable[str]) -> set[str]:
    return {" ".join(value.casefold().split()) for value in values if value.strip()}


def _accepted_fields(model: Any) -> set[str] | None:
    pydantic_fields = getattr(model, "model_fields", None)
    if pydantic_fields is not None:
        return set(pydantic_fields)

    try:
        parameters = signature(model).parameters
    except (TypeError, ValueError):
        return None
    if any(parameter.kind == Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return None
    return {
        name
        for name, parameter in parameters.items()
        if name != "self"
        and parameter.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
    }
