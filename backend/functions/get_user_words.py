import os

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

from common import json_response, read_user_id

WORDS_TABLE = os.environ.get("WORDS_TABLE")
dynamodb = boto3.resource("dynamodb")


def read_user_words(table, user_id: str) -> list[dict]:
    items: list[dict] = []
    last_evaluated_key = None

    while True:
        query_kwargs = {
            "KeyConditionExpression": Key("userId").eq(user_id),
            "ProjectionExpression": "wordId, spanish, bulgarian",
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
        user_id = read_user_id(event)
        if not user_id:
            return json_response(401, {"message": "Unauthorized."})

        table = dynamodb.Table(WORDS_TABLE)
        words = read_user_words(table, user_id)

        return json_response(
            200,
            {
                "count": len(words),
                "items": [
                    {
                        "id": item.get("wordId"),
                        "spanish": item.get("spanish"),
                        "bulgarian": item.get("bulgarian"),
                    }
                    for item in words
                ],
            },
        )
    except (ClientError, BotoCoreError) as exc:
        print(f"Failed to export words: {exc}")
        return json_response(500, {"message": "Failed to export words."})
