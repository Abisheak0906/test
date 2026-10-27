"""Command-line entry point.

Usage:
    python -m triage.main --date 2026-10-20
"""

import argparse
import sys
from decimal import Decimal

from botocore.exceptions import EndpointConnectionError

from triage import config, ingest, rules, store
from triage.models import (
    EXPOSED_DATABASE_COST_SPIKE,
    PUBLIC_DATABASE,
    UNATTACHED_VOLUME,
    DataIssue,
    Finding,
)


def print_summary(usage_records: list[dict], findings: list[Finding], issues: list[DataIssue]) -> None:
    """Print a short, readable summary. See examples/sample-summary.txt for the expected content."""
    severity_order = ("CRITICAL", "HIGH", "MEDIUM")
    counts = {severity: 0 for severity in severity_order}
    for finding in findings:
        if finding.severity in counts:
            counts[finding.severity] += 1

    unique_resources = {record.get("resource_id") for record in usage_records}
    unique_resources.discard(None)
    affected_resources = {finding.resource_id for finding in findings}
    savings_by_resource = {}
    for finding in findings:
        if finding.projected_monthly_savings_usd is not None:
            savings_by_resource.setdefault(finding.resource_id, finding.projected_monthly_savings_usd)
    total_savings = sum(savings_by_resource.values(), Decimal("0.00"))

    print(f"CostObserver triage report for {findings[0].analysis_date if findings else 'unknown date'}")
    print()
    print(f"Resources analyzed : {len(unique_resources)}")
    print(f"Resources affected : {len(affected_resources)}")
    severity_summary = " | ".join(f"{severity} {counts[severity]}" for severity in severity_order)
    print(f"Findings           : {severity_summary}")
    print(f"Projected monthly avoidable cost: ${total_savings:.2f}")
    print("  (estimate, assuming current daily rates continue and owners approve the change)")
    print()
    print("Needs attention first")
    for finding in findings:
        evidence = finding.evidence
        if finding.rule_id == EXPOSED_DATABASE_COST_SPIKE:
            detail = (
                f"Daily cost ${evidence['daily_cost_usd']:.2f} vs 7-day average "
                f"${evidence['avg_daily_cost_7d_usd']:.2f} while port "
                f"{evidence['database_port']} is open to {evidence['public_cidr']}."
            )
        elif finding.rule_id == PUBLIC_DATABASE:
            detail = (
                f"Port {evidence['database_port']} is open to {evidence['public_cidr']}."
            )
        elif finding.rule_id == UNATTACHED_VOLUME:
            detail = (
                f"Unattached for {evidence['days_unattached']} days at "
                f"${evidence['daily_cost_usd']:.2f}/day."
            )
        else:
            detail = finding.recommended_action
        print(f"  [{finding.severity}] {finding.resource_id}   {finding.rule_id}")
        print(f"             {detail} {finding.recommended_action}")
        if finding.projected_monthly_savings_usd is not None:
            print(f"             Projected saving: ${finding.projected_monthly_savings_usd:.2f}/month")

    if issues:
        print()
        print("Could not fully check")
        for issue in issues:
            print(f"  {issue.resource_id}  {issue.issue}  {issue.detail}")


def run(report_date: str, s3, dynamodb) -> None:
    report = ingest.load_usage_report(s3, config.USAGE_BUCKET, config.usage_key(report_date))
    records = report["records"]

    resource_ids = [record["resource_id"] for record in records]
    metadata = ingest.load_metadata(dynamodb.Table(config.METADATA_TABLE), resource_ids)

    findings, issues = rules.evaluate(records, metadata, report_date)
    store.save_findings(dynamodb.Table(config.FINDINGS_TABLE), findings)
    print_summary(records, findings, issues)


def main() -> int:
    parser = argparse.ArgumentParser(description="Correlate cloud cost with resource configuration.")
    parser.add_argument("--date", required=True, help="report date, for example 2026-10-20")
    args = parser.parse_args()

    try:
        run(args.date, config.s3_client(), config.dynamodb_resource())
    except EndpointConnectionError:
        print(f"Could not reach the local emulator at {config.ENDPOINT_URL}. Is moto_server running?", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
