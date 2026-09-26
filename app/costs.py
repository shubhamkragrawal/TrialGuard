"""Measured token usage and configurable Bedrock cost estimation."""

from __future__ import annotations

from typing import Any, Iterable

from app.config import Settings
from app.schemas import UsageSummary


def summarize_usage(
    results: Iterable[Any],
    settings: Settings,
) -> UsageSummary:
    completed = list(results)
    input_tokens = sum(int(result.input_tokens or 0) for result in completed)
    output_tokens = sum(int(result.output_tokens or 0) for result in completed)
    input_rate = settings.input_usd_per_million_tokens
    output_rate = settings.output_usd_per_million_tokens

    if input_rate is None or output_rate is None:
        return UsageSummary(
            model_calls=len(completed),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pricing_basis=(
                "Measured token counts. Configure current per-million-token "
                "rates to estimate cost."
            ),
        )

    estimate = (
        input_tokens * input_rate / 1_000_000
        + output_tokens * output_rate / 1_000_000
    )
    return UsageSummary(
        model_calls=len(completed),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=round(estimate, 6),
        pricing_basis=(
            f"Configured rates: ${input_rate:g}/M input tokens and "
            f"${output_rate:g}/M output tokens."
        ),
    )
