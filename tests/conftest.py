"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lucid_insights.grouping import group_violations
from lucid_insights.models import LucidAudit, RemediationInsight, ViolationGroup

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_audit_path() -> Path:
    return FIXTURES / "sample_audit.json"


@pytest.fixture
def sample_audit(sample_audit_path: Path) -> LucidAudit:
    data = json.loads(sample_audit_path.read_text(encoding="utf-8"))
    return LucidAudit.model_validate(data)


@pytest.fixture
def sample_groups(sample_audit: LucidAudit) -> list[ViolationGroup]:
    return group_violations(sample_audit)


@pytest.fixture
def sample_insight() -> RemediationInsight:
    return RemediationInsight(
        explanation="Images are missing alternative text.",
        why_it_matters="Screen reader users cannot understand the image content.",
        fix_suggestion='Add a meaningful alt, e.g. alt="Checkout hero banner".',
    )
