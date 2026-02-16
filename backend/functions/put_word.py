import datetime
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from common import (
    RANDOM_POOL,
    generate_rand_key,
    json_response,
    parse_json_body,
    read_user_claims,
    to_clean_string,
)

WORDS_TABLE = os.environ.get("WORDS_TABLE")
dynamodb = boto3.resource("dynamodb")



def lambda_handler(event, _context):
    if not WORDS_TABLE:
        return json_response(500, {"message": "WORDS_TABLE environment variable is missing."})

    try:
        payload = parse_json_body(event.get("body"))
        spanish = to_clean_string(payload.get("spanish"))
        bulgarian = to_clean_string(payload.get("bulgarian"))

        if not spanish or not bulgarian:
            return json_response(
                400,
                {"message": "Both 'spanish' and 'bulgarian' fields are required."}
            )

        if len(spanish) > 120 or len(bulgarian) > 120:
            return json_response(
                400,
                {"message": "Each field must be 120 characters or fewer."}
            )

        claims = read_user_claims(event)
        table = dynamodb.Table(WORDS_TABLE)
        word_id = spanish.lower()

        table.update_item(
            Key={"wordId": word_id},
            UpdateExpression=(
                "SET spanish = :spanish, bulgarian = :bulgarian, updatedAt = :updated_at, "
                "createdBy = :created_by, randomPool = if_not_exists(randomPool, :random_pool), "
                "randKey = if_not_exists(randKey, :rand_key)"
            ),
            ExpressionAttributeValues={
                ":spanish": spanish,
                ":bulgarian": bulgarian,
                ":updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ":created_by": claims.get("sub", "unknown"),
                ":random_pool": RANDOM_POOL,
                ":rand_key": generate_rand_key(),
            },
        )

        return json_response(
            201,
            {
                "message": "Word saved successfully.",
                "item": {
                    "wordId": word_id,
                    "spanish": spanish,
                    "bulgarian": bulgarian
                }
            }
        )
    except ValueError as exc:
        return json_response(400, {"message": str(exc)})
    except (ClientError, BotoCoreError) as exc:
        print(f"Failed to save word: {exc}")
        return json_response(500, {"message": "Failed to save word."})
