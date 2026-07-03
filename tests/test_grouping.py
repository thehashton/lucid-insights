"""Tests for violation grouping."""

from __future__ import annotations

from lucid_insights.grouping import group_violations
from lucid_insights.models import Impact, LucidAudit, Violation


def test_groups_by_rule_id(sample_audit: LucidAudit) -> None:
    groups = group_violations(sample_audit)
    rule_ids = [g.rule_id for g in groups]

    assert rule_ids.count("image-alt") == 1
    assert len(groups) == 6  # 9 violations → 6 unique rules


def test_image_alt_collects_all_selectors(sample_audit: LucidAudit) -> None:
    groups = group_violations(sample_audit)
    image_alt = next(g for g in groups if g.rule_id == "image-alt")

    assert image_alt.count == 3
    assert image_alt.selectors == [
        "img.hero-banner",
        "img.product-thumb",
        "img.logo",
    ]
    assert image_alt.impact == Impact.CRITICAL
    assert image_alt.wcag_criteria == ["1.1.1"]


def test_sorted_by_severity_then_count(sample_audit: LucidAudit) -> None:
    groups = group_violations(sample_audit)

    # critical first (image-alt has 3, button-name has 1), then serious, etc.
    assert groups[0].rule_id == "image-alt"
    assert groups[0].impact == Impact.CRITICAL
    assert groups[1].rule_id == "button-name"
    assert groups[2].rule_id == "color-contrast"
    assert groups[2].impact == Impact.SERIOUS


def test_highest_impact_wins_for_mixed_severity() -> None:
    audit = LucidAudit(
        url="https://example.com",
        timestamp="2026-07-03T12:00:00Z",
        violations=[
            Violation(
                id="color-contrast",
                impact=Impact.MODERATE,
                wcag_criteria=["1.4.3"],
                selector=".a",
                description="contrast",
            ),
            Violation(
                id="color-contrast",
                impact=Impact.SERIOUS,
                wcag_criteria=["1.4.3"],
                selector=".b",
                description="contrast",
            ),
        ],
    )
    groups = group_violations(audit)
    assert len(groups) == 1
    assert groups[0].impact == Impact.SERIOUS
    assert groups[0].count == 2


def test_empty_audit() -> None:
    audit = LucidAudit(
        url="https://example.com",
        timestamp="2026-07-03T12:00:00Z",
        violations=[],
    )
    assert group_violations(audit) == []
