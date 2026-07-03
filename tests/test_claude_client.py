"""Tests for Claude client — all Anthropic calls are mocked."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from lucid_insights.claude_client import (
    DEFAULT_MODEL,
    ClaudeClient,
    estimate_cost,
)
from lucid_insights.models import Impact, RemediationInsight, ViolationGroup
from lucid_insights.prompts import SYSTEM_PROMPT, build_user_prompt


def _mock_response(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(text=json.dumps(payload))]
    )


@pytest.fixture
def sample_group() -> ViolationGroup:
    return ViolationGroup(
        rule_id="image-alt",
        impact=Impact.CRITICAL,
        wcag_criteria=["1.1.1"],
        description="Images must have alternate text",
        help_url="https://example.com/help",
        selectors=["img.hero", "img.logo"],
        html_snippets=['<img class="hero" src="/h.jpg">'],
        count=2,
    )


def test_estimate_cost_scales_with_groups() -> None:
    estimate = estimate_cost(10, model=DEFAULT_MODEL)
    assert estimate.group_count == 10
    assert estimate.estimated_input_tokens == 7000
    assert estimate.estimated_output_tokens == 3500
    assert estimate.estimated_cost_usd > 0
    assert estimate.exceeds_threshold(10) is False
    assert estimate.exceeds_threshold(9) is True


def test_generate_insight_parses_json(mocker, sample_group: ViolationGroup) -> None:
    payload = {
        "explanation": "Missing alt text on images.",
        "why_it_matters": "Screen reader users miss image content.",
        "fix_suggestion": "Add alt attributes describing each image.",
    }
    mock_create = mocker.Mock(return_value=_mock_response(payload))
    mock_client = mocker.Mock()
    mock_client.messages.create = mock_create

    client = ClaudeClient(model=DEFAULT_MODEL, client=mock_client)
    insight = client.generate_insight(sample_group)

    assert isinstance(insight, RemediationInsight)
    assert insight.explanation == payload["explanation"]
    assert insight.fix_suggestion == payload["fix_suggestion"]

    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["system"] == SYSTEM_PROMPT
    assert "image-alt" in kwargs["messages"][0]["content"]
    assert "img.hero" in kwargs["messages"][0]["content"]


def test_generate_insight_strips_markdown_fences(
    mocker, sample_group: ViolationGroup
) -> None:
    payload = {
        "explanation": "x",
        "why_it_matters": "y",
        "fix_suggestion": "z",
    }
    fenced = f"```json\n{json.dumps(payload)}\n```"
    mock_create = mocker.Mock(
        return_value=SimpleNamespace(content=[SimpleNamespace(text=fenced)])
    )
    mock_client = mocker.Mock()
    mock_client.messages.create = mock_create

    client = ClaudeClient(client=mock_client)
    insight = client.generate_insight(sample_group)
    assert insight.explanation == "x"


def test_generate_insight_rejects_invalid_json(
    mocker, sample_group: ViolationGroup
) -> None:
    mock_create = mocker.Mock(
        return_value=SimpleNamespace(content=[SimpleNamespace(text="not-json")])
    )
    mock_client = mocker.Mock()
    mock_client.messages.create = mock_create

    client = ClaudeClient(client=mock_client)
    with pytest.raises(ValueError, match="Failed to parse"):
        client.generate_insight(sample_group)


def test_enrich_groups(mocker, sample_group: ViolationGroup) -> None:
    payload = {
        "explanation": "a",
        "why_it_matters": "b",
        "fix_suggestion": "c",
    }
    mock_create = mocker.Mock(return_value=_mock_response(payload))
    mock_client = mocker.Mock()
    mock_client.messages.create = mock_create

    client = ClaudeClient(client=mock_client)
    enriched = client.enrich_groups([sample_group])

    assert len(enriched) == 1
    assert enriched[0].insight is not None
    assert enriched[0].insight.explanation == "a"
    assert mock_create.call_count == 1


def test_require_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ClaudeClient()


def test_build_user_prompt_truncates_selectors() -> None:
    selectors = [f"img.n{i}" for i in range(25)]
    prompt = build_user_prompt(
        rule_id="image-alt",
        impact="critical",
        wcag_criteria=["1.1.1"],
        description="alt",
        help_url="",
        count=25,
        selectors=selectors,
        html_snippets=[],
    )
    assert "img.n0" in prompt
    assert "and 5 more" in prompt
