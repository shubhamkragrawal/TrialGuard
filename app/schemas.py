"""Shared contracts for retrieval, agents, checks, UI, and evaluation."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NCT_ID_PATTERN = re.compile(r"^NCT\d{8}$", re.IGNORECASE)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AssessmentMode(str, Enum):
    PROSPECTIVE = "prospective"
    RETROSPECTIVE = "retrospective"


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


class ChallengeAction(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    BLOCK = "block"


class ReleaseState(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class ChatDisposition(str, Enum):
    ANSWERED = "answered"
    UNSUPPORTED = "unsupported"
    REFUSED = "refused"


class AssessRequest(StrictModel):
    nct_id: str
    mode: AssessmentMode = AssessmentMode.PROSPECTIVE

    @field_validator("nct_id")
    @classmethod
    def normalize_nct_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not NCT_ID_PATTERN.fullmatch(normalized):
            raise ValueError("NCT ID must match NCT followed by eight digits")
        return normalized


class TrialRecord(StrictModel):
    nct_id: str
    title: str
    phase: List[str] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)
    intervention_types: List[str] = Field(default_factory=list)
    status: str
    study_type: Optional[str] = None
    design: Dict[str, Union[str, int, float, bool, None]] = Field(
        default_factory=dict
    )
    why_stopped: Optional[str] = None
    source_url: str
    retrieved_at: datetime = Field(default_factory=utc_now)
    missing_fields: List[str] = Field(default_factory=list)
    cache_hit: bool = False

    @field_validator("nct_id")
    @classmethod
    def validate_nct_id(cls, value: str) -> str:
        normalized = value.upper()
        if not NCT_ID_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid NCT ID")
        return normalized


class EvidenceItem(StrictModel):
    evidence_id: str
    nct_id: str
    title: Optional[str] = None
    phase: List[str] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)
    field_path: str
    source_passage: str
    source_url: str
    why_stopped: Optional[str] = None
    relevance_features: Dict[str, float] = Field(default_factory=dict)
    similarity_score: Optional[float] = Field(default=None, ge=0, le=1)
    relevance_summary: Optional[str] = None
    retrieval_timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("nct_id")
    @classmethod
    def validate_nct_id(cls, value: str) -> str:
        normalized = value.upper()
        if not NCT_ID_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid evidence NCT ID")
        return normalized


class CohortResult(StrictModel):
    filters: Dict[str, Union[str, List[str], int, float, bool, None]]
    status_counts: Dict[str, int]
    records_retrieved: int = Field(ge=0)
    pagination_complete: bool
    denominator: Optional[int] = Field(default=None, ge=0)
    resolved_stop_rate: Optional[float] = Field(default=None, ge=0, le=1)
    limitations: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_rate_is_complete(self) -> "CohortResult":
        if not self.pagination_complete and self.resolved_stop_rate is not None:
            raise ValueError("A stop rate requires complete cohort pagination")
        if self.resolved_stop_rate is not None and not self.denominator:
            raise ValueError("A stop rate requires a non-zero denominator")
        return self


class NumericFact(StrictModel):
    fact_id: str
    label: str
    value: Union[int, float]
    unit: str
    numerator: Optional[Union[int, float]] = None
    denominator: Optional[Union[int, float]] = None
    derivation: str


class ReviewQuestion(StrictModel):
    question_id: str
    question: str
    evidence_ids: List[str] = Field(default_factory=list)
    numeric_fact_ids: List[str] = Field(default_factory=list)
    explanation: str
    uncertainty: str


class ChallengeFinding(StrictModel):
    finding_id: str
    affected_question_ids: List[str] = Field(default_factory=list)
    reason: str
    requested_correction: Optional[str] = None


class ChallengeDecision(StrictModel):
    action: ChallengeAction
    findings: List[ChallengeFinding] = Field(default_factory=list)
    summary: str


class CheckResult(StrictModel):
    check_name: str
    status: CheckStatus
    affected_item: Optional[str] = None
    reason: str
    tool_evidence: Dict[str, Any] = Field(default_factory=dict)


class TraceEvent(StrictModel):
    stage: str
    status: str
    duration_ms: int = Field(default=0, ge=0)
    cache_hit: Optional[bool] = None
    model_id: Optional[str] = None
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    evidence_ids: List[str] = Field(default_factory=list)
    message: Optional[str] = None


class UsageSummary(StrictModel):
    model_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: Optional[float] = Field(default=None, ge=0)
    pricing_basis: str = "Token counts measured; pricing not configured."


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=500)


class ChatAgentOutput(StrictModel):
    """Structured model output before deterministic release checks."""

    answer: str = Field(min_length=1, max_length=1_200)
    evidence_ids: List[str] = Field(max_length=5)
    numeric_fact_ids: List[str] = Field(max_length=5)


class ChatSource(StrictModel):
    evidence_id: str
    nct_id: str
    title: Optional[str] = None
    source_url: str


class ChatTraceMetadata(StrictModel):
    stage: str = "report_chat"
    status: str
    duration_ms: int = Field(default=0, ge=0)
    provider: str
    model_id: Optional[str] = None
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    guardrail_action: Optional[str] = None


class ChatResponse(StrictModel):
    run_id: str
    turn: int = Field(ge=1, le=5)
    disposition: ChatDisposition
    answer: str
    evidence_ids: List[str] = Field(default_factory=list)
    numeric_fact_ids: List[str] = Field(default_factory=list)
    sources: List[ChatSource] = Field(default_factory=list)
    checks: List[CheckResult] = Field(default_factory=list)
    trace: ChatTraceMetadata
    usage: UsageSummary = Field(default_factory=UsageSummary)


class AssessmentReport(StrictModel):
    run_id: str
    mode: AssessmentMode
    trial: TrialRecord
    cohort: CohortResult
    precedents: List[EvidenceItem] = Field(default_factory=list)
    numeric_facts: List[NumericFact] = Field(default_factory=list)
    questions: List[ReviewQuestion] = Field(default_factory=list, max_length=3)
    challenge: ChallengeDecision
    checks: List[CheckResult] = Field(default_factory=list)
    release_state: ReleaseState
    revision_count: int = Field(default=0, ge=0, le=1)
    trace: List[TraceEvent] = Field(default_factory=list)
    usage: UsageSummary = Field(default_factory=UsageSummary)
    limitations: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
