"""Bounded TrialGuard assessment flow and deterministic release authority."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Optional

import httpx

from app.agents import (
    BedrockConverseConfig,
    BedrockConverseProvider,
    FakeProvider,
    Provider,
    ProviderError,
)
from app.agents.challenge import challenge_review
from app.agents.coordinator import CoordinatorAgentOutput, draft_review
from app.agents.evidence import EvidenceAgentOutput, select_evidence
from app.checks import (
    aggregate_release_state,
    check_citation_bundle_membership,
    check_numeric_fact_references,
    check_prohibited_language,
    check_prompt_injection,
    check_source_passage_support,
)
from app.config import Settings
from app.costs import summarize_usage
from app.registry import ClinicalTrialsClient, rank_precedents, retrieve_cohort
from app.schemas import (
    AssessmentMode,
    AssessmentReport,
    AssessRequest,
    ChallengeAction,
    ChallengeDecision,
    ChallengeFinding,
    CheckResult,
    CheckStatus,
    ReleaseState,
    ReviewQuestion,
    TraceEvent,
)

RESOLVED_STATUSES = {"COMPLETED", "TERMINATED", "WITHDRAWN"}
STANDARD_LIMITATIONS = [
    "ClinicalTrials.gov records are self-reported and may be incomplete or stale.",
    "Similarity and cohort statistics describe public records; they do not establish causation.",
    "This report supports qualified human review and is not clinical or regulatory advice.",
]


class AssessmentService:
    """Coordinates read-only data tools and bounded model roles."""

    def __init__(
        self,
        settings: Settings,
        *,
        provider: Optional[Provider] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        cohort_limit: int = 300,
    ) -> None:
        self.settings = settings
        self._provider = provider
        self._http_client = http_client
        self._cohort_limit = cohort_limit

    async def assess(self, request: AssessRequest) -> AssessmentReport:
        run_id = uuid.uuid4().hex[:12]
        trace: list[TraceEvent] = []
        model_results: list[Any] = []
        started = time.perf_counter()

        registry_started = time.perf_counter()
        async with ClinicalTrialsClient(
            http_client=self._http_client,
            base_url=self.settings.registry_base_url,
            max_records=self._cohort_limit,
        ) as client:
            trial = await client.fetch_trial(request.nct_id)
            retrieved = await retrieve_cohort(
                client,
                trial,
                max_records=self._cohort_limit,
            )
        trace.append(
            TraceEvent(
                stage="registry_retrieval",
                status="passed",
                duration_ms=_elapsed_ms(registry_started),
                cache_hit=trial.cache_hit,
            )
        )

        mode, framing_check, framing_limitation = _resolve_mode(request, trial.status)
        candidates = rank_precedents(trial, retrieved.records, limit=10)
        checks: list[CheckResult] = [framing_check]
        checks.extend(check_prompt_injection([trial, *candidates]))

        if any(check.status == CheckStatus.FAILED for check in checks):
            return _blocked_without_model(
                run_id=run_id,
                mode=mode,
                trial=trial,
                retrieved=retrieved,
                checks=checks,
                trace=trace,
                started=started,
                limitation=framing_limitation,
                settings=self.settings,
            )

        provider = self._provider or self._build_provider(
            candidates,
            retrieved.numeric_facts,
        )

        try:
            evidence_result = await asyncio.to_thread(
                select_evidence,
                provider,
                target_trial=trial,
                candidates=candidates,
                timeout=_role_timeout(self.settings),
                metadata={"run_id": run_id, "nct_id": trial.nct_id},
            )
            model_results.append(evidence_result)
            trace.append(_model_trace("evidence_agent", evidence_result))

            selected = evidence_result.output.precedents
            evidence_checks = [
                *check_citation_bundle_membership(selected, candidates),
                *check_source_passage_support(selected, candidates),
            ]
            checks.extend(evidence_checks)
            if evidence_result.output.insufficient_evidence:
                checks.append(
                    CheckResult(
                        check_name="evidence_sufficiency",
                        status=CheckStatus.NOT_RUN,
                        affected_item="precedents",
                        reason="The Evidence Agent found insufficient comparable evidence.",
                    )
                )

            coordinator_result = await asyncio.to_thread(
                draft_review,
                provider,
                target_trial=trial,
                cohort=retrieved.cohort,
                precedents=selected,
                numeric_facts=retrieved.numeric_facts,
                timeout=_role_timeout(self.settings),
                metadata={"run_id": run_id, "nct_id": trial.nct_id},
            )
            model_results.append(coordinator_result)
            trace.append(_model_trace("coordinator_agent", coordinator_result))

            question_checks = _check_questions(
                coordinator_result.output.questions,
                selected,
                retrieved.numeric_facts,
            )
            checks.extend(question_checks)

            challenge_result = await asyncio.to_thread(
                challenge_review,
                provider,
                draft=coordinator_result.output,
                evidence=selected,
                numeric_facts=retrieved.numeric_facts,
                deterministic_checks=checks,
                timeout=_role_timeout(self.settings),
                metadata={"run_id": run_id, "nct_id": trial.nct_id},
            )
            model_results.append(challenge_result)
            trace.append(_model_trace("challenge_agent", challenge_result))

            revision_count = 0
            if challenge_result.output.action == ChallengeAction.REVISE:
                revision_count = 1
                checks = checks[: len(checks) - len(question_checks)]
                coordinator_result = await asyncio.to_thread(
                    draft_review,
                    provider,
                    target_trial=trial,
                    cohort=retrieved.cohort,
                    precedents=selected,
                    numeric_facts=retrieved.numeric_facts,
                    revision_request=challenge_result.output,
                    timeout=_role_timeout(self.settings),
                    metadata={
                        "run_id": run_id,
                        "nct_id": trial.nct_id,
                        "revision": 1,
                    },
                )
                model_results.append(coordinator_result)
                trace.append(_model_trace("coordinator_revision", coordinator_result))
                checks.extend(
                    _check_questions(
                        coordinator_result.output.questions,
                        selected,
                        retrieved.numeric_facts,
                    )
                )
                challenge_result = await asyncio.to_thread(
                    challenge_review,
                    provider,
                    draft=coordinator_result.output,
                    evidence=selected,
                    numeric_facts=retrieved.numeric_facts,
                    deterministic_checks=checks,
                    timeout=_role_timeout(self.settings),
                    metadata={
                        "run_id": run_id,
                        "nct_id": trial.nct_id,
                        "revision": 1,
                    },
                )
                model_results.append(challenge_result)
                trace.append(_model_trace("challenge_revision", challenge_result))

            if challenge_result.output.action != ChallengeAction.APPROVE:
                checks.append(
                    CheckResult(
                        check_name="challenge_review",
                        status=CheckStatus.FAILED,
                        affected_item="report",
                        reason=challenge_result.output.summary,
                    )
                )

            questions = coordinator_result.output.questions
            release = aggregate_release_state(
                checks,
                available_item_ids=[question.question_id for question in questions],
            )
            trace.append(
                TraceEvent(
                    stage="deterministic_release_gate",
                    status=release,
                    duration_ms=0,
                    evidence_ids=[item.evidence_id for item in selected],
                )
            )
            limitations = [
                *STANDARD_LIMITATIONS,
                *retrieved.cohort.limitations,
                *evidence_result.output.limitations,
                *coordinator_result.output.limitations,
            ]
            if framing_limitation:
                limitations.append(framing_limitation)

            return AssessmentReport(
                run_id=run_id,
                mode=mode,
                trial=trial,
                cohort=retrieved.cohort,
                precedents=selected,
                numeric_facts=list(retrieved.numeric_facts),
                questions=questions,
                challenge=challenge_result.output,
                checks=checks,
                release_state=ReleaseState(release),
                revision_count=revision_count,
                trace=trace,
                usage=summarize_usage(model_results, self.settings),
                limitations=_deduplicate(limitations),
            )
        except ProviderError as exc:
            checks.append(
                CheckResult(
                    check_name="model_runtime",
                    status=CheckStatus.FAILED,
                    affected_item="report",
                    reason=str(exc),
                )
            )
            trace.append(
                TraceEvent(
                    stage="model_runtime",
                    status="failed",
                    duration_ms=_elapsed_ms(started),
                    message=str(exc),
                )
            )
            return _blocked_without_model(
                run_id=run_id,
                mode=mode,
                trial=trial,
                retrieved=retrieved,
                checks=checks,
                trace=trace,
                started=started,
                limitation=framing_limitation,
                settings=self.settings,
                model_results=model_results,
            )

    def _build_provider(
        self,
        candidates: list[Any],
        numeric_facts: tuple[Any, ...],
    ) -> Provider:
        if self.settings.bedrock_ready:
            return BedrockConverseProvider(
                BedrockConverseConfig(
                    model_id=self.settings.bedrock_model_id,
                    region_name=self.settings.aws_region,
                    default_timeout_seconds=_role_timeout(self.settings),
                    max_attempts=1,
                    guardrail_identifier=self.settings.bedrock_guardrail_id or None,
                    guardrail_version=self.settings.bedrock_guardrail_version or None,
                )
            )
        return _demo_provider(candidates, numeric_facts)


def _demo_provider(candidates: list[Any], numeric_facts: tuple[Any, ...]) -> FakeProvider:
    selected = candidates[:3]
    questions = [
        ReviewQuestion(
            question_id=f"q{index}",
            question=(
                "Which operational assumptions warrant review in light of "
                "the cited stopped study?"
            ),
            evidence_ids=[evidence.evidence_id],
            numeric_fact_ids=[],
            explanation=(
                "The cited registry stop reason identifies an operational issue "
                "that may be useful to discuss."
            ),
            uncertainty=(
                "The registry reason is self-reported and does not establish "
                "that the studies are otherwise equivalent."
            ),
        )
        for index, evidence in enumerate(selected, start=1)
    ]
    evidence_output = EvidenceAgentOutput(
        precedents=selected,
        insufficient_evidence=not bool(selected),
        limitations=[] if selected else ["No comparable stopped study was available."],
    )
    coordinator_output = CoordinatorAgentOutput(
        questions=questions,
        limitations=[] if questions else ["No evidence-linked question was generated."],
    )
    challenge_output = ChallengeDecision(
        action=ChallengeAction.APPROVE,
        findings=[],
        summary="The offline checked demo output stays within the supplied evidence.",
    )
    return FakeProvider(
        {
            "evidence": [evidence_output],
            "coordinator": [coordinator_output],
            "challenge": [challenge_output],
        }
    )


def _check_questions(
    questions: list[ReviewQuestion],
    evidence: list[Any],
    numeric_facts: tuple[Any, ...],
) -> list[CheckResult]:
    return [
        *check_citation_bundle_membership(questions, evidence),
        *check_numeric_fact_references(questions, numeric_facts),
        *check_prohibited_language(questions),
    ]


def _resolve_mode(
    request: AssessRequest,
    status: str,
) -> tuple[AssessmentMode, CheckResult, Optional[str]]:
    resolved = status.upper() in RESOLVED_STATUSES
    if request.mode == AssessmentMode.PROSPECTIVE and resolved:
        return (
            AssessmentMode.RETROSPECTIVE,
            CheckResult(
                check_name="status_framing",
                status=CheckStatus.PASSED,
                affected_item="report",
                reason=(
                    "The resolved study was automatically labeled retrospective; "
                    "no historical forecasting claim is made."
                ),
            ),
            "The requested study is resolved, so TrialGuard presents a retrospective review.",
        )
    return (
        request.mode,
        CheckResult(
            check_name="status_framing",
            status=CheckStatus.PASSED,
            affected_item="report",
            reason="The requested review mode is consistent with the registry status.",
        ),
        None,
    )


def _blocked_without_model(
    *,
    run_id: str,
    mode: AssessmentMode,
    trial: Any,
    retrieved: Any,
    checks: list[CheckResult],
    trace: list[TraceEvent],
    started: float,
    limitation: Optional[str],
    settings: Settings,
    model_results: Optional[list[Any]] = None,
) -> AssessmentReport:
    trace.append(
        TraceEvent(
            stage="deterministic_release_gate",
            status="blocked",
            duration_ms=_elapsed_ms(started),
        )
    )
    limitations = [*STANDARD_LIMITATIONS, *retrieved.cohort.limitations]
    if limitation:
        limitations.append(limitation)
    return AssessmentReport(
        run_id=run_id,
        mode=mode,
        trial=trial,
        cohort=retrieved.cohort,
        precedents=[],
        numeric_facts=list(retrieved.numeric_facts),
        questions=[],
        challenge=ChallengeDecision(
            action=ChallengeAction.BLOCK,
            findings=[
                ChallengeFinding(
                    finding_id="deterministic-block",
                    reason="A required deterministic check or runtime stage failed.",
                )
            ],
            summary="The report was blocked before release.",
        ),
        checks=checks,
        release_state=ReleaseState.BLOCKED,
        revision_count=0,
        trace=trace,
        usage=summarize_usage(model_results or [], settings),
        limitations=_deduplicate(limitations),
    )


def _model_trace(stage: str, result: Any) -> TraceEvent:
    return TraceEvent(
        stage=stage,
        status="passed",
        duration_ms=result.latency_ms,
        model_id=result.model_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


def _role_timeout(settings: Settings) -> float:
    return max(5.0, settings.report_timeout_seconds / 3)


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1_000))


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
