import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from common import json_response, parse_json_body, read_user_id, to_clean_string
from sentence_utils import evaluate_spanish_answer, safe_sentence_list

SENTENCES_TABLE = os.environ.get("SENTENCES_TABLE")
APPROVED_STATUS = "APPROVED"

dynamodb = boto3.resource("dynamodb")


def extract_expected_answers(item: dict) -> tuple[str, list[str]]:
    canonical = item.get("canonicalEs")
    canonical_answer = canonical.strip() if isinstance(canonical, str) else ""

    accepted = safe_sentence_list(item.get("acceptedEs"))
    if canonical_answer and canonical_answer not in accepted:
        accepted.append(canonical_answer)

    return canonical_answer, accepted


def lambda_handler(event, _context):
    if not SENTENCES_TABLE:
        return json_response(500, {"message": "SENTENCES_TABLE environment variable is missing."})

    try:
        user_id = read_user_id(event)
        if not user_id:
            return json_response(401, {"message": "Unauthorized."})

        payload = parse_json_body(event.get("body"))
        sentence_id = to_clean_string(payload.get("sentenceId"))
        answer = to_clean_string(payload.get("answer"))

        if not sentence_id or not answer:
            return json_response(400, {"message": "'sentenceId' and 'answer' are required."})

        table = dynamodb.Table(SENTENCES_TABLE)
        item = table.get_item(Key={"sentenceId": sentence_id}).get("Item")
        if not item:
            return json_response(404, {"message": "Sentence exercise was not found."})

        status = item.get("status")
        if status != APPROVED_STATUS:
            return json_response(404, {"message": "Sentence exercise is not available."})

        canonical_answer, accepted_answers = extract_expected_answers(item)
        if not accepted_answers:
            return json_response(500, {"message": "Sentence exercise is misconfigured."})

        result_status, message = evaluate_spanish_answer(answer, accepted_answers)
        return json_response(
            200,
            {
                "status": result_status,
                "isCorrect": result_status != "wrong",
                "message": message,
                "canonicalAnswer": canonical_answer or accepted_answers[0],
            },
        )
    except ValueError as exc:
        return json_response(400, {"message": str(exc)})
    except (ClientError, BotoCoreError) as exc:
        print(f"Failed to check sentence answer: {exc}")
        return json_response(500, {"message": "Failed to check sentence answer."})
