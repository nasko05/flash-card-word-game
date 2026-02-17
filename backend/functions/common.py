import json
import random
from decimal import Decimal
from typing import Any, Dict

RAND_KEY_MIN = 1
RAND_KEY_MAX = 1_000_000_000


def json_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    def _json_default(value: Any):
        if isinstance(value, Decimal):
            if value == value.to_integral_value():
                return int(value)
            return float(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(payload, default=_json_default)
    }


def parse_json_body(body: str | None) -> Dict[str, Any]:
    if not body:
        return {}

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object.")

    return parsed


def to_clean_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def read_user_claims(event: Dict[str, Any]) -> Dict[str, Any]:
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )


def read_user_id(event: Dict[str, Any]) -> str:
    claims = read_user_claims(event)
    user_id = claims.get("sub")
    return user_id.strip() if isinstance(user_id, str) else ""


def generate_rand_key() -> int:
    return random.randint(RAND_KEY_MIN, RAND_KEY_MAX)
