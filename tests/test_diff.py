"""Tests for report diffing."""

from __future__ import annotations

from pathlib import Path

from lucid_insights.diff import (
    embed_fingerprint,
    filter_new_or_changed,
    parse_fingerprint,
)
from lucid_insights.models import Impact, ViolationGroup


def _group(rule_id: str, *selectors: str) -> ViolationGroup:
    return ViolationGroup(
        rule_id=rule_id,
        impact=Impact.CRITICAL,
        description=rule_id,
        selectors=list(selectors),
        count=len(selectors),
    )


def test_embed_and_parse_fingerprint() -> None:
    fingerprint = {"image-alt": ["img.a", "img.b"], "label": ["input#x"]}
    markdown = f"# Report\n\n{embed_fingerprint(fingerprint)}\n"
    assert parse_fingerprint(markdown) == fingerprint


def test_filter_new_or_changed() -> None:
    previous = {"image-alt": ["img.a", "img.b"], "label": ["input#x"]}
    groups = [
        _group("image-alt", "img.a", "img.b"),  # unchanged
        _group("label", "input#x", "input#y"),  # changed selectors
        _group("button-name", "button.close"),  # new rule
    ]
    filtered = filter_new_or_changed(groups, previous)
    rule_ids = {g.rule_id for g in filtered}
    assert rule_ids == {"label", "button-name"}


def test_parse_fingerprint_from_headings_fallback() -> None:
    markdown = """
# Report

### `image-alt` (2 occurrences)

**Affected selectors:**
- `img.hero`
- `img.logo`

### `label` (1 occurrence)

**Affected selectors:**
- `input#promo`
"""
    fingerprint = parse_fingerprint(markdown)
    assert fingerprint["image-alt"] == ["img.hero", "img.logo"]
    assert fingerprint["label"] == ["input#promo"]


def test_load_fingerprint_from_file(tmp_path: Path) -> None:
    from lucid_insights.diff import load_fingerprint

    path = tmp_path / "previous.md"
    path.write_text(
        embed_fingerprint({"region": ["div.promo"]}),
        encoding="utf-8",
    )
    assert load_fingerprint(path) == {"region": ["div.promo"]}
