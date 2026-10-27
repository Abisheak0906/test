"""Focused tests for the three detection rules and missing-data behavior."""

from decimal import Decimal

from triage import rules
from triage.models import EXPOSED_DATABASE_COST_SPIKE, PUBLIC_DATABASE, UNATTACHED_VOLUME


def test_worked_example_from_the_brief():
    usage = {
        "resource_id": "vol-example",
        "resource_type": "ebs_volume",
        "daily_cost_usd": Decimal("2.00"),
        "avg_daily_cost_7d_usd": Decimal("2.00"),
    }
    metadata = {
        "resource_id": "vol-example",
        "resource_type": "ebs_volume",
        "attachment_state": "unattached",
        "unattached_since": "2026-10-10",
        "retention_required": False,
    }

    finding = rules.check_unattached_volume(usage, metadata, "2026-10-20")

    assert finding is not None
    assert finding.rule_id == UNATTACHED_VOLUME
    assert finding.severity == "MEDIUM"
    assert finding.projected_monthly_savings_usd == Decimal("60.00")


def _volume(cost="2.00", detached="2026-10-13", retention=False):
    return (
        {
            "resource_id": "vol-test",
            "resource_type": "ebs_volume",
            "daily_cost_usd": Decimal(cost),
        },
        {
            "resource_id": "vol-test",
            "attachment_state": "unattached",
            "unattached_since": detached,
            "retention_required": retention,
        },
    )


def _database(cost="60", average="30", public=True):
    return (
        {
            "resource_id": "db-test",
            "resource_type": "rds_database",
            "daily_cost_usd": Decimal(cost),
            "avg_daily_cost_7d_usd": Decimal(average),
        },
        {
            "database_port": 5432,
            "inbound_rules": [
                {"port": 5432, "cidr": "0.0.0.0/0" if public else "10.0.0.0/16"}
            ],
        },
    )


def test_unattached_volume_at_seven_day_boundary():
    usage, metadata = _volume()
    finding = rules.check_unattached_volume(usage, metadata, "2026-10-20")

    assert finding is not None
    assert finding.rule_id == UNATTACHED_VOLUME
    assert finding.projected_monthly_savings_usd == Decimal("60.00")
    assert finding.evidence["days_unattached"] == 7


@pytest.mark.parametrize(
    ("cost", "detached", "retention"),
    [("2.00", "2026-10-14", False), ("2.00", "2026-10-13", True), ("0", "2026-10-13", False)],
)
def test_unattached_volume_rejects_nonmatching_conditions(cost, detached, retention):
    usage, metadata = _volume(cost, detached, retention)
    assert rules.check_unattached_volume(usage, metadata, "2026-10-20") is None


def test_public_database_requires_matching_database_port():
    usage, metadata = _database()
    finding = rules.check_public_database(usage, metadata, "2026-10-20")
    assert finding is not None
    assert finding.rule_id == PUBLIC_DATABASE
    assert finding.projected_monthly_savings_usd is None

    metadata["inbound_rules"] = [{"port": 443, "cidr": "0.0.0.0/0"}]
    assert rules.check_public_database(usage, metadata, "2026-10-20") is None


def test_cost_spike_requires_public_exposure_and_strictly_more_than_twice_average():
    usage, metadata = _database(cost="60", average="30")
    assert rules.check_cost_spike(usage, metadata, "2026-10-20") is None

    usage, metadata = _database(cost="60.01", average="30")
    finding = rules.check_cost_spike(usage, metadata, "2026-10-20")
    assert finding is not None
    assert finding.rule_id == EXPOSED_DATABASE_COST_SPIKE

    usage, metadata = _database(cost="100", average="30", public=False)
    assert rules.check_cost_spike(usage, metadata, "2026-10-20") is None


def test_missing_fields_and_unavailable_baseline_are_reported():
    usage, metadata = _volume()
    del metadata["retention_required"]
    _, issues = rules.evaluate([usage], {usage["resource_id"]: metadata}, "2026-10-20")
    assert [issue.issue for issue in issues] == ["MISSING_FIELD"]

    usage, metadata = _database(average="0")
    _, issues = rules.evaluate([usage], {usage["resource_id"]: metadata}, "2026-10-20")
    assert [issue.issue for issue in issues] == ["BASELINE_UNAVAILABLE"]

    _, issues = rules.evaluate([usage], {}, "2026-10-20")
    assert [issue.issue for issue in issues] == ["MISSING_METADATA"]


def test_unavailable_baseline_does_not_hide_public_database_finding():
    usage, metadata = _database(average="0")
    findings, issues = rules.evaluate([usage], {usage["resource_id"]: metadata}, "2026-10-20")

    assert [finding.rule_id for finding in findings] == [PUBLIC_DATABASE]
    assert [issue.issue for issue in issues] == ["BASELINE_UNAVAILABLE"]


def test_duplicate_records_do_not_duplicate_findings_or_issues():
    usage, metadata = _volume()
    findings, issues = rules.evaluate(
        [usage, usage],
        {usage["resource_id"]: metadata},
        "2026-10-20",
    )

    assert len(findings) == 1
    assert issues == []
