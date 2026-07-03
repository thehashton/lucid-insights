"""Pydantic models for Lucid audit input and remediation report output."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Impact(StrEnum):
    """Severity levels matching Lucid / axe-core impact values."""

    CRITICAL = "critical"
    SERIOUS = "serious"
    MODERATE = "moderate"
    MINOR = "minor"


IMPACT_ORDER: dict[Impact, int] = {
    Impact.CRITICAL: 0,
    Impact.SERIOUS: 1,
    Impact.MODERATE: 2,
    Impact.MINOR: 3,
}


class Violation(BaseModel):
    """A single accessibility violation from Lucid audit output."""

    id: str = Field(..., description="Rule identifier, e.g. 'image-alt'")
    impact: Impact
    wcag_criteria: list[str] = Field(default_factory=list)
    selector: str
    html_snippet: str = ""
    description: str
    help_url: str = ""


class LucidAudit(BaseModel):
    """Top-level Lucid CLI JSON output."""

    url: str
    timestamp: datetime
    violations: list[Violation] = Field(default_factory=list)

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: Any) -> Any:
        if isinstance(value, str):
            # Accept trailing Z (ISO8601 UTC)
            return value.replace("Z", "+00:00")
        return value


class RemediationInsight(BaseModel):
    """Claude-generated remediation guidance for a violation group."""

    explanation: str = Field(..., description="Plain-English explanation of the issue")
    why_it_matters: str = Field(..., description="Impact on real users")
    fix_suggestion: str = Field(..., description="Concrete code-level fix")


class ViolationGroup(BaseModel):
    """Violations batched by rule id for a single Claude call."""

    rule_id: str
    impact: Impact
    wcag_criteria: list[str] = Field(default_factory=list)
    description: str
    help_url: str = ""
    selectors: list[str] = Field(default_factory=list)
    html_snippets: list[str] = Field(default_factory=list)
    count: int = 0
    insight: RemediationInsight | None = None

    def group_key(self) -> str:
        """Stable identity for caching and diffing."""
        selectors = "|".join(sorted(self.selectors))
        return f"{self.rule_id}::{self.impact.value}::{selectors}"


class ReportSummary(BaseModel):
    """Aggregate counts for the report header."""

    total_violations: int = 0
    total_groups: int = 0
    by_impact: dict[str, int] = Field(default_factory=dict)
    url: str = ""
    timestamp: datetime | None = None


class RemediationReport(BaseModel):
    """Full remediation report ready for template rendering."""

    summary: ReportSummary
    groups: list[ViolationGroup] = Field(default_factory=list)
    full_report_path: str | None = None
    is_diff: bool = False
    previous_report_path: str | None = None

    def groups_by_impact(self) -> dict[Impact, list[ViolationGroup]]:
        ordered: dict[Impact, list[ViolationGroup]] = {
            impact: [] for impact in Impact
        }
        for group in self.groups:
            ordered[group.impact].append(group)
        return ordered

    def fingerprint(self) -> dict[str, list[str]]:
        """Machine-readable map of rule_id -> selectors for diffing."""
        result: dict[str, list[str]] = {}
        for group in self.groups:
            result.setdefault(group.rule_id, [])
            for selector in group.selectors:
                if selector not in result[group.rule_id]:
                    result[group.rule_id].append(selector)
        for rule_id in result:
            result[rule_id] = sorted(result[rule_id])
        return result
