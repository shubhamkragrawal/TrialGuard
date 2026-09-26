from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any, Iterable

from ._common import FAILED, PASSED, item_id, make_check_result, value_of, values_of

CHECK_MEMBERSHIP = "citation_bundle_membership"
CHECK_PASSAGE = "source_passage_support"


def check_citation_bundle_membership(
    references: Iterable[Any],
    evidence_bundle: Iterable[Any],
) -> list[Any]:
    """Verify cited evidence IDs resolve to an unambiguous current-run bundle item."""
    references = list(references)
    bundle = list(evidence_bundle)
    bundle_ids = [value_of(item, "evidence_id", "id") for item in bundle]
    counts = Counter(str(identifier) for identifier in bundle_ids if identifier)
    index = {
        str(value_of(item, "evidence_id", "id")): item
        for item in bundle
        if value_of(item, "evidence_id", "id")
    }

    results: list[Any] = []
    duplicate_ids = sorted(identifier for identifier, count in counts.items() if count > 1)
    if duplicate_ids:
        results.append(
            make_check_result(
                CHECK_MEMBERSHIP,
                FAILED,
                "report",
                "Evidence bundle contains duplicate evidence IDs: "
                + ", ".join(duplicate_ids),
            )
        )

    for position, reference in enumerate(references):
        affected = item_id(reference, position, _item_prefix(reference))
        cited_ids = _citation_ids(reference)
        if not cited_ids:
            results.append(
                make_check_result(
                    CHECK_MEMBERSHIP,
                    FAILED,
                    affected,
                    "No evidence ID was supplied for this item.",
                )
            )
            continue

        missing = sorted({identifier for identifier in cited_ids if identifier not in index})
        mismatched = sorted(
            identifier
            for identifier in cited_ids
            if identifier in index
            and not _identity_matches(reference, index[identifier], identifier)
        )
        if missing or mismatched:
            details = []
            if missing:
                details.append("not in the current evidence bundle: " + ", ".join(missing))
            if mismatched:
                details.append(
                    "resolved to a different NCT ID or source field: "
                    + ", ".join(mismatched)
                )
            results.append(
                make_check_result(
                    CHECK_MEMBERSHIP,
                    FAILED,
                    affected,
                    "; ".join(details),
                )
            )
        else:
            results.append(
                make_check_result(
                    CHECK_MEMBERSHIP,
                    PASSED,
                    affected,
                    f"All {len(cited_ids)} evidence reference(s) resolve in the current bundle.",
                )
            )
    return results


def check_source_passage_support(
    cited_evidence: Iterable[Any],
    evidence_bundle: Iterable[Any],
) -> list[Any]:
    """Verify cited source text is a literal excerpt of the bundled source field."""
    cited_evidence = list(cited_evidence)
    bundle = list(evidence_bundle)
    index = {
        str(value_of(item, "evidence_id", "id")): item
        for item in bundle
        if value_of(item, "evidence_id", "id")
    }
    results: list[Any] = []

    for position, citation in enumerate(cited_evidence):
        affected = item_id(citation, position, "evidence")
        evidence_id = value_of(citation, "evidence_id", "id")
        source = index.get(str(evidence_id)) if evidence_id is not None else None
        cited_passage = value_of(
            citation,
            "source_passage",
            "passage",
            "quoted_passage",
        )
        source_passage = value_of(
            source,
            "source_passage",
            "passage",
            "quoted_passage",
        )

        failures: list[str] = []
        if source is None:
            failures.append("evidence ID is not in the current bundle")
        if not isinstance(cited_passage, str) or not cited_passage.strip():
            failures.append("citation has no source passage")
        if not isinstance(source_passage, str) or not source_passage.strip():
            failures.append("bundle item has no source passage")
        if not failures and not _is_literal_excerpt(cited_passage, source_passage):
            failures.append("cited passage is not a literal excerpt of the source field")
        if source is not None and not _identity_matches(citation, source, str(evidence_id)):
            failures.append("NCT ID or source field differs from the bundle item")

        results.append(
            make_check_result(
                CHECK_PASSAGE,
                FAILED if failures else PASSED,
                affected,
                "; ".join(failures)
                if failures
                else "The cited passage is supported by the bundled source field.",
            )
        )
    return results


def _citation_ids(reference: Any) -> list[str]:
    identifiers = values_of(
        reference,
        "evidence_ids",
        "citation_ids",
        "source_ids",
    )
    if not identifiers:
        identifier = value_of(reference, "evidence_id")
        if identifier is not None:
            identifiers = [str(identifier)]
    return list(
        dict.fromkeys(
            identifier.strip() for identifier in identifiers if identifier.strip()
        )
    )


def _identity_matches(reference: Any, source: Any, evidence_id: str) -> bool:
    direct_id = value_of(reference, "evidence_id", "id")
    if direct_id is not None and str(direct_id) != evidence_id:
        return False
    for names in (("nct_id", "source_nct_id"), ("field_path", "source_field")):
        reference_value = value_of(reference, *names)
        source_value = value_of(source, *names)
        if (
            reference_value is not None
            and source_value is not None
            and str(reference_value) != str(source_value)
        ):
            return False
    return True


def _is_literal_excerpt(cited: str, source: str) -> bool:
    normalized_cited = _normalize_passage(cited)
    normalized_source = _normalize_passage(source)
    return bool(normalized_cited) and normalized_cited in normalized_source


def _normalize_passage(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", normalized).strip()


def _item_prefix(item: Any) -> str:
    if value_of(item, "question", "question_id") is not None:
        return "question"
    return "evidence"


validate_citation_bundle_membership = check_citation_bundle_membership
validate_source_passage_support = check_source_passage_support
