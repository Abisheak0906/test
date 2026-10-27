# My solution

## How to run

- Install Python 3.10+ and the pinned dependencies: `python -m pip install -r requirements.txt`.
- In one terminal, start the local AWS emulator with `moto_server -p 4566`.
- In another terminal, load the sample data with `python scripts/setup_data.py`.
- Run the analysis with `python -m triage.main --date 2026-10-20`.
- Run tests with `python -m pytest`.

## Key decisions

- Usage JSON is parsed with `Decimal`, because DynamoDB does not accept Python floats.
- Metadata is fetched by resource ID; absent items are reported as data issues rather than guessed.
- Rule logic stays in small functions, with `evaluate` collecting findings and check issues.
- Stable date/resource/rule finding IDs make DynamoDB writes idempotent.
- Only the storage rule estimates savings. The summary counts that estimate once per resource.

## Assumptions

- Baselines are required only to check a publicly exposed database for a cost spike.
- A missing or zero baseline is `BASELINE_UNAVAILABLE`; malformed fields are `MISSING_FIELD`.
- Findings indicate conditions to investigate, not proof of compromise or approval to delete resources.

## What I would improve with more time

- Add stricter schema validation and clearer handling for malformed AWS responses.
- Use DynamoDB batch reads for larger inventories and add tests for pagination/retries.
- Add structured logging and operational metrics.

## Running this on real AWS

I would schedule a daily, least-privilege Lambda (or container task) after the cost export is available. It would read only the required S3 objects and metadata, and write findings to DynamoDB using the stable key. The scheduler and worker should have bounded retries, a dead-letter destination for repeated failures, CloudWatch logs/metrics/alarms, and alerts for missing reports or failed runs. Secrets should use IAM roles rather than embedded credentials.

## Use of AI tools

AI assistance in Copilot SDK in VS Code was used to inspect the starter project, implement the workflow and tests, and draft these explanations. I reviewed the code and ran the available tests and local-emulator commands; I should be able to explain and modify each rule, the DynamoDB item key, and the savings aggregation myself.

## Time spent

Not tracked accurately.
