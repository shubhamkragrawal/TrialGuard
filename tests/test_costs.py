from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.costs import summarize_usage


@dataclass
class Result:
    input_tokens: int | None
    output_tokens: int | None


def test_usage_is_measured_without_unverified_pricing() -> None:
    usage = summarize_usage([Result(100, 20), Result(200, 30)], Settings())
    assert usage.model_calls == 2
    assert usage.input_tokens == 300
    assert usage.output_tokens == 50
    assert usage.estimated_cost_usd is None


def test_configured_pricing_produces_estimate() -> None:
    settings = Settings(
        input_usd_per_million_tokens=1.0,
        output_usd_per_million_tokens=2.0,
    )
    usage = summarize_usage([Result(1_000_000, 500_000)], settings)
    assert usage.estimated_cost_usd == 2.0
