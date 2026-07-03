"""Tests for insight response cache."""

from __future__ import annotations

from pathlib import Path

from lucid_insights.cache import InsightCache, group_cache_key
from lucid_insights.models import Impact, RemediationInsight, ViolationGroup


def _group(selector: str = "img.hero") -> ViolationGroup:
    return ViolationGroup(
        rule_id="image-alt",
        impact=Impact.CRITICAL,
        description="Images must have alternate text",
        selectors=[selector],
        html_snippets=[f'<img class="{selector}">'],
        count=1,
    )


def test_cache_roundtrip(tmp_path: Path, sample_insight: RemediationInsight) -> None:
    cache = InsightCache(cache_dir=tmp_path)
    group = _group()

    assert cache.get(group) is None
    cache.set(group, sample_insight)
    loaded = cache.get(group)

    assert loaded is not None
    assert loaded.explanation == sample_insight.explanation


def test_cache_key_changes_with_selectors() -> None:
    a = _group("img.a")
    b = _group("img.b")
    assert group_cache_key(a) != group_cache_key(b)


def test_corrupt_cache_returns_none(
    tmp_path: Path, sample_insight: RemediationInsight
) -> None:
    cache = InsightCache(cache_dir=tmp_path)
    group = _group()
    cache.set(group, sample_insight)
    path = tmp_path / f"{group_cache_key(group)}.json"
    path.write_text("{not-json", encoding="utf-8")
    assert cache.get(group) is None
