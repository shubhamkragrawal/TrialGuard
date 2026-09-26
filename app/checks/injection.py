"""Conservative prompt-injection screening for untrusted registry text."""

from __future__ import annotations

import re
from typing import Any, Iterable

from ._common import FAILED, PASSED, make_check_result, value_of

INJECTION_PATTERNS = (
    re.compile(r"\bignore\b.{0,40}\b(previous|prior|system)\b.{0,20}\binstructions?\b", re.I),
    re.compile(r"\b(system|developer)\s+(message|prompt)\b", re.I),
    re.compile(r"\b(call|invoke|use)\b.{0,25}\b(tool|function|api|endpoint)\b", re.I),
    re.compile(r"\b(reveal|print|return)\b.{0,25}\b(secret|credential|api key|prompt)\b", re.I),
)


def check_prompt_injection(items: Iterable[Any]) -> list[Any]:
    """Block model use when registry text contains instruction-like payloads."""

    suspicious: list[str] = []
    for item in items:
        identifier = str(value_of(item, "evidence_id", "nct_id", default="registry"))
        text_parts = (
            value_of(item, "title", default=""),
            value_of(item, "source_passage", "why_stopped", default=""),
        )
        text = " ".join(str(part) for part in text_parts if part)
        if any(pattern.search(text) for pattern in INJECTION_PATTERNS):
            suspicious.append(identifier)

    if suspicious:
        return [
            make_check_result(
                "prompt_injection",
                FAILED,
                "report",
                "Instruction-like text was detected in untrusted registry fields: "
                + ", ".join(sorted(suspicious)),
            )
        ]
    return [
        make_check_result(
            "prompt_injection",
            PASSED,
            "report",
            "No instruction-like text was detected in the supplied registry fields.",
        )
    ]
