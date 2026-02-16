import os
import random

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

from common import RANDOM_POOL, generate_rand_key, json_response

WORDS_TABLE = os.environ.get("WORDS_TABLE")
RANDOM_INDEX_NAME = "RandomPoolRandKeyIndex"
MAX_LIMIT = 50
DEFAULT_LIMIT = 50

dynamodb = boto3.resource("dynamodb")


def parse_limit(raw_limit: str | None) -> int:
    if raw_limit is None:
        return DEFAULT_LIMIT

    try:
        parsed = int(raw_limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT

    return max(1, min(parsed, MAX_LIMIT))



def query_index_slice(table, key_condition, limit: int) -> list[dict]:
    items: list[dict] = []
    last_evaluated_key = None

    while len(items) < limit:
        query_kwargs = {
            "IndexName": RANDOM_INDEX_NAME,
            "KeyConditionExpression": key_condition,
            "Limit": limit - len(items),
            "ScanIndexForward": True,
        }
        if last_evaluated_key:
            query_kwargs["ExclusiveStartKey"] = last_evaluated_key

        result = table.query(**query_kwargs)
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
        pivot = generate_rand_key()

        primary_slice = query_index_slice(
            table,
            Key("randomPool").eq(RANDOM_POOL) & Key("randKey").gte(pivot),
            limit,
        )

        if len(primary_slice) < limit:
            wrap_slice = query_index_slice(
                table,
                Key("randomPool").eq(RANDOM_POOL) & Key("randKey").lt(pivot),
                limit - len(primary_slice),
            )
            primary_slice.extend(wrap_slice)

        if not primary_slice:
            return json_response(
                200,
                {
                    "count": 0,
                    "items": [],
                },
            )

        random.shuffle(primary_slice)
        sampled_words = primary_slice[:limit]

        return json_response(
            200,
            {
                "count": len(sampled_words),
                "items": [
                    {
                        "id": item.get("wordId"),
                        "spanish": item.get("spanish"),
                        "bulgarian": item.get("bulgarian"),
                    }
                    for item in sampled_words
                ],
            },
        )
    except (ClientError, BotoCoreError) as exc:
        print(f"Failed to fetch random words: {exc}")
        return json_response(500, {"message": "Failed to fetch words."})
