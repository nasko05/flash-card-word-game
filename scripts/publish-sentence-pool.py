#!/usr/bin/env python3
"""Publish generated sentence exercises to DynamoDB."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

SENTENCES_TABLE_OUTPUT_KEY = "SentencesTableName"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish sentence pool JSON into DynamoDB.")
    parser.add_argument(
        "--input",
        default="docs/sentence-pool.generated.json",
        help="Input JSON file produced by generate-sentence-pool.py",
    )
    parser.add_argument("--stack-name", default="flash-card-word-game")
    parser.add_argument("--region", default="eu-central-1")
    parser.add_argument("--profile", default="adonev-login")
    parser.add_argument("--table-name", default="", help="Optional explicit table name.")
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


def load_items(input_path: Path) -> list[dict]:
    if not input_path.exists():
        raise RuntimeError(f"Input file was not found: {input_path}")

    content = input_path.read_text(encoding="utf-8")
    parsed = json.loads(content)
    if not isinstance(parsed, list):
        raise RuntimeError("Input JSON must be an array of sentence items.")

    items: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("sentenceId"), str) or not item["sentenceId"].strip():
            continue
        # boto3 requires Decimal for floating-point numbers in DynamoDB.
        normalized = json.loads(json.dumps(item), parse_float=Decimal)
        items.append(normalized)

    if not items:
        raise RuntimeError("No valid sentence items were found in the input file.")
    return items


def main() -> int:
    args = parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cloudformation_client = session.client("cloudformation")
    dynamodb_resource = session.resource("dynamodb")

    try:
        items = load_items(Path(args.input))
        table_name = args.table_name or resolve_table_name(cloudformation_client, args.stack_name)
        table = dynamodb_resource.Table(table_name)

        with table.batch_writer(overwrite_by_pkeys=["sentenceId"]) as batch:
            for item in items:
                batch.put_item(Item=item)

        status_counts = Counter(str(item.get("status", "UNKNOWN")) for item in items)
        print(f"Published {len(items)} sentence exercises to table '{table_name}'.")
        for status, count in sorted(status_counts.items()):
            print(f"- {status}: {count}")
        return 0
    except (RuntimeError, ClientError, BotoCoreError, json.JSONDecodeError) as error:
        print(f"Publish failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
