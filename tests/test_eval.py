from eval.run_eval import load_cases, run_all, summarize  # noqa: I001


EXPECTED_CASE_IDS = [
    "evidence_rich",
    "sparse_evidence",
    "invalid_nct_id",
    "resolved_prospective",
    "prompt_injection",
    "fabricated_citation",
    "numeric_mismatch",
]


def test_frozen_evaluation_defines_exactly_seven_synthetic_cases():
    cases = load_cases()

    assert [case["case_id"] for case in cases] == EXPECTED_CASE_IDS
    assert all(case["synthetic"] is True for case in cases)


def test_all_fixed_cases_match_frozen_expected_behavior():
    results = run_all()
    summary = summarize(results)

    assert summary["total"] == 7
    assert summary["matched"] == 7
    assert summary["all_matched"] is True


def test_adversarial_outputs_are_blocked_by_expected_checks():
    results = {result.case_id: result for result in run_all()}

    assert results["fabricated_citation"].observed_release == "blocked"
    assert results["fabricated_citation"].observed_failed_checks == (
        "citation_bundle_membership",
        "source_passage_support",
    )
    assert results["numeric_mismatch"].observed_release == "blocked"
    assert results["numeric_mismatch"].observed_failed_checks == (
        "numeric_fact_references",
    )
