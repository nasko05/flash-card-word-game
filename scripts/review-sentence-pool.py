#!/usr/bin/env python3
"""Review and moderate pending sentence exercises."""

from __future__ import annotations

import argparse
import random
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

SENTENCE_INDEX_NAME = "StatusRandKeyIndex"
SENTENCES_TABLE_OUTPUT_KEY = "SentencesTableName"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review sentence pool statuses.")
    parser.add_argument("--stack-name", default="flash-card-word-game")
    parser.add_argument("--region", default="eu-central-1")
    parser.add_argument("--profile", default="adonev-login")
    parser.add_argument("--table-name", default="", help="Optional explicit table name.")
    parser.add_argument("--status", default="PENDING_REVIEW", help="Status bucket to inspect.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--action",
        choices=["list", "approve", "reject"],
        default="list",
        help="Action for selected IDs.",
    )
    parser.add_argument(
        "--ids",
        nargs="*",
        default=[],
        help="Sentence IDs to update when using approve/reject.",
    )
    return parser.parse_args()


def resolve_table_name(cloudformation_client, stack_name: str) -> str:
    response = cloudformation_client.describe_stacks(StackName=stack_name)
    stacks = response.get("Stacks", [])
    if not stacks:
        raise RuntimeError(f"Stack '{stack_name}' was not found.")

    for output in stacks[0].get("Outputs", []):
        if output.get("OutputKey") == SENTENCES_TABLE_OUTPUT_KEY:
            table_name = output.get("OutputValue", "")
            if table_name:
                return table_name

    raise RuntimeError(
        f"Stack '{stack_name}' does not expose output '{SENTENCES_TABLE_OUTPUT_KEY}'."
    )


def list_items(table, status: str, limit: int) -> list[dict[str, Any]]:
    response = table.query(
        IndexName=SENTENCE_INDEX_NAME,
        KeyConditionExpression=Key("status").eq(status),
        Limit=max(1, min(limit, 100)),
        ScanIndexForward=True,
    )
    return response.get("Items", [])


def update_status(table, sentence_id: str, target_status: str):
    table.update_item(
        Key={"sentenceId": sentence_id},
        UpdateExpression="SET #status = :status, statusRandKey = :rand_key",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": target_status,
            ":rand_key": random.randint(1, 1_000_000_000),
        },
        ConditionExpression="attribute_exists(sentenceId)",
    )


def main() -> int:
    args = parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cloudformation_client = session.client("cloudformation")
    dynamodb_resource = session.resource("dynamodb")

    try:
        table_name = args.table_name or resolve_table_name(cloudformation_client, args.stack_name)
        table = dynamodb_resource.Table(table_name)

        if args.action == "list":
            items = list_items(table, args.status, args.limit)
            if not items:
                print(f"No items found for status '{args.status}'.")
                return 0

            for item in items:
                print(
                    f"{item.get('sentenceId')} | {item.get('status')} | "
                    f"{item.get('promptBg')} -> {item.get('canonicalEs')}"
                )
            return 0

        if not args.ids:
            raise RuntimeError("--ids is required when action is approve/reject.")

        target_status = "APPROVED" if args.action == "approve" else "REJECTED"
        updated = 0
        for sentence_id in args.ids:
            update_status(table, sentence_id, target_status)
            updated += 1

        print(f"Updated {updated} items to status '{target_status}'.")
        return 0
    except (RuntimeError, ClientError, BotoCoreError) as error:
        print(f"Review action failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
