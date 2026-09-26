"""Metadata-only operational observability for TrialGuard.

This module deliberately accepts and emits only a small allowlist of
operational fields. Prompts, model responses, request headers, credentials,
chat text, registry payloads, and exception messages are never retained.

AWS integrations are optional and fail closed: an unavailable CloudWatch
client or X-Ray recorder must never affect an assessment.
"""

from __future__ import annotations

import json
import logging
import math
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

_LOGGER = logging.getLogger("trialguard.observability")
_LOGGER.setLevel(logging.INFO)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_XRAY_TRACE_ID = re.compile(r"^1-[0-9a-f]{8}-[0-9a-f]{24}$")

# Strictly allowlisted. Anything not listed here is dropped, including prompt,
# response, request headers, credentials, authorization values, and chat text.
SAFE_OPERATIONAL_FIELDS = frozenset(
    {
        "event_type",
        "timestamp",
        "service",
        "run_id",
        "trace_id",
        "stage",
        "status",
        "duration_ms",
        "release_state",
        "model_calls",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "estimated_cost_usd",
        "error_count",
        "error_type",
        "error_code",
    }
)

_IDENTIFIER_FIELDS = frozenset(
    {
        "event_type",
        "service",
        "run_id",
        "stage",
        "status",
        "release_state",
        "error_type",
        "error_code",
    }
)
_INTEGER_FIELDS = frozenset(
    {
        "duration_ms",
        "model_calls",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "error_count",
    }
)


