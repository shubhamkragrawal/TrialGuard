"""Model-provider abstractions for TrialGuard's bounded agent roles.

The provider returns validated structured data and operational metadata only.
It deliberately does not retain prompts, raw model responses, or hidden
reasoning in ``LLMResult``.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
import time
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
)

from pydantic import BaseModel

OutputT = TypeVar("OutputT", bound=BaseModel)
TraceScalar = Union[str, int, float, bool, None]

_JSON_FENCE = re.compile(
    r"^\s*```(?:json)?\s*(?P<payload>.*?)\s*```\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)
_RETRYABLE_ERROR_CODES = frozenset(
    {
        "InternalServerException",
        "ModelNotReadyException",
        "ModelTimeoutException",
        "RequestTimeout",
        "ServiceUnavailableException",
        "ThrottlingException",
        "TooManyRequestsException",
    }
)
_TRACE_METADATA_KEYS = frozenset(
    {
        "run_id",
        "stage",
        "revision",
        "nct_id",
        "mode",
        "evidence_count",
        "question_count",
        "input_tokens",
        "output_tokens",
        "total_tokens",
    }
)


class ProviderError(RuntimeError):
    """Base error for provider failures safe to expose to orchestration."""


class ProviderConfigurationError(ProviderError):
    """The provider was configured with unusable values."""


class ProviderTimeoutError(ProviderError):
    """The provider did not return before the caller's deadline."""


class ProviderRequestError(ProviderError):
    """Bedrock rejected or failed a request."""


class ProviderGuardrailError(ProviderError):
    """A configured Bedrock guardrail intervened."""


class StructuredOutputError(ProviderError):
    """The model response was not valid for the requested output contract."""


@dataclass(frozen=True)
class AgentMessage:
    """A trusted instruction or bounded conversation message."""

    role: Literal["system", "user", "assistant"]
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("Agent messages cannot be empty.")


@dataclass(frozen=True)
class TokenUsage:
    """Provider token counts, when the provider reports them."""

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


@dataclass(frozen=True)
class LLMResult(Generic[OutputT]):
    """Validated output plus trace-safe operational metadata."""

    output: OutputT
    model_id: str
    latency_ms: int
    usage: TokenUsage = field(default_factory=TokenUsage)
    attempt_usage: Tuple[TokenUsage, ...] = ()
    stop_reason: Optional[str] = None
    retries: int = 0
    guardrail_action: Literal["not_run", "not_intervened"] = "not_run"
    request_id: Optional[str] = None
    metadata: Mapping[str, TraceScalar] = field(
        default_factory=lambda: MappingProxyType({})
    )

    @property
    def input_tokens(self) -> Optional[int]:
        """Total input tokens across attempts for this role call."""

        return self.usage.input_tokens

    @property
    def output_tokens(self) -> Optional[int]:
        """Total output tokens across attempts for this role call."""

        return self.usage.output_tokens

    @property
    def total_tokens(self) -> Optional[int]:
        """Total tokens across attempts for this role call."""

        return self.usage.total_tokens


@dataclass(frozen=True)
class ProviderCall:
    """Metadata-only record of a fake-provider call."""

    role: str
    output_schema: str
    message_count: int
    metadata: Mapping[str, TraceScalar]


