from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from app.checks import (
    aggregate_release_state,
    check_citation_bundle_membership,
    check_numeric_fact_references,
    check_prohibited_language,
    check_source_passage_support,
)
from app.checks._common import result_name, result_status, result_to_dict

DEFAULT_CASES_PATH = Path(__file__).with_name("cases.json")


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    title: str
    expected_release: str
    observed_release: str
    expected_failed_checks: tuple[str, ...]
    observed_failed_checks: tuple[str, ...]
    matched: bool
    synthetic: bool
    checks: tuple[dict[str, Any], ...]


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    case_path = Path(path)
    cases = json.loads(case_path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or len(cases) != 7:
        raise ValueError("The frozen evaluation set must contain exactly seven cases.")
    identifiers = [str(case.get("case_id", "")) for case in cases]
    if len(set(identifiers)) != 7 or any(not identifier for identifier in identifiers):
        raise ValueError("Every evaluation case must have a unique non-empty case_id.")
    if any(case.get("synthetic") is not True for case in cases):
        raise ValueError("Offline evaluation cases must be explicitly marked synthetic.")
    return cases


def run_case(
    case: dict[str, Any],
    *,
    cases_path: str | Path = DEFAULT_CASES_PATH,
) -> EvalResult:
    base_directory = Path(cases_path).resolve().parent
    fixture_path = base_directory / str(case["fixture"])
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    bundle = fixture.get("evidence_bundle", [])
    facts = fixture.get("numeric_facts", [])
    fake_output = fixture.get("fake_model_output", {})
    selected = fake_output.get("selected_evidence", [])
    questions = fake_output.get("questions", [])

    checks: list[Any] = list(fixture.get("preflight_checks", []))
    checks.extend(check_citation_bundle_membership(selected, bundle))
    checks.extend(check_citation_bundle_membership(questions, bundle))
    checks.extend(check_source_passage_support(selected, bundle))
    checks.extend(check_numeric_fact_references(questions, facts))
    checks.extend(check_prohibited_language(questions))

    question_ids = [
        str(question.get("question_id") or question.get("id"))
        for question in questions
        if question.get("question_id") or question.get("id")
    ]
    observed_release = aggregate_release_state(
        checks,
        available_item_ids=question_ids,
    )
    observed_failed = tuple(
        sorted(
            {
                result_name(result)
                for result in checks
                if result_status(result) == "failed"
            }
        )
    )
    expected_failed = tuple(sorted(case.get("expected_failed_checks", [])))
    expected_release = str(case["expected_release"])

    return EvalResult(
        case_id=str(case["case_id"]),
        title=str(case["title"]),
        expected_release=expected_release,
        observed_release=observed_release,
        expected_failed_checks=expected_failed,
        observed_failed_checks=observed_failed,
        matched=(
            observed_release == expected_release
            and observed_failed == expected_failed
        ),
        synthetic=bool(case["synthetic"]),
        checks=tuple(result_to_dict(result) for result in checks),
    )


def run_all(path: str | Path = DEFAULT_CASES_PATH) -> list[EvalResult]:
    return [run_case(case, cases_path=path) for case in load_cases(path)]


def summarize(results: Iterable[EvalResult]) -> dict[str, Any]:
    results = list(results)
    return {
        "fixture_mode": "synthetic_offline",
        "total": len(results),
        "matched": sum(result.matched for result in results),
        "all_matched": all(result.matched for result in results),
        "results": [asdict(result) for result in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TrialGuard's frozen offline evaluation.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    summary = summarize(run_all(arguments.cases))
    rendered = json.dumps(summary, indent=2)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if summary["all_matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
