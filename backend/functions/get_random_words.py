import os
import random

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

from common import generate_rand_key, json_response, read_user_id

WORDS_TABLE = os.environ.get("WORDS_TABLE")
RANDOM_INDEX_NAME = "RandomPoolRandKeyIndex"
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


def read_indexed_random_words(table, user_id: str, limit: int) -> list[dict]:
    pivot = generate_rand_key()

    primary_slice = query_index_slice(
        table,
        Key("randomPool").eq(user_id) & Key("randKey").gte(pivot),
        limit,
    )

    if len(primary_slice) < limit:
        wrap_slice = query_index_slice(
            table,
            Key("randomPool").eq(user_id) & Key("randKey").lt(pivot),
            limit - len(primary_slice),
        )
        primary_slice.extend(wrap_slice)

    return primary_slice


def fallback_user_partition_sample(table, user_id: str, limit: int) -> list[dict]:
    # Reservoir sampling keeps memory bounded while preserving uniformity.
    reservoir: list[dict] = []
    seen = 0
    last_evaluated_key = None

    while True:
        query_kwargs = {
            "KeyConditionExpression": Key("userId").eq(user_id),
            "ProjectionExpression": "wordId, spanish, bulgarian",
            "Limit": SCAN_PAGE_SIZE,
        }
        if last_evaluated_key:
            query_kwargs["ExclusiveStartKey"] = last_evaluated_key

        result = table.query(**query_kwargs)
        for item in result.get("Items", []):
            seen += 1
            if len(reservoir) < limit:
                reservoir.append(item)
                continue

            replacement_position = random.randint(1, seen)
            if replacement_position <= limit:
                reservoir[replacement_position - 1] = item

        last_evaluated_key = result.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    return reservoir


def is_index_unavailable_error(error: ClientError) -> bool:
    err = error.response.get("Error", {})
    code = str(err.get("Code", ""))
    message = str(err.get("Message", "")).lower()

    if code not in {"ValidationException", "ResourceNotFoundException"}:
        return False

    return (
        "backfilling global secondary index" in message
        or "does not have the specified index" in message
        or RANDOM_INDEX_NAME.lower() in message
    )



def lambda_handler(event, _context):
    if not WORDS_TABLE:
        return json_response(500, {"message": "WORDS_TABLE environment variable is missing."})

    try:
        limit = parse_limit((event.get("queryStringParameters") or {}).get("limit"))
        user_id = read_user_id(event)
        if not user_id:
            return json_response(401, {"message": "Unauthorized."})

        table = dynamodb.Table(WORDS_TABLE)

        try:
            sampled_words = read_indexed_random_words(table, user_id, limit)
        except ClientError as index_error:
            if not is_index_unavailable_error(index_error):
                raise
            print(f"Random index unavailable, falling back to scan sampling: {index_error}")
            sampled_words = []

        if not sampled_words:
            sampled_words = fallback_user_partition_sample(table, user_id, limit)

        if not sampled_words:
            return json_response(
                200,
                {
                    "count": 0,
                    "items": [],
                },
            )

        random.shuffle(sampled_words)
        sampled_words = sampled_words[:limit]

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