def _safe_identifier(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate if _IDENTIFIER.fullmatch(candidate) else None


def _nonnegative_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        candidate = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return candidate if candidate >= 0 else None


def _nonnegative_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        candidate = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return candidate if candidate >= 0 and math.isfinite(candidate) else None


def _safe_timestamp(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        observed = value
    elif isinstance(value, str):
        try:
            observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return observed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize_operational_metadata(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return only validated, low-risk operational metadata.

    This is an allowlist, not a redaction pass. Unknown keys and complex values
    are dropped wholesale so newly introduced payload fields cannot
    accidentally reach logs or telemetry.
    """

    safe: dict[str, Any] = {}
    for field in SAFE_OPERATIONAL_FIELDS:
        if field not in values:
            continue
        value = values[field]
        if field in _IDENTIFIER_FIELDS:
            sanitized = _safe_identifier(value)
        elif field in _INTEGER_FIELDS:
            sanitized = _nonnegative_int(value)
        elif field == "estimated_cost_usd":
            sanitized = _nonnegative_float(value)
        elif field == "timestamp":
            sanitized = _safe_timestamp(value)
        elif field == "trace_id":
            sanitized = (
                value
                if isinstance(value, str) and _XRAY_TRACE_ID.fullmatch(value)
                else None
            )
        else:  # pragma: no cover - every allowlisted field is classified above
            sanitized = None

        if sanitized is not None:
            safe[field] = sanitized
    return safe


def new_xray_trace_id(*, epoch_seconds: Optional[int] = None) -> str:
    """Create an AWS X-Ray-compatible trace identifier without an AWS call."""

    observed_epoch = int(time.time() if epoch_seconds is None else epoch_seconds)
    observed_epoch = max(0, min(observed_epoch, 0xFFFFFFFF))
    return f"1-{observed_epoch:08x}-{secrets.token_hex(12)}"


def build_operational_event(
    *,
    run_id: str,
    stage: str,
    status: str,
    duration_ms: int = 0,
    release_state: Optional[str] = None,
    model_calls: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: Optional[int] = None,
    estimated_cost_usd: Optional[float] = None,
    error: Optional[BaseException] = None,
    error_code: Optional[str] = None,
    trace_id: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build one structured event containing metadata only.

    ``metadata`` exists for ergonomic integration with callers, but it passes
    through the same strict allowlist. Explicit arguments take precedence.
    Exception messages are intentionally ignored because they may contain raw
    provider content, URLs, headers, or credentials.
    """

    raw: dict[str, Any] = dict(metadata or {})
    calculated_total = (
        input_tokens + output_tokens if total_tokens is None else total_tokens
    )
    raw.update(
        {
            "event_type": "trialguard.operation",
            "timestamp": occurred_at or datetime.now(timezone.utc),
            "service": "trialguard",
            "run_id": run_id,
            "stage": stage,
            "status": status,
            "duration_ms": duration_ms,
            "model_calls": model_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": calculated_total,
            "error_count": 1 if error is not None or error_code else 0,
        }
    )
    if release_state is not None:
        raw["release_state"] = release_state
    if estimated_cost_usd is not None:
        raw["estimated_cost_usd"] = estimated_cost_usd
    if trace_id is not None:
        raw["trace_id"] = trace_id
    if error is not None:
        raw["error_type"] = type(error).__name__
    if error_code is not None:
        raw["error_code"] = error_code

    return sanitize_operational_metadata(raw)


def emit_json_event(
    event: Mapping[str, Any],
    *,
    logger: Optional[Any] = None,
) -> bool:
    """Write one sanitized compact JSON event; return false on logging failure."""

    try:
        safe_event = sanitize_operational_metadata(event)
        payload = json.dumps(
            safe_event,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        (logger or _LOGGER).info(payload)
        return True
    except Exception:  # Telemetry must not affect the application.
        return False


def cloudwatch_metric_data(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Translate a safe event to low-cardinality CloudWatch custom metrics.

    Run IDs and trace IDs remain in structured logs/traces and are deliberately
    excluded from metric dimensions to avoid unbounded cardinality.
    """

    safe = sanitize_operational_metadata(event)
    dimensions = [
        {"Name": "Service", "Value": safe.get("service", "trialguard")},
        {"Name": "Stage", "Value": safe.get("stage", "unknown")},
        {"Name": "Status", "Value": safe.get("status", "unknown")},
    ]
    if "release_state" in safe:
        dimensions.append(
            {"Name": "ReleaseState", "Value": safe["release_state"]}
        )

    specifications = (
        ("duration_ms", "DurationMs", "Milliseconds"),
        ("model_calls", "ModelCalls", "Count"),
        ("input_tokens", "InputTokens", "Count"),
        ("output_tokens", "OutputTokens", "Count"),
        ("total_tokens", "TotalTokens", "Count"),
        ("estimated_cost_usd", "EstimatedCostUsd", "None"),
        ("error_count", "ErrorCount", "Count"),
    )
    return [
        {
            "MetricName": metric_name,
            "Dimensions": dimensions,
            "Unit": unit,
            "Value": safe[field],
        }
        for field, metric_name, unit in specifications
        if field in safe
    ]


class CloudWatchMetricsPublisher:
    """Optional fail-safe publisher for TrialGuard custom metrics."""

    def __init__(
        self,
        client: Optional[Any] = None,
        *,
        namespace: str = "TrialGuard",
        enabled: bool = True,
    ) -> None:
        self._client = client
        self.namespace = namespace
        self.enabled = enabled

    @classmethod
    def from_boto3(
        cls,
        *,
        enabled: bool = False,
        region_name: str = "us-east-1",
        namespace: str = "TrialGuard",
    ) -> "CloudWatchMetricsPublisher":
        """Create a publisher lazily; degrade to disabled if boto3/AWS fails."""

        if not enabled:
            return cls(namespace=namespace, enabled=False)
        try:
            import boto3

            client = boto3.client("cloudwatch", region_name=region_name)
            return cls(client, namespace=namespace)
        except Exception:
            return cls(namespace=namespace, enabled=False)

    def publish(self, event: Mapping[str, Any]) -> bool:
        """Publish custom metrics and swallow all telemetry-side failures."""

        if not self.enabled or self._client is None:
            return False
        try:
            metric_data = cloudwatch_metric_data(event)
            if not metric_data:
                return False
            self._client.put_metric_data(
                Namespace=self.namespace,
                MetricData=metric_data,
            )
            return True
        except Exception:
            return False


class CloudWatchLogsPublisher:
    """Optional metadata-only CloudWatch Logs publisher."""

    def __init__(
        self,
        client: Optional[Any] = None,
        *,
        log_group: str = "/trialguard/demo",
        log_stream: str = "application",
        enabled: bool = True,
    ) -> None:
        self._client = client
        self.log_group = log_group
        self.log_stream = log_stream
        self.enabled = enabled
        self._ready = False

    @classmethod
    def from_boto3(
        cls,
        *,
        enabled: bool = False,
        region_name: str = "us-east-1",
        log_group: str = "/trialguard/demo",
        log_stream: str = "application",
    ) -> "CloudWatchLogsPublisher":
        if not enabled:
            return cls(
                log_group=log_group,
                log_stream=log_stream,
                enabled=False,
            )
        try:
            import boto3

            return cls(
                boto3.client("logs", region_name=region_name),
                log_group=log_group,
                log_stream=log_stream,
            )
        except Exception:
            return cls(
                log_group=log_group,
                log_stream=log_stream,
                enabled=False,
            )

    def publish(self, event: Mapping[str, Any]) -> bool:
        if not self.enabled or self._client is None:
            return False
        try:
            if not self._ready:
                self._ensure_destination()
            safe_event = sanitize_operational_metadata(event)
            self._client.put_log_events(
                logGroupName=self.log_group,
                logStreamName=self.log_stream,
                logEvents=[
                    {
                        "timestamp": int(time.time() * 1_000),
                        "message": json.dumps(
                            safe_event,
                            ensure_ascii=True,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    }
                ],
            )
            return True
        except Exception:
            return False

    def _ensure_destination(self) -> None:
        try:
            self._client.create_log_group(logGroupName=self.log_group)
        except Exception as exc:
            if "ResourceAlreadyExists" not in type(exc).__name__ and (
                "ResourceAlreadyExists" not in str(exc)
            ):
                raise
        try:
            self._client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.log_stream,
            )
        except Exception as exc:
            if "ResourceAlreadyExists" not in type(exc).__name__ and (
                "ResourceAlreadyExists" not in str(exc)
            ):
                raise
        self._ready = True


def xray_trace_metadata(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return allowlisted annotations and metadata suitable for AWS X-Ray."""

    safe = sanitize_operational_metadata(event)
    annotation_fields = (
        "run_id",
        "stage",
        "status",
        "release_state",
        "model_calls",
        "error_count",
    )
    annotations = {
        key: safe[key]
        for key in annotation_fields
        if isinstance(safe.get(key), (str, int, float, bool))
    }
    return {
        "annotations": annotations,
        "metadata": {"trialguard": safe},
    }


def attach_xray_metadata(
    recorder: Optional[Any],
    event: Mapping[str, Any],
) -> bool:
    """Attach safe values to an X-Ray-compatible recorder, if one is present."""

    if recorder is None:
        return False
    try:
        trace = xray_trace_metadata(event)
        for key, value in trace["annotations"].items():
            recorder.put_annotation(key, value)
        recorder.put_metadata(
            "operational_event",
            trace["metadata"]["trialguard"],
            namespace="trialguard",
        )
        return True
    except Exception:
        return False
