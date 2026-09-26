from __future__ import annotations

from typing import Any, Iterable

from ._common import (
    FAILED,
    NOT_RUN,
    result_affected_item,
    result_status,
)

RELEASE_FULL = "full"
RELEASE_PARTIAL = "partial"
RELEASE_BLOCKED = "blocked"

GLOBAL_TARGETS = {None, "", "global", "report", "brief", "all"}


def aggregate_release_state(
    checks: Iterable[Any],
    *,
    available_item_ids: Iterable[str] | None = None,
) -> str:
    """Aggregate deterministic results into full, partial, or blocked release."""
    checks = list(checks)
    failed = [result for result in checks if result_status(result) == FAILED]
    not_run = [result for result in checks if result_status(result) == NOT_RUN]

    if any(_is_global(result_affected_item(result)) for result in failed):
        return RELEASE_BLOCKED

    item_ids = {_normalize_item(identifier) for identifier in (available_item_ids or [])}
    failed_items = {
        _normalize_item(affected)
        for affected in (result_affected_item(result) for result in failed)
        if affected is not None
    }

    if failed:
        if not item_ids or item_ids.issubset(failed_items):
            return RELEASE_BLOCKED
        return RELEASE_PARTIAL
    if not_run:
        return RELEASE_PARTIAL
    return RELEASE_FULL


def _is_global(affected_item: str | None) -> bool:
    if affected_item is None:
        return True
    return affected_item.strip().lower() in GLOBAL_TARGETS


def _normalize_item(identifier: str) -> str:
    normalized = str(identifier).strip().lower()
    for prefix in ("question:", "evidence:", "item:"):
        if normalized.startswith(prefix):
            return normalized.removeprefix(prefix)
    return normalized


determine_release_state = aggregate_release_state
