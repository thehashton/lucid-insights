"""CLI integration tests with mocked Anthropic calls."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from lucid_insights.cli import app
from lucid_insights.diff import embed_fingerprint
from lucid_insights.models import RemediationInsight

runner = CliRunner()


def _fake_client(mocker):
    return mocker.Mock(
        generate_insight=mocker.Mock(
            side_effect=lambda group: RemediationInsight(
                explanation=f"{group.rule_id} issue",
                why_it_matters="impact",
                fix_suggestion=f"fix {group.rule_id}",
            )
        )
    )


def test_report_markdown(
    mocker, sample_audit_path: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    mocker.patch("lucid_insights.cli.ClaudeClient", return_value=_fake_client(mocker))

    output = tmp_path / "report.md"
    cache_dir = tmp_path / "cache"
    result = runner.invoke(
        app,
        [
            "report",
            "--input",
            str(sample_audit_path),
            "--output",
            str(output),
            "--format",
            "markdown",
            "--cache-dir",
            str(cache_dir),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    text = output.read_text(encoding="utf-8")
    assert "image-alt" in text
    assert "Accessibility Remediation Report" in text
    assert "lucid-insights:fingerprint" in text


def test_cost_threshold_requires_yes(
    mocker, sample_audit_path: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    mocker.patch("lucid_insights.cli.ClaudeClient")

    result = runner.invoke(
        app,
        [
            "report",
            "--input",
            str(sample_audit_path),
            "--output",
            str(tmp_path / "out.md"),
            "--cost-threshold",
            "1",
            "--no-cache",
        ],
    )
    assert result.exit_code == 2
    assert "exceeds threshold" in result.output


def test_diff_against_filters_unchanged(
    mocker, sample_audit_path: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    previous = tmp_path / "previous.md"
    fingerprint = {
        "image-alt": ["img.hero-banner", "img.product-thumb", "img.logo"],
        "button-name": ["button.icon-only.close"],
        "color-contrast": [".muted-label", "a.footer-link"],
        "label": ["input#promo-code"],
        "landmark-one-main": ["html"],
        "region": ["div.promo-banner"],
    }
    previous.write_text(embed_fingerprint(fingerprint), encoding="utf-8")

    client = mocker.Mock()
    client.generate_insight = mocker.Mock()
    mocker.patch("lucid_insights.cli.ClaudeClient", return_value=client)

    result = runner.invoke(
        app,
        [
            "report",
            "--input",
            str(sample_audit_path),
            "--diff-against",
            str(previous),
            "--no-cache",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "No violations to remediate" in result.output
    client.generate_insight.assert_not_called()