@runtime_checkable
class Provider(Protocol):
    """Contract shared by live and deterministic model providers."""

    def generate(
        self,
        *,
        role: str,
        messages: Sequence[AgentMessage],
        output_schema: Type[OutputT],
        timeout: Optional[float] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> LLMResult[OutputT]:
        """Generate and validate one role-specific structured response."""


@dataclass(frozen=True)
class BedrockConverseConfig:
    """Explicit Bedrock configuration.

    Authentication is intentionally absent. ``boto3`` uses its normal AWS
    credential chain, which permits workload IAM roles in deployment.
    """

    model_id: str
    region_name: str
    max_tokens: int = 1_200
    temperature: float = 0.0
    top_p: Optional[float] = None
    default_timeout_seconds: float = 30.0
    max_attempts: int = 3
    retry_base_seconds: float = 0.25
    guardrail_identifier: Optional[str] = None
    guardrail_version: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ProviderConfigurationError("A Bedrock model ID is required.")
        if not self.region_name.strip():
            raise ProviderConfigurationError("An AWS region is required.")
        if self.max_tokens < 1:
            raise ProviderConfigurationError("max_tokens must be positive.")
        if not 0.0 <= self.temperature <= 1.0:
            raise ProviderConfigurationError("temperature must be between 0 and 1.")
        if self.top_p is not None and not 0.0 < self.top_p <= 1.0:
            raise ProviderConfigurationError("top_p must be greater than 0 and at most 1.")
        if self.default_timeout_seconds <= 0:
            raise ProviderConfigurationError(
                "default_timeout_seconds must be positive."
            )
        if self.max_attempts < 1:
            raise ProviderConfigurationError("max_attempts must be positive.")
        if self.retry_base_seconds < 0:
            raise ProviderConfigurationError(
                "retry_base_seconds cannot be negative."
            )
        if bool(self.guardrail_identifier) != bool(self.guardrail_version):
            raise ProviderConfigurationError(
                "Guardrail identifier and version must be provided together."
            )


class BedrockConverseProvider:
    """Structured-output provider backed by Bedrock Runtime Converse."""

    def __init__(
        self,
        config: BedrockConverseConfig,
        *,
        client: Optional[Any] = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._client = client or self._create_client(config)
        self._sleep = sleeper
        self._monotonic = monotonic

    @staticmethod
    def _create_client(config: BedrockConverseConfig) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise ProviderConfigurationError(
                "boto3 is required for the Bedrock provider."
            ) from exc

        client_config = Config(
            connect_timeout=min(10.0, config.default_timeout_seconds),
            read_timeout=config.default_timeout_seconds,
            retries={"total_max_attempts": 1},
            user_agent_extra="TrialGuard-agent-runtime",
        )
        return boto3.client(
            "bedrock-runtime",
            region_name=config.region_name,
            config=client_config,
        )

    def generate(
        self,
        *,
        role: str,
        messages: Sequence[AgentMessage],
        output_schema: Type[OutputT],
        timeout: Optional[float] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> LLMResult[OutputT]:
        normalized_messages = _normalize_messages(messages)
        request = self._build_request(normalized_messages, output_schema)
        timeout_seconds = (
            self.config.default_timeout_seconds if timeout is None else timeout
        )
        if timeout_seconds <= 0:
            raise ProviderConfigurationError("timeout must be positive.")

        started_at = self._monotonic()
        deadline = started_at + timeout_seconds
        last_error: Optional[Exception] = None
        attempt_usage: List[TokenUsage] = []

        for attempt in range(self.config.max_attempts):
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise ProviderTimeoutError(
                    f"Bedrock role '{role}' exceeded its timeout."
                ) from last_error

            try:
                response = self._invoke_with_timeout(request, remaining)
                attempt_usage.append(_token_usage(response.get("usage")))
                stop_reason = _optional_string(response.get("stopReason"))
                if stop_reason == "guardrail_intervened":
                    raise ProviderGuardrailError(
                        f"Bedrock guardrail intervened for role '{role}'."
                    )
                raw_text = _response_text(response)
                parsed = parse_structured_output(raw_text, output_schema)
            except ProviderGuardrailError:
                raise
            except ProviderTimeoutError as exc:
                last_error = exc
                break
            except StructuredOutputError as exc:
                last_error = exc
                if attempt + 1 >= self.config.max_attempts:
                    break
                self._backoff(attempt, deadline)
                continue
            except Exception as exc:
                last_error = exc
                if not _is_retryable_error(exc):
                    code = _error_code(exc)
                    suffix = f" ({code})" if code else ""
                    raise ProviderRequestError(
                        f"Bedrock request failed for role '{role}'{suffix}."
                    ) from exc
                if attempt + 1 >= self.config.max_attempts:
                    break
                self._backoff(attempt, deadline)
                continue

            latency_ms = max(0, round((self._monotonic() - started_at) * 1_000))
            usage = _sum_token_usage(attempt_usage)
            return LLMResult(
                output=parsed,
                model_id=self.config.model_id,
                latency_ms=latency_ms,
                usage=usage,
                attempt_usage=tuple(attempt_usage),
                stop_reason=stop_reason,
                retries=attempt,
                guardrail_action=(
                    "not_intervened"
                    if self.config.guardrail_identifier
                    else "not_run"
                ),
                request_id=_request_id(response),
                metadata=_result_metadata(metadata, usage),
            )

        if isinstance(last_error, ProviderTimeoutError):
            raise ProviderTimeoutError(
                f"Bedrock role '{role}' exceeded its timeout."
            ) from last_error
        if isinstance(last_error, StructuredOutputError):
            raise StructuredOutputError(
                f"Bedrock returned invalid structured output for role '{role}' "
                f"after {self.config.max_attempts} attempt(s)."
            ) from last_error

        code = _error_code(last_error)
        suffix = f" ({code})" if code else ""
        raise ProviderRequestError(
            f"Bedrock request failed for role '{role}' after "
            f"{self.config.max_attempts} attempt(s){suffix}."
        ) from last_error

    def _build_request(
        self,
        messages: Sequence[AgentMessage],
        output_schema: Type[OutputT],
    ) -> Dict[str, Any]:
        system_texts = [
            message.content for message in messages if message.role == "system"
        ]
        schema = _model_json_schema(output_schema)
        system_texts.append(
            "Return exactly one JSON value matching this JSON Schema. "
            "Do not include markdown, commentary, or hidden reasoning:\n"
            + json.dumps(schema, separators=(",", ":"), sort_keys=True)
        )
        conversation = [
            {"role": message.role, "content": [{"text": message.content}]}
            for message in messages
            if message.role != "system"
        ]
        if not conversation:
            raise ProviderConfigurationError(
                "At least one user or assistant message is required."
            )

        inference_config: Dict[str, Any] = {
            "maxTokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        if self.config.top_p is not None:
            inference_config["topP"] = self.config.top_p

        request: Dict[str, Any] = {
            "modelId": self.config.model_id,
            "system": [{"text": text} for text in system_texts],
            "messages": conversation,
            "inferenceConfig": inference_config,
        }
        if self.config.guardrail_identifier and self.config.guardrail_version:
            request["guardrailConfig"] = {
                "guardrailIdentifier": self.config.guardrail_identifier,
                "guardrailVersion": self.config.guardrail_version,
                "trace": "enabled",
            }
        return request

    def _invoke_with_timeout(
        self, request: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="trialguard-bedrock"
        )
        future = executor.submit(self._client.converse, **dict(request))
        try:
            response = future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise ProviderTimeoutError("Bedrock Converse call timed out.") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if not isinstance(response, Mapping):
            raise ProviderRequestError("Bedrock returned an invalid response envelope.")
        return response

    def _backoff(self, attempt: int, deadline: float) -> None:
        delay = self.config.retry_base_seconds * (2**attempt)
        if delay <= 0:
            return
        remaining = deadline - self._monotonic()
        if remaining <= delay:
            raise ProviderTimeoutError("Bedrock retry budget exhausted.")
        self._sleep(delay)


class FakeProvider:
    """Deterministic provider for tests and checked offline demonstrations."""

    model_id = "trialguard.fake"

    def __init__(
        self,
        responses: Union[
            Mapping[str, Iterable[Union[str, Mapping[str, Any], BaseModel, Exception]]],
            Iterable[Union[str, Mapping[str, Any], BaseModel, Exception]],
        ],
    ) -> None:
        if isinstance(responses, Mapping):
            self._responses = {
                role: list(role_responses)
                for role, role_responses in responses.items()
            }
            self._default_responses: List[
                Union[str, Mapping[str, Any], BaseModel, Exception]
            ] = []
        else:
            self._responses = {}
            self._default_responses = list(responses)
        self.calls: List[ProviderCall] = []

    def generate(
        self,
        *,
        role: str,
        messages: Sequence[AgentMessage],
        output_schema: Type[OutputT],
        timeout: Optional[float] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> LLMResult[OutputT]:
        normalized_messages = _normalize_messages(messages)
        if timeout is not None and timeout <= 0:
            raise ProviderTimeoutError(f"Fake role '{role}' exceeded its timeout.")

        safe_metadata = _safe_metadata(metadata)
        self.calls.append(
            ProviderCall(
                role=role,
                output_schema=getattr(output_schema, "__name__", str(output_schema)),
                message_count=len(normalized_messages),
                metadata=safe_metadata,
            )
        )
        queue = self._responses.get(role, self._default_responses)
        if not queue:
            raise ProviderRequestError(
                f"No fake response is configured for role '{role}'."
            )
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, str):
            parsed = parse_structured_output(response, output_schema)
        else:
            parsed = _validate_model(output_schema, response)
        return LLMResult(
            output=parsed,
            model_id=self.model_id,
            latency_ms=0,
            attempt_usage=(TokenUsage(),),
            stop_reason="end_turn",
            retries=0,
            guardrail_action="not_run",
            metadata=safe_metadata,
        )


def parse_structured_output(
    raw_text: str, output_schema: Type[OutputT]
) -> OutputT:
    """Parse JSON and validate it with a Pydantic-compatible model class."""

    if not isinstance(raw_text, str) or not raw_text.strip():
        raise StructuredOutputError("The model returned no structured output.")
    match = _JSON_FENCE.match(raw_text)
    payload = match.group("payload") if match else raw_text.strip()
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise StructuredOutputError("The model response was not valid JSON.") from exc
    return _validate_model(output_schema, decoded)


def _validate_model(output_schema: Type[OutputT], value: Any) -> OutputT:
    try:
        if isinstance(value, output_schema):
            return value
        if hasattr(output_schema, "model_validate"):
            return output_schema.model_validate(value)
        if hasattr(output_schema, "parse_obj"):  # Pydantic v1 compatibility
            return output_schema.parse_obj(value)
    except Exception as exc:
        raise StructuredOutputError(
            "The model response did not match the requested schema."
        ) from exc
    raise ProviderConfigurationError(
        "output_schema must be a Pydantic-compatible model class."
    )


def _model_json_schema(output_schema: Type[OutputT]) -> Mapping[str, Any]:
    try:
        if hasattr(output_schema, "model_json_schema"):
            return output_schema.model_json_schema()
        if hasattr(output_schema, "schema"):  # Pydantic v1 compatibility
            return output_schema.schema()
    except Exception as exc:
        raise ProviderConfigurationError(
            "Could not build the requested output JSON Schema."
        ) from exc
    raise ProviderConfigurationError(
        "output_schema must provide a Pydantic-compatible JSON Schema."
    )


def _normalize_messages(messages: Sequence[AgentMessage]) -> Tuple[AgentMessage, ...]:
    normalized = tuple(messages)
    if not normalized:
        raise ProviderConfigurationError("At least one message is required.")
    if any(not isinstance(message, AgentMessage) for message in normalized):
        raise ProviderConfigurationError("All messages must be AgentMessage values.")
    return normalized


def _response_text(response: Mapping[str, Any]) -> str:
    try:
        blocks = response["output"]["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise StructuredOutputError(
            "Bedrock response did not contain a message."
        ) from exc
    texts = [
        block.get("text")
        for block in blocks
        if isinstance(block, Mapping) and isinstance(block.get("text"), str)
    ]
    text = "".join(texts).strip()
    if not text:
        raise StructuredOutputError(
            "Bedrock response did not contain structured text."
        )
    return text


def _token_usage(value: Any) -> TokenUsage:
    if not isinstance(value, Mapping):
        return TokenUsage()
    input_tokens = _optional_int(value.get("inputTokens"))
    output_tokens = _optional_int(value.get("outputTokens"))
    total_tokens = _optional_int(value.get("totalTokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _sum_token_usage(attempts: Sequence[TokenUsage]) -> TokenUsage:
    def total(values: Iterable[Optional[int]]) -> Optional[int]:
        known = [value for value in values if value is not None]
        return sum(known) if known else None

    return TokenUsage(
        input_tokens=total(usage.input_tokens for usage in attempts),
        output_tokens=total(usage.output_tokens for usage in attempts),
        total_tokens=total(usage.total_tokens for usage in attempts),
    )


def _request_id(response: Mapping[str, Any]) -> Optional[str]:
    metadata = response.get("ResponseMetadata")
    if not isinstance(metadata, Mapping):
        return None
    return _optional_string(metadata.get("RequestId"))


def _safe_metadata(
    metadata: Optional[Mapping[str, Any]],
) -> Mapping[str, TraceScalar]:
    if not metadata:
        return MappingProxyType({})
    safe: Dict[str, TraceScalar] = {}
    for key, value in metadata.items():
        if key not in _TRACE_METADATA_KEYS:
            continue
        if value is None or isinstance(value, (bool, int, float)):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = value[:128]
    return MappingProxyType(safe)


def _result_metadata(
    metadata: Optional[Mapping[str, Any]], usage: TokenUsage
) -> Mapping[str, TraceScalar]:
    safe = dict(_safe_metadata(metadata))
    if usage.input_tokens is not None:
        safe["input_tokens"] = usage.input_tokens
    if usage.output_tokens is not None:
        safe["output_tokens"] = usage.output_tokens
    if usage.total_tokens is not None:
        safe["total_tokens"] = usage.total_tokens
    return MappingProxyType(safe)


def _optional_string(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _optional_int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _error_code(exc: Optional[Exception]) -> Optional[str]:
    if exc is None:
        return None
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return None
    error = response.get("Error")
    if not isinstance(error, Mapping):
        return None
    return _optional_string(error.get("Code"))


def _is_retryable_error(exc: Exception) -> bool:
    return _error_code(exc) in _RETRYABLE_ERROR_CODES
