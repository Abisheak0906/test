"""Shared data shapes. You may extend these, but keep the field names in Finding."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

UNATTACHED_VOLUME = "UNATTACHED_VOLUME"
PUBLIC_DATABASE = "PUBLIC_DATABASE"
EXPOSED_DATABASE_COST_SPIKE = "EXPOSED_DATABASE_COST_SPIKE"

SEVERITY_BY_RULE = {
    UNATTACHED_VOLUME: "MEDIUM",
    PUBLIC_DATABASE: "HIGH",
    EXPOSED_DATABASE_COST_SPIKE: "CRITICAL",
}


@dataclass
class Finding:
    resource_id: str
    rule_id: str
    severity: str
    analysis_date: str
    recommended_action: str
    evidence: dict[str, Any] = field(default_factory=dict)
    projected_monthly_savings_usd: Decimal | None = None

    @property
    def finding_id(self) -> str:
        """Stable key, so processing the same input twice updates instead of duplicating."""
        return f"{self.analysis_date}#{self.resource_id}#{self.rule_id}"


@dataclass
class DataIssue:
    resource_id: str
    issue: str
    detail: str
