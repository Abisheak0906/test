# CostObserver interview notes

## 60-second explanation

CostObserver reads a daily cost report from local S3 and resource metadata from DynamoDB. It checks each resource against three focused rules: old unattached volumes that cost money and are not required, databases open to the public internet on their database port, and those same exposed databases whose daily cost is strictly more than twice their 7-day average. It stores findings with a stable date/resource/rule key, prints a prioritized summary, and reports missing information instead of treating it as safe. Savings are estimates for eligible volumes only.

## Execution walkthrough

1. `main()` parses the report date and creates S3/DynamoDB clients from `config.py`.
2. `run()` calls `ingest.load_usage_report()` for the date-specific S3 key.
3. `ingest.load_metadata()` looks up each distinct resource ID.
4. `rules.evaluate()` applies the matching rules, deduplicates results, and collects data issues.
5. `store.save_findings()` writes each finding using its stable `finding_id`.
6. `print_summary()` sorts and prints results, counts affected resources, and sums savings once per resource.

## Important files and functions

- `triage/config.py`: endpoint, region, bucket/table names, and S3 key builder.
- `triage/ingest.py`: reads JSON using `Decimal` and loads metadata.
- `triage/rules.py`: three rule functions plus `evaluate()` and data issue handling.
- `triage/models.py`: `Finding`, `DataIssue`, rule IDs, severity mapping, and stable finding IDs.
- `triage/store.py`: idempotent DynamoDB upserts.
- `triage/main.py`: command-line workflow and readable terminal summary.
- `tests/test_rules.py`, `tests/test_workflow.py`: rule boundaries, missing information, ingestion, persistence, repeated runs, and output.

## Three rules

- `UNATTACHED_VOLUME` (`MEDIUM`): volume is unattached at least 7 days, costs more than $0/day, and `retention_required` is explicitly `false`. Savings are daily cost × 30, rounded to cents.
- `PUBLIC_DATABASE` (`HIGH`): an inbound rule has the same port as `database_port` and its CIDR is exactly `0.0.0.0/0`.
- `EXPOSED_DATABASE_COST_SPIKE` (`CRITICAL`): the database matches the public rule and has a positive 7-day average; today's cost must be strictly greater than 2× that average. Exactly 2× does not qualify.

The public and cost-spike findings do not estimate savings. They are investigation/security signals, not proof of an attack.

## Savings example

A volume costing `$2.00` per day produces `$2.00 × 30 = $60.00` projected monthly savings. If it has multiple findings, the summary only sums its savings once by resource ID. Actual savings depend on the owner approving action and the daily cost continuing.

## Edge cases and tests to know

- Exactly 7 unattached days qualifies; 6 days does not.
- Missing/true `retention_required`, zero cost, or an attached volume does not qualify.
- A public rule on port 443 does not expose a database listening on 5432.
- Exactly twice the average is not a spike; a private database never gets the exposed-database spike finding.
- Missing metadata and required fields are surfaced as issues; missing/zero public-database baselines get `BASELINE_UNAVAILABLE`.
- Duplicate input rows and repeated runs do not duplicate findings. `test_end_to_end_run_is_idempotent_and_prints_summary` checks output and persistence.

## Five likely questions

1. **Why use `Decimal`?** DynamoDB does not support Python `float`; `Decimal` also avoids binary floating-point rounding in cost values.
2. **How do reruns avoid duplicates?** `finding_id` is deterministic: report date + resource ID + rule ID. `put_item` replaces the same key.
3. **Why is the spike rule limited to public databases?** That is the specified rule; a high bill alone is not evidence of exposure or an attack.
4. **How is missing metadata handled?** It creates a `MISSING_METADATA` issue, and that resource's rules are skipped rather than guessed.
5. **How is total savings computed?** Sum non-null savings by distinct resource ID; the database rules have no savings estimate.

## Three possible live-coding changes (hints)

1. Add a new volume age threshold: locate the date difference in `check_unattached_volume` and add a boundary test first.
2. Support a different database public CIDR: keep the exact condition centralized in `check_public_database` and test both allowed and rejected CIDRs.
3. Add a new severity count to the output: update the severity ordering/count summary, then assert the rendered line in a test.

## Python concepts in this project

- **Functions:** named units with one job, such as loading data or evaluating one rule.
- **Dictionaries and lists:** JSON objects become dictionaries; records and inbound rules are lists.
- **Optional values:** rule functions return a `Finding` or `None` when the condition does not match.
- **Dataclasses:** `Finding` and `DataIssue` provide clear structured records with named fields.
- **Type annotations:** communicate expected inputs and return values; they do not validate JSON at runtime.
- **`Decimal`:** exact decimal arithmetic for money and DynamoDB-compatible numeric values.
- **Exceptions:** AWS/JSON failures should be surfaced to the caller rather than silently treated as missing records.
- **Comprehensions, sets, and dictionaries:** concise ways to count unique resources and deduplicate stable finding IDs.

## Prioritized 30-minute revision plan

1. **0–8 minutes:** Read `triage/rules.py`; explain each condition and the 7-day/2× boundaries without looking at notes.
2. **8–13 minutes:** Trace `main.run()` through ingestion, metadata lookup, evaluation, and storage.
3. **13–18 minutes:** Explain `Finding.finding_id`, why DynamoDB writes are safe to repeat, and how savings are counted once.
4. **18–24 minutes:** Run `python -m pytest`; read the boundary, missing-data, and repeat-run tests and explain what each proves.
5. **24–30 minutes:** Practice a small change: alter a test fixture, predict the finding, then implement the matching rule change and run the focused test.
