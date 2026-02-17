#!/usr/bin/env python3
"""Import an open-source BG/ES sentence corpus into sentence-pool JSON format."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

APPROVED_STATUS = "APPROVED"
PENDING_REVIEW_STATUS = "PENDING_REVIEW"

PERSON_PRONOUNS = {
    "yo": "yo",
    "tu": "t\u00fa",
    "el": "\u00e9l",
    "ella": "ella",
    "nosotros": "nosotros",
    "vosotros": "vosotros",
    "ellos": "ellos",
}

KNOWN_PRESENT_FORMS = {
    "trabajo",
    "trabajas",
    "trabaja",
    "trabajamos",
    "trabaj\u00e1is",
    "trabajan",
    "estudio",
    "estudias",
    "estudia",
    "estudiamos",
    "estudi\u00e1is",
    "estudian",
    "cocino",
    "cocinas",
    "cocina",
    "cocinamos",
    "cocin\u00e1is",
    "cocinan",
    "compro",
    "compras",
    "compra",
    "compramos",
    "compr\u00e1is",
    "compran",
    "bebo",
    "bebes",
    "bebe",
    "bebemos",
    "beb\u00e9is",
    "beben",
    "leo",
    "lees",
    "lee",
    "leemos",
    "le\u00e9is",
    "leen",
    "escribo",
    "escribes",
    "escribe",
    "escribimos",
    "escrib\u00eds",
    "escriben",
    "voy",
    "vas",
    "va",
    "vamos",
    "vais",
    "van",
    "tengo",
    "tienes",
    "tiene",
    "tenemos",
    "ten\u00e9is",
    "tienen",
    "hago",
    "haces",
    "hace",
    "hacemos",
    "hac\u00e9is",
    "hacen",
    "hablo",
    "hablas",
    "habla",
    "hablamos",
    "habl\u00e1is",
    "hablan",
    "vivo",
    "vives",
    "vive",
    "vivimos",
    "viv\u00eds",
    "viven",
    "puedo",
    "puedes",
    "puede",
    "podemos",
    "pod\u00e9is",
    "pueden",
}

NON_PRESENT_MARKERS = {
    "ayer",
    "anoche",
    "ma\u00f1ana",
    "fui",
    "fue",
    "fueron",
    "estuve",
    "estuvo",
    "estaban",
    "he",
    "ha",
    "han",
}

TOKEN_RE = re.compile(r"[A-Za-z\u00c0-\u024f\u00f1\u00d1]+", re.UNICODE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import open BG/ES sentence dataset.")
    parser.add_argument("--input", required=True, help="Input file path (TSV/CSV).")
    parser.add_argument("--output", default="docs/sentence-pool.imported.json")
    parser.add_argument("--delimiter", default="\t", help="Input delimiter (default: TAB).")
    parser.add_argument("--bg-column", type=int, default=0)
    parser.add_argument("--es-column", type=int, default=1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-items", type=int, default=2000)
    return parser.parse_args()


def clean_sentence(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return ""
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def sentence_id(prompt_bg: str, canonical_es: str) -> str:
    raw = f"{prompt_bg}::{canonical_es}".encode("utf-8")
    return "sent-open-" + hashlib.sha1(raw).hexdigest()[:16]


def infer_person(tokens: list[str]) -> str | None:
    if not tokens:
        return None

    first = tokens[0].lower()
    for key, pronoun in PERSON_PRONOUNS.items():
        if first == pronoun:
            return key
    return None


def infer_confidence_and_status(es_sentence: str) -> tuple[float, str]:
    lowered = es_sentence.lower()
    tokens = TOKEN_RE.findall(lowered)
    person_key = infer_person(tokens)

    verb_token = ""
    if person_key and len(tokens) > 1:
        verb_token = tokens[1]
    elif tokens:
        verb_token = tokens[0]

    confidence = 0.78
    if verb_token in KNOWN_PRESENT_FORMS:
        confidence = 0.92

    if any(marker in tokens for marker in NON_PRESENT_MARKERS):
        confidence = min(confidence, 0.65)

    status = APPROVED_STATUS if confidence >= 0.9 else PENDING_REVIEW_STATUS
    return confidence, status


def build_item(bg_sentence: str, es_sentence: str, rng: random.Random) -> dict:
    confidence, status = infer_confidence_and_status(es_sentence)

    tokens = TOKEN_RE.findall(es_sentence.lower())
    person_key = infer_person(tokens) or "unknown"
    accepted_answers = {es_sentence}
    if person_key != "unknown":
        pronoun = PERSON_PRONOUNS.get(person_key, "")
        if pronoun and es_sentence.lower().startswith(pronoun + " "):
            accepted_answers.add(es_sentence[len(pronoun) + 1 :].strip())

    return {
        "sentenceId": sentence_id(bg_sentence, es_sentence),
        "status": status,
        "statusRandKey": rng.randint(1, 1_000_000_000),
        "promptBg": bg_sentence,
        "canonicalEs": es_sentence,
        "acceptedEs": sorted(accepted_answers),
        "personKey": person_key,
        "verbLemma": "unknown",
        "domain": "open_corpus",
        "difficulty": 3,
        "tense": "present",
        "source": "open-corpus-import-v1",
        "confidence": round(confidence, 3),
        "tags": ["open-corpus", "bg-to-es", "daily-life"],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    imported: dict[str, dict] = {}

    with input_path.open("r", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter=args.delimiter)
        for row in reader:
            if len(imported) >= max(1, args.max_items):
                break

            if len(row) <= max(args.bg_column, args.es_column):
                continue

            bg_sentence = clean_sentence(row[args.bg_column])
            es_sentence = clean_sentence(row[args.es_column])
            if not bg_sentence or not es_sentence:
                continue

            item = build_item(bg_sentence, es_sentence, rng)
            imported[item["sentenceId"]] = item

    items = sorted(imported.values(), key=lambda item: item["sentenceId"])
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    approved = sum(1 for item in items if item["status"] == APPROVED_STATUS)
    pending = len(items) - approved
    print(f"Imported {len(items)} items from open corpus.")
    print(f"- {APPROVED_STATUS}: {approved}")
    print(f"- {PENDING_REVIEW_STATUS}: {pending}")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
