"""Persist findings to DynamoDB."""

from triage.models import Finding


def save_findings(table, findings: list[Finding]) -> int:
    """Write findings to the PrioritizedFindings table and return how many were written.

    Use Finding.finding_id as the key so that re-running the same report
    does not create duplicates. See README.md for the item format.
    """
    for finding in findings:
        item = {
            "finding_id": finding.finding_id,
            "resource_id": finding.resource_id,
            "rule_id": finding.rule_id,
            "severity": finding.severity,
            "analysis_date": finding.analysis_date,
            "evidence": finding.evidence,
            "recommended_action": finding.recommended_action,
        }
        if finding.projected_monthly_savings_usd is not None:
            item["projected_monthly_savings_usd"] = finding.projected_monthly_savings_usd
        table.put_item(Item=item)
    return len(findings)
