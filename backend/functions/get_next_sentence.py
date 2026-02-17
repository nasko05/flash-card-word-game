import os
import random

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import BotoCoreError, ClientError

from common import generate_rand_key, json_response, read_user_id

SENTENCES_TABLE = os.environ.get("SENTENCES_TABLE")
SENTENCE_INDEX_NAME = "StatusRandKeyIndex"
APPROVED_STATUS = "APPROVED"
CANDIDATE_LIMIT = 30
SCAN_PAGE_SIZE = 100

dynamodb = boto3.resource("dynamodb")


def parse_optional_difficulty(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None
    return max(1, min(value, 5))


def parse_optional_domain(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    cleaned = raw_value.strip().lower()
    return cleaned or None


def query_index_slice(table, key_condition, limit: int) -> list[dict]:
    items: list[dict] = []
    last_evaluated_key = None

    while len(items) < limit:
        query_kwargs = {
            "IndexName": SENTENCE_INDEX_NAME,
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


def read_approved_candidates_from_index(table) -> list[dict]:
    pivot = generate_rand_key()
    first_slice = query_index_slice(
        table,
        Key("status").eq(APPROVED_STATUS) & Key("statusRandKey").gte(pivot),
        CANDIDATE_LIMIT,
    )
    if len(first_slice) < CANDIDATE_LIMIT:
        wrap_slice = query_index_slice(
            table,
            Key("status").eq(APPROVED_STATUS) & Key("statusRandKey").lt(pivot),
            CANDIDATE_LIMIT - len(first_slice),
        )
        first_slice.extend(wrap_slice)
    return first_slice


def read_approved_candidates_from_scan(table) -> list[dict]:
    items: list[dict] = []
    last_evaluated_key = None

    while len(items) < CANDIDATE_LIMIT:
        scan_kwargs = {
            "FilterExpression": Attr("status").eq(APPROVED_STATUS),
            "Limit": SCAN_PAGE_SIZE,
        }
        if last_evaluated_key:
            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

        result = table.scan(**scan_kwargs)
        items.extend(result.get("Items", []))
        last_evaluated_key = result.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    random.shuffle(items)
    return items[:CANDIDATE_LIMIT]


def is_index_unavailable_error(error: ClientError) -> bool:
    err = error.response.get("Error", {})
    code = str(err.get("Code", ""))
    message = str(err.get("Message", "")).lower()

    if code not in {"ValidationException", "ResourceNotFoundException"}:
        return False

    return (
        "backfilling global secondary index" in message
        or "does not have the specified index" in message
        or SENTENCE_INDEX_NAME.lower() in message
    )


def item_matches_filters(item: dict, domain: str | None, difficulty: int | None) -> bool:
    if domain:
        item_domain = item.get("domain")
        if not isinstance(item_domain, str) or item_domain.lower() != domain:
            return False

    if difficulty is not None:
        item_difficulty = item.get("difficulty")
        try:
            parsed_difficulty = int(item_difficulty)
        except (TypeError, ValueError):
            return False
        if parsed_difficulty != difficulty:
            return False

    return True


def lambda_handler(event, _context):
    if not SENTENCES_TABLE:
        return json_response(500, {"message": "SENTENCES_TABLE environment variable is missing."})

    try:
        user_id = read_user_id(event)
        if not user_id:
            return json_response(401, {"message": "Unauthorized."})

        query = event.get("queryStringParameters") or {}
        target_domain = parse_optional_domain(query.get("domain"))
        target_difficulty = parse_optional_difficulty(query.get("difficulty"))

        table = dynamodb.Table(SENTENCES_TABLE)
        try:
            candidates = read_approved_candidates_from_index(table)
        except ClientError as index_error:
            if not is_index_unavailable_error(index_error):
                raise
            print(f"Sentence index unavailable, using scan fallback: {index_error}")
            candidates = []

        if not candidates:
            candidates = read_approved_candidates_from_scan(table)

        filtered_candidates = [
            item for item in candidates if item_matches_filters(item, target_domain, target_difficulty)
        ]

        if not filtered_candidates:
            return json_response(
                200,
                {
                    "item": None,
                    "message": "No sentence exercises are available for this filter.",
                },
            )

        selected = random.choice(filtered_candidates)
        return json_response(
            200,
            {
                "item": {
                    "id": selected.get("sentenceId"),
                    "promptBulgarian": selected.get("promptBg"),
                    "personKey": selected.get("personKey"),
                    "domain": selected.get("domain"),
                    "difficulty": selected.get("difficulty"),
                    "tense": selected.get("tense"),
                }
            },
        )
    except (ClientError, BotoCoreError) as exc:
        print(f"Failed to fetch next sentence exercise: {exc}")
        return json_response(500, {"message": "Failed to fetch sentence exercise."})
