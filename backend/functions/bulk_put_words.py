import datetime
import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from common import json_response, parse_json_body, read_user_claims, to_clean_string

WORDS_TABLE = os.environ.get("WORDS_TABLE")
MAX_BULK_ITEMS = 1000
MAX_ERRORS_IN_RESPONSE = 20

dynamodb = boto3.resource("dynamodb")


def parse_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")

    if not isinstance(items, list):
        raise ValueError("'items' must be an array of objects.")

    if not items:
        raise ValueError("'items' cannot be empty.")

    if len(items) > MAX_BULK_ITEMS:
        raise ValueError(f"'items' cannot contain more than {MAX_BULK_ITEMS} rows.")

    return items


def lambda_handler(event, _context):
    if not WORDS_TABLE:
        return json_response(500, {"message": "WORDS_TABLE environment variable is missing."})

    try:
        payload = parse_json_body(event.get("body"))
        raw_items = parse_items(payload)
        claims = read_user_claims(event)
        actor = claims.get("sub", "unknown")
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        valid_by_word_id: dict[str, dict[str, str]] = {}
        validation_errors: list[dict[str, Any]] = []

        for index, raw_item in enumerate(raw_items, start=1):
            if not isinstance(raw_item, dict):
                validation_errors.append(
                    {
                        "row": index,
                        "message": "Row must be an object with 'spanish' and 'bulgarian' fields."
                    }
                )
                continue

            spanish = to_clean_string(raw_item.get("spanish"))
            bulgarian = to_clean_string(raw_item.get("bulgarian"))

            if not spanish or not bulgarian:
                validation_errors.append(
                    {
                        "row": index,
                        "message": "Both 'spanish' and 'bulgarian' are required."
                    }
                )
                continue

            if len(spanish) > 120 or len(bulgarian) > 120:
                validation_errors.append(
                    {
                        "row": index,
                        "message": "Each field must be 120 characters or fewer."
                    }
                )
                continue

            word_id = spanish.lower()
            valid_by_word_id[word_id] = {
                "wordId": word_id,
                "spanish": spanish,
                "bulgarian": bulgarian,
                "updatedAt": timestamp,
                "createdBy": actor
            }

        valid_items = list(valid_by_word_id.values())
        rejected_count = len(validation_errors)

        if not valid_items:
            return json_response(
                400,
                {
                    "message": "No valid rows found in bulk upload.",
                    "savedCount": 0,
                    "rejectedCount": rejected_count,
                    "errors": validation_errors[:MAX_ERRORS_IN_RESPONSE]
                }
            )

        table = dynamodb.Table(WORDS_TABLE)
        with table.batch_writer(overwrite_by_pkeys=["wordId"]) as batch:
            for item in valid_items:
                batch.put_item(Item=item)

        return json_response(
            201,
            {
                "message": "Bulk upload processed.",
                "savedCount": len(valid_items),
                "rejectedCount": rejected_count,
                "errors": validation_errors[:MAX_ERRORS_IN_RESPONSE]
            }
        )
    except ValueError as exc:
        return json_response(400, {"message": str(exc)})
    except (ClientError, BotoCoreError) as exc:
        print(f"Failed to process bulk word upload: {exc}")
        return json_response(500, {"message": "Failed to process bulk upload."})
