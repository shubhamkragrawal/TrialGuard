from __future__ import annotations

import json
from datetime import datetime, timezone

from app.observability import (
    CloudWatchLogsPublisher,
    CloudWatchMetricsPublisher,
    attach_xray_metadata,
    build_operational_event,
    cloudwatch_metric_data,
    emit_json_event,
    new_xray_trace_id,
    sanitize_operational_metadata,
    xray_trace_metadata,
)


class RecordingLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


class RaisingLogger:
    def info(self, message: str) -> None:
        raise RuntimeError(f"logger unavailable: {message}")


class CloudWatchClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[dict] = []

    def put_metric_data(self, **request) -> None:
        if self.fail:
            raise RuntimeError("CloudWatch unavailable")
        self.requests.append(request)


class CloudWatchLogsClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.groups: list[dict] = []
        self.streams: list[dict] = []
        self.events: list[dict] = []

    def create_log_group(self, **request) -> None:
        if self.fail:
            raise RuntimeError("CloudWatch Logs unavailable")
        self.groups.append(request)

    def create_log_stream(self, **request) -> None:
        self.streams.append(request)

    def put_log_events(self, **request) -> None:
        self.events.append(request)


class XRayRecorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.annotations: dict[str, object] = {}
        self.metadata: list[tuple[str, object, str]] = []

    def put_annotation(self, key: str, value: object) -> None:
        if self.fail:
            raise RuntimeError("X-Ray unavailable")
        self.annotations[key] = value

    def put_metadata(self, key: str, value: object, namespace: str) -> None:
        if self.fail:
            raise RuntimeError("X-Ray unavailable")
        self.metadata.append((key, value, namespace))


def test_builds_complete_structured_operational_event() -> None:
    observed_at = datetime(2026, 9, 26, 12, 30, tzinfo=timezone.utc)
    trace_id = new_xray_trace_id(epoch_seconds=1_700_000_000)

    event = build_operational_event(
        run_id="run-123",
        trace_id=trace_id,
        stage="challenge_agent",
        status="complete",
        duration_ms=432,
        release_state="full",
        model_calls=3,
        input_tokens=120,
        output_tokens=30,
        estimated_cost_usd=0.0012,
        occurred_at=observed_at,
    )

    assert event == {
        "event_type": "trialguard.operation",
        "timestamp": "2026-09-26T12:30:00Z",
        "service": "trialguard",
        "run_id": "run-123",
        "trace_id": trace_id,
        "stage": "challenge_agent",
        "status": "complete",
        "duration_ms": 432,
        "release_state": "full",
        "model_calls": 3,
        "input_tokens": 120,
        "output_tokens": 30,
        "total_tokens": 150,
        "estimated_cost_usd": 0.0012,
        "error_count": 0,
    }


def test_drops_secret_and_raw_content_fields_from_every_output() -> None:
    secret_values = {
        "prompt": "PROMPT-SHOULD-NOT-APPEAR",
        "raw_prompt": "RAW-PROMPT-SHOULD-NOT-APPEAR",
        "response": "MODEL-RESPONSE-SHOULD-NOT-APPEAR",
        "raw_response": "RAW-RESPONSE-SHOULD-NOT-APPEAR",
        "request_headers": {"Authorization": "Bearer VERY-SECRET-TOKEN"},
        "credentials": {
            "aws_access_key_id": "AKIAEXAMPLE",
            "aws_secret_access_key": "AWS-SECRET-SHOULD-NOT-APPEAR",
        },
        "chat_text": "PRIVATE-CHAT-SHOULD-NOT-APPEAR",
        "messages": ["PRIVATE-MESSAGE-SHOULD-NOT-APPEAR"],
    }
    event = build_operational_event(
        run_id="run-safe",
        stage="evidence_agent",
        status="failed",
        error=RuntimeError("exception contains AWS-SECRET-SHOULD-NOT-APPEAR"),
        metadata=secret_values,
    )
    outputs = {
        "event": event,
        "metrics": cloudwatch_metric_data(event),
        "trace": xray_trace_metadata(event),
    }
    serialized = json.dumps(outputs)

    for key, value in secret_values.items():
        assert key not in serialized
        if isinstance(value, str):
            assert value not in serialized
    assert "VERY-SECRET-TOKEN" not in serialized
    assert "AKIAEXAMPLE" not in serialized
    assert "AWS-SECRET-SHOULD-NOT-APPEAR" not in serialized
    assert "PRIVATE-MESSAGE-SHOULD-NOT-APPEAR" not in serialized
    assert event["error_type"] == "RuntimeError"
    assert event["error_count"] == 1


