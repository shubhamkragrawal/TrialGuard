"""Environment-driven configuration without credential handling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_float(value: str) -> float | None:
    return float(value) if value.strip() else None


@dataclass(frozen=True)
class Settings:
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_challenge_model_id: str = ""
    bedrock_guardrail_id: str = ""
    bedrock_guardrail_version: str = ""
    bedrock_native_json_schema: bool = True
    live_bedrock_enabled: bool = False
    cloudwatch_metrics_enabled: bool = False
    cloudwatch_logs_enabled: bool = False
    registry_base_url: str = "https://clinicaltrials.gov"
    report_timeout_seconds: int = 90
    model_call_limit: int = 5
    daily_live_run_limit: int = 15
    rate_limit_requests_per_minute: int = 6
    cache_dir: Path = Path("data/cache")
    runs_dir: Path = Path("runs")
    input_usd_per_million_tokens: float | None = None
    output_usd_per_million_tokens: float | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            aws_region=os.getenv("TRIALGUARD_AWS_REGION", cls.aws_region),
            bedrock_model_id=os.getenv(
                "TRIALGUARD_BEDROCK_MODEL_ID", cls.bedrock_model_id
            ),
            bedrock_challenge_model_id=os.getenv(
                "TRIALGUARD_BEDROCK_CHALLENGE_MODEL_ID",
                cls.bedrock_challenge_model_id,
            ),
            bedrock_guardrail_id=os.getenv(
                "TRIALGUARD_BEDROCK_GUARDRAIL_ID", cls.bedrock_guardrail_id
            ),
            bedrock_guardrail_version=os.getenv(
                "TRIALGUARD_BEDROCK_GUARDRAIL_VERSION",
                cls.bedrock_guardrail_version,
            ),
            bedrock_native_json_schema=_as_bool(
                os.getenv(
                    "TRIALGUARD_BEDROCK_NATIVE_JSON_SCHEMA",
                    str(cls.bedrock_native_json_schema),
                )
            ),
            live_bedrock_enabled=_as_bool(
                os.getenv("TRIALGUARD_LIVE_BEDROCK_ENABLED", "false")
            ),
            cloudwatch_metrics_enabled=_as_bool(
                os.getenv("TRIALGUARD_CLOUDWATCH_METRICS_ENABLED", "false")
            ),
            cloudwatch_logs_enabled=_as_bool(
                os.getenv("TRIALGUARD_CLOUDWATCH_LOGS_ENABLED", "false")
            ),
            registry_base_url=os.getenv(
                "TRIALGUARD_REGISTRY_BASE_URL", cls.registry_base_url
            ).rstrip("/"),
            report_timeout_seconds=int(
                os.getenv(
                    "TRIALGUARD_REPORT_TIMEOUT_SECONDS",
                    str(cls.report_timeout_seconds),
                )
            ),
            model_call_limit=int(
                os.getenv("TRIALGUARD_MODEL_CALL_LIMIT", str(cls.model_call_limit))
            ),
            daily_live_run_limit=int(
                os.getenv(
                    "TRIALGUARD_DAILY_LIVE_RUN_LIMIT",
                    str(cls.daily_live_run_limit),
                )
            ),
            rate_limit_requests_per_minute=int(
                os.getenv(
                    "TRIALGUARD_RATE_LIMIT_REQUESTS_PER_MINUTE",
                    str(cls.rate_limit_requests_per_minute),
                )
            ),
            cache_dir=Path(
                os.getenv("TRIALGUARD_CACHE_DIR", str(cls.cache_dir))
            ),
            runs_dir=Path(os.getenv("TRIALGUARD_RUNS_DIR", str(cls.runs_dir))),
            input_usd_per_million_tokens=_optional_float(
                os.getenv("TRIALGUARD_INPUT_USD_PER_MILLION_TOKENS", "")
            ),
            output_usd_per_million_tokens=_optional_float(
                os.getenv("TRIALGUARD_OUTPUT_USD_PER_MILLION_TOKENS", "")
            ),
        )

    @property
    def challenge_model_id(self) -> str:
        return self.bedrock_challenge_model_id or self.bedrock_model_id

    @property
    def bedrock_ready(self) -> bool:
        return self.live_bedrock_enabled and bool(self.bedrock_model_id)
