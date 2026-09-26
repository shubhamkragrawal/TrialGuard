from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from ._common import FAILED, PASSED, item_id, make_check_result, value_of, values_of

CHECK_NAME = "numeric_fact_references"
NUMBER_PATTERN = re.compile(
    r"(?<![\w])(?P<number>[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"(?P<percent>\s*%)?"
)
PHASE_NUMBER_PATTERN = re.compile(r"\bphase\s+[1-4]\b", re.IGNORECASE)
IDENTIFIER_NUMBER_PATTERN = re.compile(
    r"\b(?:NCT\d{8}|[A-Z][A-Z0-9]{0,7}-\d{1,8})\b"
)


def check_numeric_fact_references(
    generated_items: Iterable[Any],
    numeric_facts: Iterable[Any],
) -> list[Any]:
    """Check that displayed numbers equal values from explicitly referenced facts."""
    fact_index = {
        str(value_of(fact, "fact_id", "id")): fact
        for fact in numeric_facts
        if value_of(fact, "fact_id", "id")
    }
    results: list[Any] = []

    for position, item in enumerate(generated_items):
        affected = item_id(item, position, "question")
        fact_ids = list(
            dict.fromkeys(
                identifier.strip()
                for identifier in values_of(
                    item,
                    "numeric_fact_ids",
                    "fact_ids",
                    "numeric_facts",
                )
                if identifier.strip()
            )
        )
        text = _generated_text(item)
        displayed = _extract_numbers(text)
        missing_ids = sorted(identifier for identifier in fact_ids if identifier not in fact_index)

        failures: list[str] = []
        if displayed and not fact_ids:
            failures.append("displayed numbers have no numeric fact reference")
        if missing_ids:
            failures.append("unknown numeric fact IDs: " + ", ".join(missing_ids))

        available_facts = [
            fact_index[identifier]
            for identifier in fact_ids
            if identifier in fact_index
        ]
        unmatched = [
            token
            for token in displayed
            if not any(_token_matches_fact(token, fact) for fact in available_facts)
        ]
        if unmatched:
            failures.append(
                "displayed values do not match referenced facts: "
                + ", ".join(token["raw"] for token in unmatched)
            )

        results.append(
            make_check_result(
                CHECK_NAME,
                FAILED if failures else PASSED,
                affected,
                "; ".join(failures)
                if failures
                else (
                    f"All {len(displayed)} displayed numeric value(s) match "
                    "the referenced deterministic facts."
                ),
            )
        )
    return results


def infer_exact_numeric_fact_ids(
    text: str,
    numeric_facts: Iterable[Any],
) -> list[str]:
    """Return fact IDs for displayed values that map to exactly one fact."""
    facts = [
        fact
        for fact in numeric_facts
        if value_of(fact, "fact_id", "id")
    ]
    inferred: list[str] = []
    for token in _extract_numbers(text):
        matches = [
            str(value_of(fact, "fact_id", "id"))
            for fact in facts
            if _token_matches_fact(token, fact)
        ]
        if len(matches) == 1 and matches[0] not in inferred:
            inferred.append(matches[0])
    return inferred


def _generated_text(item: Any) -> str:
    parts = [
        value_of(item, "question", "text", "claim"),
        value_of(item, "explanation", "rationale"),
        value_of(item, "uncertainty", "limitations"),
    ]
    return " ".join(str(part) for part in parts if part)


def _extract_numbers(text: str) -> list[dict[str, Any]]:
    numbers: list[dict[str, Any]] = []
    phase_number_spans = [
        match.span() for match in PHASE_NUMBER_PATTERN.finditer(text)
    ]
    identifier_number_spans = [
        match.span() for match in IDENTIFIER_NUMBER_PATTERN.finditer(text)
    ]
    for match in NUMBER_PATTERN.finditer(text):
        if any(
            start <= match.start() and match.end() <= end
            for start, end in (*phase_number_spans, *identifier_number_spans)
        ):
            continue
        raw_number = match.group("number").replace(",", "")
        try:
            value = Decimal(raw_number)
        except InvalidOperation:
            continue
        numbers.append(
            {
                "value": value,
                "is_percent": bool(match.group("percent")),
                "raw": match.group(0).strip(),
            }
        )
    return numbers


def _token_matches_fact(token: dict[str, Any], fact: Any) -> bool:
    candidates = _fact_values(fact)
    value = token["value"]
    if token["is_percent"]:
        if any(_decimal_equal(value, candidate) for candidate in candidates):
            return True
        return any(_decimal_equal(value / Decimal(100), candidate) for candidate in candidates)
    return any(_decimal_equal(value, candidate) for candidate in candidates)


def _fact_values(fact: Any) -> set[Decimal]:
    values: set[Decimal] = set()
    for name in ("value", "numerator", "denominator"):
        parsed = _as_decimal(value_of(fact, name))
        if parsed is not None:
            values.add(parsed)

    unit = str(value_of(fact, "unit", default="")).lower()
    fact_value = _as_decimal(value_of(fact, "value"))
    if fact_value is not None and ("percent" in unit or "%" in unit):
        if abs(fact_value) <= 1:
            values.add(fact_value * Decimal(100))
        else:
            values.add(fact_value / Decimal(100))
    return values


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _decimal_equal(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= Decimal("0.000001")


validate_numeric_fact_references = check_numeric_fact_references
