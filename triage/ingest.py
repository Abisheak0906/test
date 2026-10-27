"""Read the daily usage file and the resource metadata."""

import json
from decimal import Decimal


def load_usage_report(s3, bucket: str, key: str) -> dict:
    """Download and parse the daily usage file from S3.

    Returns the parsed document: {"report_date": ..., "currency": ..., "records": [...]}.

    Tip: DynamoDB does not accept Python floats. Parsing with
    json.loads(text, parse_float=Decimal) avoids conversion problems later.
    """
    response = s3.get_object(Bucket=bucket, Key=key)
    text = response["Body"].read().decode("utf-8")
    report = json.loads(text, parse_float=Decimal)
    if not isinstance(report, dict) or not isinstance(report.get("records"), list):
        raise ValueError("Usage report must be an object containing a records list")
    return report


def load_metadata(table, resource_ids: list[str]) -> dict[str, dict]:
    """Return metadata items keyed by resource_id.

    Resources without a metadata item should simply be absent from the result,
    so the caller can report them as a data issue.
    """
    metadata_by_id = {}
    for resource_id in dict.fromkeys(resource_ids):
        response = table.get_item(Key={"resource_id": resource_id})
        item = response.get("Item")
        if item is not None:
            metadata_by_id[resource_id] = item
    return metadata_by_id
