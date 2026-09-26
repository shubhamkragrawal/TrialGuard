from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from inspect import signature
from typing import Any, Mapping, Sequence

try:
    from app.schemas import CheckResult as SchemaCheckResult
except ImportError:  # Allows this workstream to run before shared schemas land.

    @dataclass(frozen=True)
    class SchemaCheckResult:
        check_name: str
        status: str
        affected_item: str | None
        reason: str


CheckResult = SchemaCheckResult

PASSED = "passed"
FAILED = "failed"
NOT_RUN = "not_run"


def value_of(item: Any, *names: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        for name in names:
            if name in item:
                return item[name]
        return default

    for name in names:
        if hasattr(item, name):
            return getattr(item, name)
    return default


def values_of(item: Any, *names: str) -> list[str]:
    value = value_of(item, *names)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(entry) for entry in value if entry is not None]
    return [str(value)]


def item_id(item: Any, index: int, prefix: str) -> str:
    identifier = value_of(
        item,
        f"{prefix}_id",
        "question_id",
        "evidence_id",
        "id",
    )
    return f"{prefix}:{identifier if identifier is not None else index + 1}"


def _constructor_fields() -> set[str]:
    model_fields = getattr(CheckResult, "model_fields", None)
    if model_fields:
        return set(model_fields)
    if is_dataclass(CheckResult):
        return {field.name for field in fields(CheckResult)}
    try:
        return set(signature(CheckResult).parameters)
    except (TypeError, ValueError):
        return {"check_name", "status", "affected_item", "reason"}


def make_check_result(
    check_name: str,
    status: str,
    affected_item: str | None,
    reason: str,
) -> CheckResult:
    available = _constructor_fields()
    kwargs: dict[str, Any] = {}

    _set_first(kwargs, available, ("check_name", "name", "check"), check_name)
    if "status" in available:
        kwargs["status"] = status
    elif "outcome" in available:
        kwargs["outcome"] = status
    elif "result" in available:
        kwargs["result"] = status
    elif "passed" in available:
        kwargs["passed"] = None if status == NOT_RUN else status == PASSED

    _set_first(
        kwargs,
        available,
        ("affected_item", "item_id", "target", "scope"),
        affected_item,
    )
    _set_first(kwargs, available, ("reason", "message", "detail"), reason)
    return CheckResult(**kwargs)


def _set_first(
    target: dict[str, Any],
    available: set[str],
    names: tuple[str, ...],
    value: Any,
) -> None:
    for name in names:
        if name in available:
            target[name] = value
            return


def result_status(result: Any) -> str:
    status = value_of(result, "status", "outcome", "result")
    if status is not None:
        status = getattr(status, "value", status)
        normalized = str(status).strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {PASSED, "pass", "ok", "success", "true"}:
            return PASSED
        if normalized in {FAILED, "fail", "blocked", "error", "false"}:
            return FAILED
        if normalized in {NOT_RUN, "skipped", "unknown", "none"}:
            return NOT_RUN

    passed = value_of(result, "passed")
    if passed is True:
        return PASSED
    if passed is False:
        return FAILED
    return NOT_RUN


def result_name(result: Any) -> str:
    return str(value_of(result, "check_name", "name", "check", default="unknown"))


def result_affected_item(result: Any) -> str | None:
    affected = value_of(result, "affected_item", "item_id", "target", "scope")
    return None if affected is None else str(affected)


def result_reason(result: Any) -> str:
    return str(value_of(result, "reason", "message", "detail", default=""))


def result_to_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, Mapping):
        return dict(result)
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if is_dataclass(result):
        return asdict(result)
    return {
        "check_name": result_name(result),
        "status": result_status(result),
        "affected_item": result_affected_item(result),
        "reason": result_reason(result),
    }
