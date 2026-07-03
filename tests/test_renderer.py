"""Tests for Jinja2 report rendering."""

from __future__ import annotations

from datetime import UTC, datetime

from lucid_insights.models import (
    Impact,
    RemediationInsight,
    RemediationReport,
    ReportSummary,
    ViolationGroup,
)
from lucid_insights.renderer import OutputFormat, render_report


def _report_with_insights() -> RemediationReport:
    insight = RemediationInsight(
        explanation="Images lack alternative text.",
        why_it_matters="Screen reader users cannot understand images.",
        fix_suggestion='Add alt="…" to each image.',
    )
    groups = [
        ViolationGroup(
            rule_id="image-alt",
            impact=Impact.CRITICAL,
            wcag_criteria=["1.1.1"],
            description="Images must have alternate text",
            help_url="https://example.com/image-alt",
            selectors=["img.hero", "img.logo"],
            html_snippets=[],
            count=2,
            insight=insight,
        ),
        ViolationGroup(
            rule_id="region",
            impact=Impact.MINOR,
            wcag_criteria=["1.3.1"],
            description="Content should be in landmarks",
            selectors=["div.promo"],
            count=1,
            insight=RemediationInsight(
                explanation="Content sits outside landmarks.",
                why_it_matters="Assistive tech users may miss it.",
                fix_suggestion="Wrap content in a landmark region.",
            ),
        ),
    ]
    return RemediationReport(
        summary=ReportSummary(
            total_violations=3,
            total_groups=2,
            by_impact={"critical": 2, "minor": 1},
            url="https://example.com/checkout",
            timestamp=datetime(2026, 7, 3, 14, 30, tzinfo=UTC),
        ),
        groups=groups,
        full_report_path="report.md",
    )


def test_markdown_report_has_summary_and_sections() -> None:
    text = render_report(_report_with_insights(), fmt=OutputFormat.MARKDOWN)

    assert "# Accessibility Remediation Report" in text
    assert "https://example.com/checkout" in text
    assert "`image-alt`" in text
    assert "Images lack alternative text." in text
    assert "lucid-insights:fingerprint" in text
    assert "img.hero" in text


def test_github_comment_collapses_minor() -> None:
    text = render_report(_report_with_insights(), fmt=OutputFormat.GITHUB_COMMENT)

    assert "<details>" in text
    assert "<summary>" in text
    assert "Minor" in text
    # Critical stays expanded (heading, not only inside details)
    assert "### Critical" in text
    assert "`image-alt`" in text


def test_slack_summary_top_issues_and_link() -> None:
    text = render_report(_report_with_insights(), fmt=OutputFormat.SLACK)

    assert "*Accessibility remediation summary*" in text
    assert "Top issues" in text
    assert "`image-alt`" in text
    assert "report.md" in text


def test_empty_report() -> None:
    report = RemediationReport(
        summary=ReportSummary(
            total_violations=0,
            total_groups=0,
            by_impact={},
            url="https://example.com",
        ),
        groups=[],
    )
    text = render_report(report, fmt=OutputFormat.MARKDOWN)
    assert "No violations" in text
