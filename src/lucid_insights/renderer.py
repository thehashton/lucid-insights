"""Jinja2 rendering for remediation reports."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from lucid_insights.diff import embed_fingerprint
from lucid_insights.models import IMPACT_ORDER, Impact, RemediationReport


class OutputFormat(StrEnum):
    MARKDOWN = "markdown"
    GITHUB_COMMENT = "github-comment"
    SLACK = "slack"


_TEMPLATE_MAP = {
    OutputFormat.MARKDOWN: "report.md.j2",
    OutputFormat.GITHUB_COMMENT: "github_comment.md.j2",
    OutputFormat.SLACK: "slack.md.j2",
}


def _env() -> Environment:
    return Environment(
        loader=PackageLoader("lucid_insights", "templates"),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_report(
    report: RemediationReport,
    fmt: OutputFormat = OutputFormat.MARKDOWN,
) -> str:
    """Render a remediation report to the requested format."""
    template_name = _TEMPLATE_MAP[fmt]
    template = _env().get_template(template_name)

    by_impact = report.groups_by_impact()
    # Ordered sections: critical → minor, omit empty
    impact_sections = [
        (impact, by_impact[impact])
        for impact in sorted(Impact, key=lambda i: IMPACT_ORDER[i])
        if by_impact[impact]
    ]

    fingerprint_block = embed_fingerprint(report.fingerprint())

    return template.render(
        report=report,
        summary=report.summary,
        impact_sections=impact_sections,
        fingerprint_block=fingerprint_block,
        Impact=Impact,
    )


def write_report(
    report: RemediationReport,
    output_path: Path,
    fmt: OutputFormat = OutputFormat.MARKDOWN,
) -> str:
    """Render and write a report; returns the rendered text."""
    content = render_report(report, fmt=fmt)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return content
