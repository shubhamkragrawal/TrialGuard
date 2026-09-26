from __future__ import annotations

import re
from typing import Any, Iterable

from ._common import FAILED, PASSED, item_id, make_check_result, value_of

CHECK_NAME = "prohibited_language"

CAUSAL_PATTERNS = (
    re.compile(
        r"\b(?:will|would|guarantees?|ensures?|causes?|prevents?)\b"
        r".{0,70}\b(?:reduce|increase|prevent|avoid|eliminate|improve|cause|lead|"
        r"termination|failure|success|risk)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reduces?|increases?|prevents?|causes?|ensures?|guarantees?|"
        r"leads?\s+to|results?\s+in)\b.{0,70}\b(?:termination|failure|success|risk)\b",
        re.IGNORECASE,
    ),
)

PRESCRIPTIVE_PATTERNS = (
    re.compile(
        r"\b(?:should|must|need(?:s)?\s+to|ought\s+to)\s+"
        r"(?:change|increase|decrease|exclude|include|use|adopt|stop|proceed|"
        r"terminate|approve|reject|redesign|dose|enroll)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:we\s+recommend|recommend(?:ed|ation)?\s+(?:that|to)|"
        r"go\s*/?\s*no[- ]?go|do\s+not\s+proceed|proceed\s+with|"
        r"approve\s+the\s+trial|terminate\s+the\s+trial)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:change|increase|decrease|exclude|include|adopt|stop|proceed|"
        r"terminate|approve|reject|redesign)\b",
        re.IGNORECASE,
    ),
)

CLINICAL_OR_REGULATORY_PATTERNS = (
    re.compile(
        r"\b(?:prescribe|treat\s+(?:the\s+)?patients?|safe\s+and\s+effective|"
        r"clinically\s+superior|guarantee(?:s|d)?\s+(?:FDA|regulatory)\s+approval|"
        r"will\s+satisfy\s+(?:the\s+)?(?:FDA|regulator))\b",
        re.IGNORECASE,
    ),
)


def check_prohibited_language(generated_items: Iterable[Any]) -> list[Any]:
    """Block causal promises, operational directives, and clinical advice."""
    results: list[Any] = []
    for position, item in enumerate(generated_items):
        affected = item_id(item, position, "question")
        question = value_of(item, "question", "text", "claim", default="")
        explanation = value_of(item, "explanation", "rationale", default="")
        text = " ".join(str(part) for part in (question, explanation) if part).strip()

        categories: list[str] = []
        if any(pattern.search(text) for pattern in CAUSAL_PATTERNS):
            categories.append("causal claim")
        if any(pattern.search(text) for pattern in PRESCRIPTIVE_PATTERNS):
            categories.append("prescriptive or go/no-go advice")
        if any(pattern.search(text) for pattern in CLINICAL_OR_REGULATORY_PATTERNS):
            categories.append("clinical or regulatory advice")
        if question and not str(question).rstrip().endswith("?"):
            categories.append("output is not phrased as a review question")

        results.append(
            make_check_result(
                CHECK_NAME,
                FAILED if categories else PASSED,
                affected,
                "Detected " + ", ".join(categories) + "."
                if categories
                else "No prohibited causal, prescriptive, clinical, or go/no-go wording found.",
            )
        )
    return results


validate_prohibited_language = check_prohibited_language
