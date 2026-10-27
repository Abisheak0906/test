"""Tests for S3 ingestion, DynamoDB persistence, and report output."""

from decimal import Decimal

from triage import config, ingest, main
from triage.models import Finding
from triage.store import save_findings


def test_ingestion_reads_decimals_and_deduplicates_metadata_lookups(aws):
    s3, dynamodb = aws
    report = ingest.load_usage_report(
        s3,
        config.USAGE_BUCKET,
        config.usage_key("2026-10-20"),
    )
    assert isinstance(report["records"][0]["daily_cost_usd"], Decimal)

    table = dynamodb.Table(config.METADATA_TABLE)
    items = ingest.load_metadata(table, ["db-orders-prod", "db-orders-prod", "unknown"])
    assert "db-orders-prod" in items
    assert "unknown" not in items


def test_saving_same_finding_twice_keeps_one_dynamodb_item(aws):
    _, dynamodb = aws
    finding = Finding(
        resource_id="vol-test",
        rule_id="UNATTACHED_VOLUME",
        severity="MEDIUM",
        analysis_date="2026-10-20",
        recommended_action="Check with the owner.",
        evidence={"daily_cost_usd": Decimal("2.00")},
        projected_monthly_savings_usd=Decimal("60.00"),
    )
    table = dynamodb.Table(config.FINDINGS_TABLE)

    assert save_findings(table, [finding]) == 1
    assert save_findings(table, [finding]) == 1
    items = table.scan()["Items"]
    assert len(items) == 1
    assert items[0]["projected_monthly_savings_usd"] == Decimal("60.00")


def test_end_to_end_run_is_idempotent_and_prints_summary(aws, capsys):
    s3, dynamodb = aws
    main.run("2026-10-20", s3, dynamodb)
    first_items = dynamodb.Table(config.FINDINGS_TABLE).scan()["Items"]
    main.run("2026-10-20", s3, dynamodb)
    second_items = dynamodb.Table(config.FINDINGS_TABLE).scan()["Items"]

    assert len(first_items) == len(second_items)
    assert len({item["finding_id"] for item in second_items}) == len(second_items)
    output = capsys.readouterr().out
    assert "CostObserver triage report for 2026-10-20" in output
    assert "Resources analyzed : 16" in output
    assert "Findings           : CRITICAL" in output
    assert "Could not fully check" in output