def test_sanitizer_rejects_complex_and_unbounded_values() -> None:
    safe = sanitize_operational_metadata(
        {
            "run_id": "run-ok",
            "stage": "stage with raw free text",
            "status": {"secret": "value"},
            "model_calls": -1,
            "estimated_cost_usd": float("inf"),
            "unknown": "drop-me",
        }
    )

    assert safe == {"run_id": "run-ok"}


def test_json_event_is_structured_sanitized_and_fail_safe() -> None:
    logger = RecordingLogger()
    event = {
        "run_id": "run-1",
        "stage": "release_gate",
        "status": "blocked",
        "prompt": "do not log this",
    }

    assert emit_json_event(event, logger=logger) is True
    assert json.loads(logger.messages[0]) == {
        "run_id": "run-1",
        "stage": "release_gate",
        "status": "blocked",
    }
    assert emit_json_event(event, logger=RaisingLogger()) is False


def test_cloudwatch_metrics_use_low_cardinality_dimensions() -> None:
    event = build_operational_event(
        run_id="unique-run-id",
        stage="coordinator_agent",
        status="complete",
        duration_ms=99,
        release_state="full",
        model_calls=1,
        input_tokens=10,
        output_tokens=5,
        estimated_cost_usd=0.00001,
    )
    metrics = cloudwatch_metric_data(event)

    assert {metric["MetricName"] for metric in metrics} == {
        "DurationMs",
        "ModelCalls",
        "InputTokens",
        "OutputTokens",
        "TotalTokens",
        "EstimatedCostUsd",
        "ErrorCount",
    }
    serialized = json.dumps(metrics)
    assert "unique-run-id" not in serialized
    assert "RunId" not in serialized
    assert all(metric["Dimensions"][1]["Value"] == "coordinator_agent" for metric in metrics)


def test_cloudwatch_publisher_is_optional_and_fail_safe() -> None:
    event = build_operational_event(
        run_id="run-1",
        stage="registry_retrieval",
        status="complete",
    )
    client = CloudWatchClient()

    assert CloudWatchMetricsPublisher(client).publish(event) is True
    assert client.requests[0]["Namespace"] == "TrialGuard"
    assert CloudWatchMetricsPublisher(enabled=False).publish(event) is False
    assert CloudWatchMetricsPublisher(CloudWatchClient(fail=True)).publish(event) is False


def test_cloudwatch_logs_publisher_emits_sanitized_events() -> None:
    event = build_operational_event(
        run_id="run-logs",
        stage="report_chat",
        status="answered",
        metadata={"chat_text": "must never appear"},
    )
    client = CloudWatchLogsClient()

    assert CloudWatchLogsPublisher(client).publish(event) is True
    message = json.loads(client.events[0]["logEvents"][0]["message"])
    assert message["run_id"] == "run-logs"
    assert "chat_text" not in message
    assert CloudWatchLogsPublisher(enabled=False).publish(event) is False
    assert CloudWatchLogsPublisher(CloudWatchLogsClient(fail=True)).publish(event) is False


def test_xray_metadata_is_allowlisted_and_optional() -> None:
    event = build_operational_event(
        run_id="run-2",
        stage="challenge_agent",
        status="failed",
        release_state="blocked",
        error_code="guardrail_intervened",
        metadata={"chat_text": "never trace this"},
    )
    recorder = XRayRecorder()

    assert attach_xray_metadata(recorder, event) is True
    assert recorder.annotations == {
        "run_id": "run-2",
        "stage": "challenge_agent",
        "status": "failed",
        "release_state": "blocked",
        "model_calls": 0,
        "error_count": 1,
    }
    assert recorder.metadata[0][0] == "operational_event"
    assert recorder.metadata[0][2] == "trialguard"
    assert "chat_text" not in json.dumps(recorder.metadata)
    assert attach_xray_metadata(None, event) is False
    assert attach_xray_metadata(XRayRecorder(fail=True), event) is False
