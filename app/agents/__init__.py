"""TrialGuard's provider-neutral, structured agent runtime."""

from .provider import (
    AgentMessage,
    BedrockConverseConfig,
    BedrockConverseProvider,
    FakeProvider,
    LLMResult,
    Provider,
    ProviderConfigurationError,
    ProviderError,
    ProviderGuardrailError,
    ProviderRequestError,
    ProviderTimeoutError,
    StructuredOutputError,
    TokenUsage,
    parse_structured_output,
)

__all__ = [
    "AgentMessage",
    "BedrockConverseConfig",
    "BedrockConverseProvider",
    "CHALLENGE_ROLE",
    "COORDINATOR_ROLE",
    "EVIDENCE_ROLE",
    "CoordinatorAgentOutput",
    "EvidenceAgentOutput",
    "FakeProvider",
    "LLMResult",
    "Provider",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderGuardrailError",
    "ProviderRequestError",
    "ProviderTimeoutError",
    "StructuredOutputError",
    "TokenUsage",
    "challenge_review",
    "draft_review",
    "parse_structured_output",
    "select_evidence",
]


def __getattr__(name: str):
    """Load shared-schema-dependent role modules only when requested."""

    if name in {"EVIDENCE_ROLE", "EvidenceAgentOutput", "select_evidence"}:
        from .evidence import EVIDENCE_ROLE, EvidenceAgentOutput, select_evidence

        return {
            "EVIDENCE_ROLE": EVIDENCE_ROLE,
            "EvidenceAgentOutput": EvidenceAgentOutput,
            "select_evidence": select_evidence,
        }[name]
    if name in {"COORDINATOR_ROLE", "CoordinatorAgentOutput", "draft_review"}:
        from .coordinator import (
            COORDINATOR_ROLE,
            CoordinatorAgentOutput,
            draft_review,
        )

        return {
            "COORDINATOR_ROLE": COORDINATOR_ROLE,
            "CoordinatorAgentOutput": CoordinatorAgentOutput,
            "draft_review": draft_review,
        }[name]
    if name in {"CHALLENGE_ROLE", "challenge_review"}:
        from .challenge import CHALLENGE_ROLE, challenge_review

        return {
            "CHALLENGE_ROLE": CHALLENGE_ROLE,
            "challenge_review": challenge_review,
        }[name]
    raise AttributeError(name)

