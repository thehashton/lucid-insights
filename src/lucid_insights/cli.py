"""Typer CLI for lucid-insights."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console

from lucid_insights.cache import InsightCache
from lucid_insights.claude_client import (
    DEFAULT_COST_THRESHOLD,
    DEFAULT_MODEL,
    ClaudeClient,
    estimate_cost,
)
from lucid_insights.diff import filter_new_or_changed, load_fingerprint
from lucid_insights.grouping import group_violations
from lucid_insights.models import (
    IMPACT_ORDER,
    Impact,
    LucidAudit,
    RemediationReport,
    ReportSummary,
    ViolationGroup,
)
from lucid_insights.renderer import OutputFormat, render_report, write_report

app = typer.Typer(
    name="lucid-insights",
    help="Turn Lucid accessibility audit JSON into actionable remediation reports.",
    no_args_is_help=True,
)
console = Console(stderr=True)


def main() -> None:
    """Entry point for the lucid-insights console script."""
    app()


@app.callback()
def _root() -> None:
    """Turn Lucid accessibility audit JSON into actionable remediation reports."""


@app.command("report")
def report_command(
    input_path: Path = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to Lucid audit JSON output.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write report to this path (stdout if omitted).",
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.MARKDOWN,
        "--format",
        "-f",
        help="Report format: markdown, github-comment, or slack.",
    ),
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        "-m",
        help="Claude model ID (see docs.claude.com).",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation when group count exceeds the cost threshold.",
    ),
    cost_threshold: int = typer.Option(
        DEFAULT_COST_THRESHOLD,
        "--cost-threshold",
        help="Require --yes when unique violation groups exceed this count.",
    ),
    full_report: Path | None = typer.Option(
        None,
        "--full-report",
        help="Path shown in Slack summaries linking to the full markdown report.",
    ),
    diff_against: Path | None = typer.Option(
        None,
        "--diff-against",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Only report new/changed violations vs a previous report.md.",
    ),
    cache: bool = typer.Option(
        True,
        "--cache/--no-cache",
        help="Cache Claude responses per violation-group hash.",
    ),
    cache_dir: Path | None = typer.Option(
        None,
        "--cache-dir",
        help="Override the default insight cache directory.",
    ),
) -> None:
    """Generate a human-readable remediation report from Lucid audit JSON."""
    audit = _load_audit(input_path)
    groups = group_violations(audit)

    previous_path: str | None = None
    is_diff = False
    if diff_against is not None:
        previous = load_fingerprint(diff_against)
        groups = filter_new_or_changed(groups, previous)
        previous_path = str(diff_against)
        is_diff = True
        console.print(
            f"[cyan]Diff mode:[/cyan] {len(groups)} new/changed rule group(s) "
            f"vs {diff_against}"
        )

    if not groups:
        report = _build_report(
            audit,
            groups=[],
            full_report_path=str(full_report) if full_report else None,
            is_diff=is_diff,
            previous_report_path=previous_path,
        )
        _emit(report, format=format, output=output)
        console.print("[green]No violations to remediate.[/green]")
        raise typer.Exit(code=0)

    insight_cache = InsightCache(cache_dir=cache_dir) if cache else None
    pending = _split_cached(groups, insight_cache)

    estimate = estimate_cost(len(pending), model=model)
    console.print(
        f"[bold]Cost estimate[/bold] for {estimate.group_count} API call(s) "
        f"({estimate.model}):\n"
        f"  ~{estimate.estimated_input_tokens:,} input tokens, "
        f"~{estimate.estimated_output_tokens:,} output tokens\n"
        f"  ~${estimate.estimated_cost_usd:.4f} USD (approximate)"
    )
    if insight_cache is not None:
        cached_count = len(groups) - len(pending)
        if cached_count:
            console.print(f"[dim]{cached_count} group(s) served from cache.[/dim]")

    if estimate.exceeds_threshold(cost_threshold) and not yes:
        console.print(
            f"[yellow]Group count ({estimate.group_count}) exceeds threshold "
            f"({cost_threshold}). Re-run with --yes to proceed.[/yellow]"
        )
        raise typer.Exit(code=2)

    if pending:
        client = ClaudeClient(model=model)
        for group in pending:
            console.print(f"[dim]Generating insight for[/dim] {group.rule_id}…")
            insight = client.generate_insight(group)
            group.insight = insight
            if insight_cache is not None:
                insight_cache.set(group, insight)

    full_report_path = None
    if full_report is not None:
        full_report_path = str(full_report)
    elif output is not None and format == OutputFormat.MARKDOWN:
        full_report_path = str(output)

    report = _build_report(
        audit,
        groups=groups,
        full_report_path=full_report_path,
        is_diff=is_diff,
        previous_report_path=previous_path,
    )
    _emit(report, format=format, output=output)
    console.print("[green]Report generated.[/green]")


def _load_audit(path: Path) -> LucidAudit:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid JSON in {path}: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        return LucidAudit.model_validate(data)
    except Exception as exc:
        console.print(f"[red]Audit JSON does not match Lucid schema: {exc}[/red]")
        raise typer.Exit(code=1) from exc


def _split_cached(
    groups: list[ViolationGroup],
    insight_cache: InsightCache | None,
) -> list[ViolationGroup]:
    """Attach cached insights in-place; return groups still needing API calls."""
    pending: list[ViolationGroup] = []
    for group in groups:
        if insight_cache is not None:
            cached = insight_cache.get(group)
            if cached is not None:
                group.insight = cached
                continue
        pending.append(group)
    return pending


def _build_report(
    audit: LucidAudit,
    groups: list[ViolationGroup],
    *,
    full_report_path: str | None,
    is_diff: bool,
    previous_report_path: str | None,
) -> RemediationReport:
    by_impact: dict[str, int] = {}
    for group in groups:
        by_impact[group.impact.value] = (
            by_impact.get(group.impact.value, 0) + group.count
        )

    ordered_counts = {
        impact.value: by_impact[impact.value]
        for impact in sorted(Impact, key=lambda i: IMPACT_ORDER[i])
        if impact.value in by_impact
    }

    summary = ReportSummary(
        total_violations=sum(g.count for g in groups),
        total_groups=len(groups),
        by_impact=ordered_counts,
        url=audit.url,
        timestamp=audit.timestamp,
    )
    return RemediationReport(
        summary=summary,
        groups=groups,
        full_report_path=full_report_path,
        is_diff=is_diff,
        previous_report_path=previous_report_path,
    )


def _emit(
    report: RemediationReport,
    *,
    format: OutputFormat,
    output: Path | None,
) -> None:
    content = render_report(report, fmt=format)
    if output is not None:
        write_report(report, output, fmt=format)
        console.print(f"[dim]Wrote {output}[/dim]")
    else:
        sys.stdout.write(content if content.endswith("\n") else content + "\n")
