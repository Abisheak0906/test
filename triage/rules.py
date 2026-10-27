"""Detection rules. See README.md, section "The rules", for the exact conditions."""

from datetime import date
from decimal import Decimal, InvalidOperation

from triage.models import (
    EXPOSED_DATABASE_COST_SPIKE,
    PUBLIC_DATABASE,
    SEVERITY_BY_RULE,
    UNATTACHED_VOLUME,
    DataIssue,
    Finding,
)


def _decimal(value) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _finding(
    usage: dict,
    rule_id: str,
    report_date: str,
    action: str,
    evidence: dict,
    savings: Decimal | None = None,
) -> Finding:
    return Finding(
        resource_id=usage["resource_id"],
        rule_id=rule_id,
        severity=SEVERITY_BY_RULE[rule_id],
        analysis_date=report_date,
        recommended_action=action,
        evidence=evidence,
        projected_monthly_savings_usd=savings,
    )


def check_unattached_volume(usage: dict, metadata: dict, report_date: str) -> Finding | None:
    """Rule A: storage that may no longer be needed."""
    cost = _decimal(usage.get("daily_cost_usd"))
    detached = metadata.get("unattached_since")
    if (
        usage.get("resource_type") != "ebs_volume"
        or metadata.get("attachment_state") != "unattached"
        or cost is None
        or cost <= 0
        or not isinstance(detached, str)
        or metadata.get("retention_required") is not False
    ):
        return None

    try:
        days_unattached = (date.fromisoformat(report_date) - date.fromisoformat(detached)).days
    except ValueError:
        return None
    if days_unattached < 7:
        return None

    savings = (cost * 30).quantize(Decimal("0.01"))
    return _finding(
        usage,
        UNATTACHED_VOLUME,
        report_date,
        "Confirm with the owner before deleting this volume.",
        {
            "daily_cost_usd": cost,
            "days_unattached": days_unattached,
            "retention_required": False,
        },
        savings,
    )


def check_public_database(usage: dict, metadata: dict, report_date: str) -> Finding | None:
    """Rule B: database port open to any IPv4 address (0.0.0.0/0)."""
    if usage.get("resource_type") != "rds_database":
        return None
    database_port = metadata.get("database_port")
    inbound_rules = metadata.get("inbound_rules")
    if database_port is None or not isinstance(inbound_rules, list):
        return None

    public_rule = next(
        (
            rule
            for rule in inbound_rules
            if isinstance(rule, dict)
            and rule.get("port") == database_port
            and rule.get("cidr") == "0.0.0.0/0"
        ),
        None,
    )
    if public_rule is None:
        return None

    return _finding(
        usage,
        PUBLIC_DATABASE,
        report_date,
        "Restrict the database port to approved sources.",
        {"database_port": database_port, "public_cidr": public_rule["cidr"]},
    )


def check_cost_spike(usage: dict, metadata: dict, report_date: str) -> Finding | None:
    """Rule C: an exposed database whose daily cost is more than 2x its 7-day average."""
    if check_public_database(usage, metadata, report_date) is None:
        return None
    average = _decimal(usage.get("avg_daily_cost_7d_usd"))
    cost = _decimal(usage.get("daily_cost_usd"))
    if average is None or average <= 0 or cost is None or cost <= average * 2:
        return None

    return _finding(
        usage,
        EXPOSED_DATABASE_COST_SPIKE,
        report_date,
        "Investigate the cost increase and restrict database access.",
        {
            "daily_cost_usd": cost,
            "avg_daily_cost_7d_usd": average,
            "database_port": metadata["database_port"],
            "public_cidr": "0.0.0.0/0",
        },
    )


def evaluate(
    usage_records: list[dict],
    metadata_by_id: dict[str, dict],
    report_date: str,
) -> tuple[list[Finding], list[DataIssue]]:
    """Run every rule against every usage record.

    Returns all findings plus any data issues that prevented a check.
    """
    findings_by_id = {}
    issues_by_key = {}

    def add_issue(resource_id: str, issue: str, detail: str) -> None:
        data_issue = DataIssue(resource_id=resource_id, issue=issue, detail=detail)
        issues_by_key[(resource_id, issue, detail)] = data_issue

    for usage in usage_records:
        resource_id = usage.get("resource_id")
        resource_type = usage.get("resource_type")
        if not isinstance(resource_id, str):
            continue
        metadata = metadata_by_id.get(resource_id)
        if metadata is None:
            add_issue(resource_id, "MISSING_METADATA", "No metadata found for this resource.")
            continue

        if resource_type == "ebs_volume":
            cost = _decimal(usage.get("daily_cost_usd"))
            if cost is None:
                add_issue(resource_id, "MISSING_FIELD", "Missing or invalid daily_cost_usd.")
            attachment_state = metadata.get("attachment_state")
            if attachment_state is None:
                add_issue(resource_id, "MISSING_FIELD", "Missing attachment_state in metadata.")
                continue
            if attachment_state != "unattached":
                continue
            detached = metadata.get("unattached_since")
            if not isinstance(detached, str):
                add_issue(resource_id, "MISSING_FIELD", "Missing unattached_since in metadata.")
            else:
                try:
                    date.fromisoformat(detached)
                except ValueError:
                    add_issue(resource_id, "MISSING_FIELD", "Invalid unattached_since date in metadata.")
            if "retention_required" not in metadata:
                add_issue(resource_id, "MISSING_FIELD", "Missing retention_required in metadata.")
            finding = check_unattached_volume(usage, metadata, report_date)
            if finding is not None:
                findings_by_id.setdefault(finding.finding_id, finding)

        elif resource_type == "rds_database":
            if metadata.get("database_port") is None:
                add_issue(resource_id, "MISSING_FIELD", "Missing database_port in metadata.")
            if not isinstance(metadata.get("inbound_rules"), list):
                add_issue(resource_id, "MISSING_FIELD", "Missing or invalid inbound_rules in metadata.")
            elif any(not isinstance(rule, dict) for rule in metadata["inbound_rules"]):
                add_issue(resource_id, "MISSING_FIELD", "An inbound rule is malformed.")
            public_finding = check_public_database(usage, metadata, report_date)
            if public_finding is None:
                continue
            findings_by_id.setdefault(public_finding.finding_id, public_finding)

            cost = _decimal(usage.get("daily_cost_usd"))
            if cost is None:
                add_issue(resource_id, "MISSING_FIELD", "Missing or invalid daily_cost_usd.")
            average_value = usage.get("avg_daily_cost_7d_usd")
            average = _decimal(average_value)
            if average_value is None or average == 0:
                add_issue(resource_id, "BASELINE_UNAVAILABLE", "The 7-day average is missing or zero.")
            elif average is None or average < 0:
                add_issue(resource_id, "MISSING_FIELD", "The 7-day average is invalid.")
            elif cost is not None:
                spike_finding = check_cost_spike(usage, metadata, report_date)
                if spike_finding is not None:
                    findings_by_id.setdefault(spike_finding.finding_id, spike_finding)

    ordered_findings = sorted(
        findings_by_id.values(),
        key=lambda finding: (
            {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}.get(finding.severity, 3),
            finding.resource_id,
            finding.rule_id,
        ),
    )
    ordered_issues = sorted(issues_by_key.values(), key=lambda issue: (issue.resource_id, issue.issue, issue.detail))
    return ordered_findings, ordered_issues
