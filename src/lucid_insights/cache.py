"""Disk cache for Claude responses keyed by violation-group hash."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lucid_insights.models import RemediationInsight, ViolationGroup

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "lucid-insights"


def group_cache_key(group: ViolationGroup) -> str:
    """Hash stable group identity for cache lookups."""
    payload = {
        "rule_id": group.rule_id,
        "impact": group.impact.value,
        "wcag_criteria": group.wcag_criteria,
        "description": group.description,
        "selectors": sorted(group.selectors),
        "html_snippets": group.html_snippets,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return digest


class InsightCache:
    """Simple JSON-file cache under ~/.cache/lucid-insights by default."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, group: ViolationGroup) -> RemediationInsight | None:
        path = self._path_for(group_cache_key(group))
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RemediationInsight.model_validate(data)
        except (json.JSONDecodeError, OSError, ValueError):
            return None

    def set(self, group: ViolationGroup, insight: RemediationInsight) -> None:
        path = self._path_for(group_cache_key(group))
        path.write_text(
            insight.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def get_or_none(self, group: ViolationGroup) -> RemediationInsight | None:
        return self.get(group)
