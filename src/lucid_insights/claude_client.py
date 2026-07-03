"""Thin Anthropic SDK wrapper for remediation generation."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from anthropic import Anthropic

from lucid_insights.models import RemediationInsight, ViolationGroup
from lucid_insights.prompts import SYSTEM_PROMPT, build_user_prompt

# Default: Claude Sonnet 5 — best balance of speed and quality for remediation.
# Model IDs from https://docs.claude.com/en/docs/about-claude/models/overview
DEFAULT_MODEL = "claude-sonnet-5"

# Approximate pricing per million tokens (USD). Used only for pre-flight estimates.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}

# Rough token estimates per group for cost gating (not billed usage).
ESTIMATED_INPUT_TOKENS_PER_GROUP = 700
ESTIMATED_OUTPUT_TOKENS_PER_GROUP = 350

DEFAULT_COST_THRESHOLD = 10


@dataclass(frozen=True)
class CostEstimate:
    """Pre-flight token and cost estimate for a batch of groups."""

    group_count: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    model: str

    def exceeds_threshold(self, threshold: int = DEFAULT_COST_THRESHOLD) -> bool:
        return self.group_count > threshold


def estimate_cost(group_count: int, model: str = DEFAULT_MODEL) -> CostEstimate:
    """Estimate tokens and USD cost before calling the API."""
    input_tokens = group_count * ESTIMATED_INPUT_TOKENS_PER_GROUP
    output_tokens = group_count * ESTIMATED_OUTPUT_TOKENS_PER_GROUP
    input_price, output_price = _pricing_for_model(model)
    cost = (input_tokens / 1_000_000) * input_price + (
        output_tokens / 1_000_000
    ) * output_price
    return CostEstimate(
        group_count=group_count,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_cost_usd=cost,
        model=model,
    )


def _pricing_for_model(model: str) -> tuple[float, float]:
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Fall back to Sonnet-class pricing for unknown aliases.
    for known, prices in MODEL_PRICING.items():
        if known in model or model in known:
            return prices
    return MODEL_PRICING[DEFAULT_MODEL]


def _require_api_key() -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export your Anthropic API key before "
            "running lucid-insights report."
        )
    return api_key


class ClaudeClient:
    """Generate RemediationInsight objects via the Anthropic Messages API."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        client: Anthropic | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = client or Anthropic(api_key=_require_api_key())

    def generate_insight(self, group: ViolationGroup) -> RemediationInsight:
        """Call Claude once for a violation group and parse the JSON response."""
        user_prompt = build_user_prompt(
            rule_id=group.rule_id,
            impact=group.impact.value,
            wcag_criteria=group.wcag_criteria,
            description=group.description,
            help_url=group.help_url,
            count=group.count,
            selectors=group.selectors,
            html_snippets=group.html_snippets,
        )

        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        text = _extract_text(response)
        return _parse_insight(text)

    def enrich_groups(self, groups: list[ViolationGroup]) -> list[ViolationGroup]:
        """Attach insights to each group, returning updated copies."""
        enriched: list[ViolationGroup] = []
        for group in groups:
            insight = self.generate_insight(group)
            enriched.append(group.model_copy(update={"insight": insight}))
        return enriched


def _extract_text(response: object) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", []):
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    if not parts:
        raise ValueError("Claude response contained no text content")
    return "\n".join(parts)


def _parse_insight(text: str) -> RemediationInsight:
    """Parse model JSON, tolerating accidental markdown fences."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse Claude JSON response: {exc}") from exc

    return RemediationInsight.model_validate(data)
