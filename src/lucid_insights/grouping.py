"""Batch similar Lucid violations before calling Claude."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from lucid_insights.models import (
    IMPACT_ORDER,
    Impact,
    LucidAudit,
    Violation,
    ViolationGroup,
)


def group_violations(audit: LucidAudit) -> list[ViolationGroup]:
    """Group violations by rule id.

    Each group shares one Claude explanation and lists every affected selector.
    When the same rule appears with different impacts, the highest severity wins.
    WCAG criteria and help URLs are unioned across instances.
    """
    buckets: dict[str, list[Violation]] = defaultdict(list)
    for violation in audit.violations:
        buckets[violation.id].append(violation)

    groups: list[ViolationGroup] = []
    for rule_id, violations in buckets.items():
        impact = _highest_impact(v.impact for v in violations)
        criteria = _unique_preserve_order(
            criterion for v in violations for criterion in v.wcag_criteria
        )
        selectors = _unique_preserve_order(v.selector for v in violations)
        snippets = _unique_preserve_order(
            v.html_snippet for v in violations if v.html_snippet
        )
        description = max((v.description for v in violations), key=len, default="")
        help_url = next((v.help_url for v in violations if v.help_url), "")

        groups.append(
            ViolationGroup(
                rule_id=rule_id,
                impact=impact,
                wcag_criteria=criteria,
                description=description,
                help_url=help_url,
                selectors=selectors,
                html_snippets=snippets,
                count=len(violations),
            )
        )

    return sorted(
        groups,
        key=lambda g: (IMPACT_ORDER[g.impact], -g.count, g.rule_id),
    )


def _highest_impact(impacts: Iterable[Impact]) -> Impact:
    return min(impacts, key=lambda impact: IMPACT_ORDER[impact])


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
