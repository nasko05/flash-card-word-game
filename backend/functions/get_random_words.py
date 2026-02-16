import os
import random

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from common import json_response

WORDS_TABLE = os.environ.get("WORDS_TABLE")
MAX_LIMIT = 50
DEFAULT_LIMIT = 50
SCAN_PAGE_SIZE = 250

dynamodb = boto3.resource("dynamodb")


def parse_limit(raw_limit: str | None) -> int:
    if raw_limit is None:
        return DEFAULT_LIMIT

    try:
        parsed = int(raw_limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT

    return max(1, min(parsed, MAX_LIMIT))


def read_all_words(table) -> list[dict]:
    items: list[dict] = []
    last_evaluated_key = None

    while True:
        scan_kwargs = {
            "ProjectionExpression": "wordId, spanish, bulgarian",
            "Limit": SCAN_PAGE_SIZE
        }
        if last_evaluated_key:
            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

        result = table.scan(**scan_kwargs)
        items.extend(result.get("Items", []))
        last_evaluated_key = result.get("LastEvaluatedKey")

        if not last_evaluated_key:
            break

    return items



def lambda_handler(event, _context):
    if not WORDS_TABLE:
        return json_response(500, {"message": "WORDS_TABLE environment variable is missing."})

    try:
        limit = parse_limit((event.get("queryStringParameters") or {}).get("limit"))
        table = dynamodb.Table(WORDS_TABLE)
        words = read_all_words(table)

        if not words:
            return json_response(200, {"count": 0, "items": []})

        sample_size = min(limit, len(words))
        sampled_words = random.sample(words, sample_size)

        return json_response(
            200,
            {
                "count": sample_size,
                "items": [
                    {
                        "id": item.get("wordId"),
                        "spanish": item.get("spanish"),
                        "bulgarian": item.get("bulgarian")
                    }
                    for item in sampled_words
                ]
            }
        )
    except (ClientError, BotoCoreError) as exc:
        print(f"Failed to fetch random words: {exc}")
        return json_response(500, {"message": "Failed to fetch words."})
