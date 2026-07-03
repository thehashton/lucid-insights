"""Diff current violations against a previous remediation report."""

from __future__ import annotations

import json
import re
from pathlib import Path

from lucid_insights.models import ViolationGroup

FINGERPRINT_START = "<!-- lucid-insights:fingerprint"
FINGERPRINT_END = "-->"

_FINGERPRINT_RE = re.compile(
    r"<!--\s*lucid-insights:fingerprint\s*(\{.*?\})\s*-->",
    re.DOTALL,
)


def embed_fingerprint(fingerprint: dict[str, list[str]]) -> str:
    """Render a machine-readable fingerprint block for markdown reports."""
    payload = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
    return f"{FINGERPRINT_START}\n{payload}\n{FINGERPRINT_END}"


def parse_fingerprint(markdown: str) -> dict[str, list[str]]:
    """Extract rule_id -> selectors map from a previous report."""
    match = _FINGERPRINT_RE.search(markdown)
    if not match:
        # Fallback: parse rule headings like ### `image-alt`
        return _parse_fingerprint_from_headings(markdown)

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError("Previous report fingerprint is not valid JSON") from exc

    if not isinstance(data, dict):
        raise ValueError("Previous report fingerprint must be a JSON object")

    result: dict[str, list[str]] = {}
    for rule_id, selectors in data.items():
        if not isinstance(selectors, list):
            continue
        result[str(rule_id)] = [str(s) for s in selectors]
    return result


def load_fingerprint(path: Path) -> dict[str, list[str]]:
    """Load fingerprint from a previous markdown report path."""
    text = path.read_text(encoding="utf-8")
    return parse_fingerprint(text)


def filter_new_or_changed(
    groups: list[ViolationGroup],
    previous: dict[str, list[str]],
) -> list[ViolationGroup]:
    """Keep groups that are new or have different selectors than last run."""
    filtered: list[ViolationGroup] = []
    for group in groups:
        prior_selectors = set(previous.get(group.rule_id, []))
        current_selectors = set(group.selectors)
        if not prior_selectors or current_selectors != prior_selectors:
            filtered.append(group)
    return filtered


def _parse_fingerprint_from_headings(markdown: str) -> dict[str, list[str]]:
    """Best-effort parse when fingerprint comment is missing."""
    result: dict[str, list[str]] = {}
    current_rule: str | None = None
    for line in markdown.splitlines():
        heading = re.match(r"^###\s+`([^`]+)`", line)
        if heading:
            current_rule = heading.group(1)
            result.setdefault(current_rule, [])
            continue
        if current_rule is None:
            continue
        selector_match = re.match(r"^-\s+`([^`]+)`", line)
        if selector_match:
            selector = selector_match.group(1)
            if selector not in result[current_rule]:
                result[current_rule].append(selector)
    return result
