from types import SimpleNamespace

from app.checks import (
    aggregate_release_state,
    check_citation_bundle_membership,
    check_numeric_fact_references,
    check_prohibited_language,
    check_source_passage_support,
)
from app.checks._common import result_name, result_status


def evidence(**overrides):
    values = {
        "evidence_id": "ev-1",
        "nct_id": "NCT00000001",
        "field_path": "protocolSection.statusModule.whyStopped",
        "source_passage": "Enrollment was slower than anticipated.",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def question(**overrides):
    values = {
        "question_id": "q1",
        "question": "What enrollment assumptions warrant closer operational review?",
        "evidence_ids": ["ev-1"],
        "numeric_fact_ids": [],
        "explanation": "The source reports an enrollment difficulty.",
        "uncertainty": "Registry reasons are self-reported.",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def fact(**overrides):
    values = {
        "fact_id": "fact-stop-rate",
        "label": "Resolved-study stop rate",
        "value": 40,
        "unit": "percent",
        "numerator": 2,
        "denominator": 5,
        "derivation": "2 / 5",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def statuses(results):
    return [result_status(result) for result in results]


def test_citation_membership_accepts_current_bundle_ids():
    results = check_citation_bundle_membership([question()], [evidence()])

    assert statuses(results) == ["passed"]


def test_citation_membership_blocks_fabricated_and_spoofed_ids():
    missing = question(evidence_ids=["ev-fabricated"])
    spoofed = evidence(nct_id="NCT99999999")

    results = check_citation_bundle_membership(
        [missing, spoofed],
        [evidence()],
    )

    assert statuses(results) == ["failed", "failed"]
    assert {result_name(result) for result in results} == {
        "citation_bundle_membership"
    }


def test_citation_membership_blocks_ambiguous_bundle_ids():
    results = check_citation_bundle_membership(
        [question()],
        [evidence(), evidence(source_passage="A different passage.")],
    )

    assert statuses(results)[0] == "failed"


def test_source_passage_support_allows_normalized_literal_excerpt():
    cited = evidence(source_passage="Enrollment   was slower")

    results = check_source_passage_support([cited], [evidence()])

    assert statuses(results) == ["passed"]


def test_source_passage_support_blocks_unsupported_passage():
    cited = evidence(source_passage="The treatment was ineffective.")

    results = check_source_passage_support([cited], [evidence()])

    assert statuses(results) == ["failed"]


def test_numeric_check_accepts_value_numerator_and_denominator():
    item = question(
        question=(
            "What operational assumptions warrant review given that "
            "2 of 5 resolved studies stopped, a 40% rate?"
        ),
        numeric_fact_ids=["fact-stop-rate"],
    )

    results = check_numeric_fact_references([item], [fact()])

    assert statuses(results) == ["passed"]


def test_numeric_check_ignores_phase_label_numbers():
    item = question(
        question=(
            "How should the Phase 2 context be reviewed given that "
            "2 of 5 resolved studies stopped?"
        ),
        numeric_fact_ids=["fact-stop-rate"],
    )

    results = check_numeric_fact_references([item], [fact()])

    assert statuses(results) == ["passed"]


def test_numeric_check_ignores_biomedical_identifier_numbers():
    item = question(
        question=(
            "The MK-0646 precedent reported that 2 of 5 resolved studies stopped."
        ),
        numeric_fact_ids=["fact-stop-rate"],
    )

    results = check_numeric_fact_references([item], [fact()])

    assert statuses(results) == ["passed"]


def test_numeric_check_blocks_mismatch_unknown_fact_and_missing_reference():
    mismatch = question(
        question="Which assumptions warrant review given a 75% stop rate?",
        numeric_fact_ids=["fact-stop-rate"],
    )
    unknown = question(
        question="Which assumptions warrant review given a 40% stop rate?",
        numeric_fact_ids=["fact-missing"],
    )
    unreferenced = question(
        question="Which assumptions warrant review given a 40% stop rate?",
        numeric_fact_ids=[],
    )

    results = check_numeric_fact_references(
        [mismatch, unknown, unreferenced],
        [fact()],
    )

    assert statuses(results) == ["failed", "failed", "failed"]


def test_language_check_allows_non_prescriptive_review_question():
    results = check_prohibited_language([question()])

    assert statuses(results) == ["passed"]


def test_language_check_blocks_causal_prescriptive_and_statement_outputs():
    causal = question(
        question="Will changing eligibility reduce termination risk?"
    )
    prescriptive = question(question="The team should change the dose?")
    statement = question(question="Review the recruitment plan.")

    results = check_prohibited_language([causal, prescriptive, statement])

    assert statuses(results) == ["failed", "failed", "failed"]


def test_release_aggregation_supports_full_partial_and_blocked_states():
    passed = {
        "check_name": "citation_bundle_membership",
        "status": "passed",
        "affected_item": "question:q1",
        "reason": "ok",
    }
    failed_q1 = {
        "check_name": "numeric_fact_references",
        "status": "failed",
        "affected_item": "question:q1",
        "reason": "mismatch",
    }
    failed_report = {
        "check_name": "prompt_injection",
        "status": "failed",
        "affected_item": "report",
        "reason": "blocked",
    }
    not_run = {
        "check_name": "evidence_sufficiency",
        "status": "not_run",
        "affected_item": "precedents",
        "reason": "insufficient evidence",
    }

    assert aggregate_release_state([passed], available_item_ids=["q1"]) == "full"
    assert (
        aggregate_release_state(
            [failed_q1],
            available_item_ids=["q1", "q2"],
        )
        == "partial"
    )
    assert (
        aggregate_release_state([failed_q1], available_item_ids=["q1"])
        == "blocked"
    )
    assert (
        aggregate_release_state([failed_report], available_item_ids=["q1"])
        == "blocked"
    )
    assert aggregate_release_state([not_run]) == "partial"
