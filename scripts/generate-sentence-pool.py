#!/usr/bin/env python3
"""Generate natural present-tense BG->ES sentence exercises."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

APPROVED_STATUS = "APPROVED"
PENDING_REVIEW_STATUS = "PENDING_REVIEW"


@dataclass(frozen=True)
class Person:
    key: str
    bg_subject: str
    es_subject: str


PERSONS: list[Person] = [
    Person("yo", "Аз", "yo"),
    Person("tu", "Ти", "t\u00fa"),
    Person("el", "Той", "\u00e9l"),
    Person("ella", "Тя", "ella"),
    Person("nosotros", "Ние", "nosotros"),
    Person("vosotros", "Вие", "vosotros"),
    Person("ellos", "Те", "ellos"),
]

VERBS: list[dict] = [
    {
        "lemma": "trabajar",
        "domain": "work",
        "difficulty": 1,
        "bg_present": {
            "yo": "работя",
            "tu": "работиш",
            "el": "работи",
            "ella": "работи",
            "nosotros": "работим",
            "vosotros": "работите",
            "ellos": "работят",
        },
        "es_present": {
            "yo": "trabajo",
            "tu": "trabajas",
            "el": "trabaja",
            "ella": "trabaja",
            "nosotros": "trabajamos",
            "vosotros": "trabaj\u00e1is",
            "ellos": "trabajan",
        },
        "objects": [
            {"bg": "в офис", "es": "en una oficina"},
            {"bg": "от вкъщи", "es": "desde casa"},
            {"bg": "в екип", "es": "en equipo"},
        ],
        "contexts": [
            {"bg": "всяка сутрин", "es": "cada ma\u00f1ana"},
            {"bg": "днес", "es": "hoy"},
            {"bg": "следобед", "es": "por la tarde"},
        ],
    },
    {
        "lemma": "estudiar",
        "domain": "education",
        "difficulty": 1,
        "bg_present": {
            "yo": "уча",
            "tu": "учиш",
            "el": "учи",
            "ella": "учи",
            "nosotros": "учим",
            "vosotros": "учите",
            "ellos": "учат",
        },
        "es_present": {
            "yo": "estudio",
            "tu": "estudias",
            "el": "estudia",
            "ella": "estudia",
            "nosotros": "estudiamos",
            "vosotros": "estudi\u00e1is",
            "ellos": "estudian",
        },
        "objects": [
            {"bg": "испански", "es": "espa\u00f1ol"},
            {"bg": "за изпита", "es": "para el examen"},
            {"bg": "нова тема", "es": "un tema nuevo"},
        ],
        "contexts": [
            {"bg": "в библиотеката", "es": "en la biblioteca"},
            {"bg": "всяка вечер", "es": "cada noche"},
            {"bg": "след работа", "es": "despu\u00e9s del trabajo"},
        ],
    },
    {
        "lemma": "cocinar",
        "domain": "home",
        "difficulty": 1,
        "bg_present": {
            "yo": "готвя",
            "tu": "готвиш",
            "el": "готви",
            "ella": "готви",
            "nosotros": "готвим",
            "vosotros": "готвите",
            "ellos": "готвят",
        },
        "es_present": {
            "yo": "cocino",
            "tu": "cocinas",
            "el": "cocina",
            "ella": "cocina",
            "nosotros": "cocinamos",
            "vosotros": "cocin\u00e1is",
            "ellos": "cocinan",
        },
        "objects": [
            {"bg": "вечеря", "es": "la cena"},
            {"bg": "супа", "es": "sopa"},
            {"bg": "паста", "es": "pasta"},
        ],
        "contexts": [
            {"bg": "за семейството", "es": "para la familia"},
            {"bg": "вкъщи", "es": "en casa"},
            {"bg": "в момента", "es": "ahora mismo"},
        ],
    },
    {
        "lemma": "comprar",
        "domain": "shopping",
        "difficulty": 1,
        "bg_present": {
            "yo": "купувам",
            "tu": "купуваш",
            "el": "купува",
            "ella": "купува",
            "nosotros": "купуваме",
            "vosotros": "купувате",
            "ellos": "купуват",
        },
        "es_present": {
            "yo": "compro",
            "tu": "compras",
            "el": "compra",
            "ella": "compra",
            "nosotros": "compramos",
            "vosotros": "compr\u00e1is",
            "ellos": "compran",
        },
        "objects": [
            {"bg": "хляб", "es": "pan"},
            {"bg": "плодове", "es": "fruta"},
            {"bg": "кафе", "es": "caf\u00e9"},
        ],
        "contexts": [
            {"bg": "в супермаркета", "es": "en el supermercado"},
            {"bg": "за седмицата", "es": "para la semana"},
            {"bg": "сутрин", "es": "por la ma\u00f1ana"},
        ],
    },
    {
        "lemma": "beber",
        "domain": "daily_life",
        "difficulty": 1,
        "bg_present": {
            "yo": "пия",
            "tu": "пиеш",
            "el": "пие",
            "ella": "пие",
            "nosotros": "пием",
            "vosotros": "пиете",
            "ellos": "пият",
        },
        "es_present": {
            "yo": "bebo",
            "tu": "bebes",
            "el": "bebe",
            "ella": "bebe",
            "nosotros": "bebemos",
            "vosotros": "beb\u00e9is",
            "ellos": "beben",
        },
        "objects": [
            {"bg": "вода", "es": "agua"},
            {"bg": "чай", "es": "t\u00e9"},
            {"bg": "кафе", "es": "caf\u00e9"},
        ],
        "contexts": [
            {"bg": "следобед", "es": "por la tarde"},
            {"bg": "на закуска", "es": "en el desayuno"},
            {"bg": "в офиса", "es": "en la oficina"},
        ],
    },
    {
        "lemma": "leer",
        "domain": "leisure",
        "difficulty": 1,
        "bg_present": {
            "yo": "чета",
            "tu": "четеш",
            "el": "чете",
            "ella": "чете",
            "nosotros": "четем",
            "vosotros": "четете",
            "ellos": "четат",
        },
        "es_present": {
            "yo": "leo",
            "tu": "lees",
            "el": "lee",
            "ella": "lee",
            "nosotros": "leemos",
            "vosotros": "le\u00e9is",
            "ellos": "leen",
        },
        "objects": [
            {"bg": "книга", "es": "un libro"},
            {"bg": "статия", "es": "un art\u00edculo"},
            {"bg": "новини", "es": "noticias"},
        ],
        "contexts": [
            {"bg": "вечер", "es": "por la noche"},
            {"bg": "в метрото", "es": "en el metro"},
            {"bg": "преди сън", "es": "antes de dormir"},
        ],
    },
    {
        "lemma": "escribir",
        "domain": "work",
        "difficulty": 2,
        "bg_present": {
            "yo": "пиша",
            "tu": "пишеш",
            "el": "пише",
            "ella": "пише",
            "nosotros": "пишем",
            "vosotros": "пишете",
            "ellos": "пишат",
        },
        "es_present": {
            "yo": "escribo",
            "tu": "escribes",
            "el": "escribe",
            "ella": "escribe",
            "nosotros": "escribimos",
            "vosotros": "escrib\u00eds",
            "ellos": "escriben",
        },
        "objects": [
            {"bg": "имейл", "es": "un correo"},
            {"bg": "съобщение", "es": "un mensaje"},
            {"bg": "доклад", "es": "un informe"},
        ],
        "contexts": [
            {"bg": "на работа", "es": "en el trabajo"},
            {"bg": "на телефона", "es": "en el tel\u00e9fono"},
            {"bg": "в момента", "es": "ahora"},
        ],
    },
    {
        "lemma": "ir",
        "domain": "travel",
        "difficulty": 2,
        "bg_present": {
            "yo": "отивам",
            "tu": "отиваш",
            "el": "отива",
            "ella": "отива",
            "nosotros": "отиваме",
            "vosotros": "отивате",
            "ellos": "отиват",
        },
        "es_present": {
            "yo": "voy",
            "tu": "vas",
            "el": "va",
            "ella": "va",
            "nosotros": "vamos",
            "vosotros": "vais",
            "ellos": "van",
        },
        "objects": [
            {"bg": "на работа", "es": "al trabajo"},
            {"bg": "до магазина", "es": "a la tienda"},
            {"bg": "до фитнеса", "es": "al gimnasio"},
        ],
        "contexts": [
            {"bg": "сега", "es": "ahora"},
            {"bg": "всеки ден", "es": "cada d\u00eda"},
            {"bg": "след малко", "es": "en un rato"},
        ],
    },
    {
        "lemma": "tener",
        "domain": "daily_life",
        "difficulty": 2,
        "bg_present": {
            "yo": "имам",
            "tu": "имаш",
            "el": "има",
            "ella": "има",
            "nosotros": "имаме",
            "vosotros": "имате",
            "ellos": "имат",
        },
        "es_present": {
            "yo": "tengo",
            "tu": "tienes",
            "el": "tiene",
            "ella": "tiene",
            "nosotros": "tenemos",
            "vosotros": "ten\u00e9is",
            "ellos": "tienen",
        },
        "objects": [
            {"bg": "среща", "es": "una reuni\u00f3n"},
            {"bg": "време", "es": "tiempo"},
            {"bg": "много работа", "es": "mucho trabajo"},
        ],
        "contexts": [
            {"bg": "днес", "es": "hoy"},
            {"bg": "сутринта", "es": "esta ma\u00f1ana"},
            {"bg": "в момента", "es": "ahora"},
        ],
    },
    {
        "lemma": "hacer",
        "domain": "daily_life",
        "difficulty": 2,
        "bg_present": {
            "yo": "правя",
            "tu": "правиш",
            "el": "прави",
            "ella": "прави",
            "nosotros": "правим",
            "vosotros": "правите",
            "ellos": "правят",
        },
        "es_present": {
            "yo": "hago",
            "tu": "haces",
            "el": "hace",
            "ella": "hace",
            "nosotros": "hacemos",
            "vosotros": "hac\u00e9is",
            "ellos": "hacen",
        },
        "objects": [
            {"bg": "упражнения", "es": "ejercicio"},
            {"bg": "закуска", "es": "el desayuno"},
            {"bg": "план за деня", "es": "el plan del d\u00eda"},
        ],
        "contexts": [
            {"bg": "рано сутрин", "es": "temprano por la ma\u00f1ana"},
            {"bg": "вкъщи", "es": "en casa"},
            {"bg": "всяка вечер", "es": "cada noche"},
        ],
    },
    {
        "lemma": "hablar",
        "domain": "social",
        "difficulty": 1,
        "bg_present": {
            "yo": "говоря",
            "tu": "говориш",
            "el": "говори",
            "ella": "говори",
            "nosotros": "говорим",
            "vosotros": "говорите",
            "ellos": "говорят",
        },
        "es_present": {
            "yo": "hablo",
            "tu": "hablas",
            "el": "habla",
            "ella": "habla",
            "nosotros": "hablamos",
            "vosotros": "habl\u00e1is",
            "ellos": "hablan",
        },
        "objects": [
            {"bg": "с колега", "es": "con un compa\u00f1ero"},
            {"bg": "с приятели", "es": "con amigos"},
            {"bg": "по телефона", "es": "por tel\u00e9fono"},
        ],
        "contexts": [
            {"bg": "в момента", "es": "ahora"},
            {"bg": "в офиса", "es": "en la oficina"},
            {"bg": "след работа", "es": "despu\u00e9s del trabajo"},
        ],
    },
    {
        "lemma": "vivir",
        "domain": "home",
        "difficulty": 1,
        "bg_present": {
            "yo": "живея",
            "tu": "живееш",
            "el": "живее",
            "ella": "живее",
            "nosotros": "живеем",
            "vosotros": "живеете",
            "ellos": "живеят",
        },
        "es_present": {
            "yo": "vivo",
            "tu": "vives",
            "el": "vive",
            "ella": "vive",
            "nosotros": "vivimos",
            "vosotros": "viv\u00eds",
            "ellos": "viven",
        },
        "objects": [
            {"bg": "в голям град", "es": "en una ciudad grande"},
            {"bg": "близо до парка", "es": "cerca del parque"},
            {"bg": "в малък апартамент", "es": "en un piso peque\u00f1o"},
        ],
        "contexts": [
            {"bg": "в момента", "es": "ahora"},
            {"bg": "със семейството си", "es": "con mi familia"},
            {"bg": "от няколко години", "es": "desde hace varios a\u00f1os"},
        ],
    },
    {
        "lemma": "poder",
        "domain": "daily_life",
        "difficulty": 2,
        "bg_present": {
            "yo": "мога",
            "tu": "можеш",
            "el": "може",
            "ella": "може",
            "nosotros": "можем",
            "vosotros": "можете",
            "ellos": "могат",
        },
        "es_present": {
            "yo": "puedo",
            "tu": "puedes",
            "el": "puede",
            "ella": "puede",
            "nosotros": "podemos",
            "vosotros": "pod\u00e9is",
            "ellos": "pueden",
        },
        "objects": [
            {"bg": "да дойда по-рано", "es": "venir m\u00e1s temprano"},
            {"bg": "да помогна", "es": "ayudar"},
            {"bg": "да остана още малко", "es": "quedarme un poco m\u00e1s"},
        ],
        "contexts": [
            {"bg": "днес", "es": "hoy"},
            {"bg": "следобед", "es": "esta tarde"},
            {"bg": "ако е нужно", "es": "si hace falta"},
        ],
    },
]

IRREGULAR_VERBS = {"ir", "tener", "hacer", "poder"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate sentence pool JSON.")
    parser.add_argument(
        "--output",
        default="docs/sentence-pool.generated.json",
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--samples-per-person",
        type=int,
        default=3,
        help="How many sentence combinations to generate per person/verb.",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def sentence_id(prompt_bg: str, canonical_es: str) -> str:
    raw = f"{prompt_bg}::{canonical_es}".encode("utf-8")
    return "sent-" + hashlib.sha1(raw).hexdigest()[:16]


def build_sentence_item(
    person: Person,
    verb: dict,
    obj: dict,
    context: dict,
    rng: random.Random,
) -> dict:
    bg_sentence = f"{person.bg_subject} {verb['bg_present'][person.key]} {obj['bg']} {context['bg']}."
    es_with_subject = (
        f"{person.es_subject} {verb['es_present'][person.key]} {obj['es']} {context['es']}."
    )
    es_without_subject = f"{verb['es_present'][person.key]} {obj['es']} {context['es']}."

    canonical = es_with_subject
    accepted = sorted({es_with_subject, es_without_subject})

    base_confidence = 0.96
    if verb["lemma"] in IRREGULAR_VERBS:
        base_confidence = 0.9
    confidence = round(base_confidence - rng.uniform(0.0, 0.04), 3)
    status = APPROVED_STATUS if confidence >= 0.93 else PENDING_REVIEW_STATUS

    return {
        "sentenceId": sentence_id(bg_sentence, canonical),
        "status": status,
        "statusRandKey": rng.randint(1, 1_000_000_000),
        "promptBg": bg_sentence,
        "canonicalEs": canonical,
        "acceptedEs": accepted,
        "personKey": person.key,
        "verbLemma": verb["lemma"],
        "domain": verb["domain"],
        "difficulty": verb["difficulty"],
        "tense": "present",
        "source": "rule-based-v1",
        "confidence": confidence,
        "tags": [verb["domain"], "daily-life", "bg-to-es", "present-tense"],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def build_pool(samples_per_person: int, rng: random.Random) -> list[dict]:
    by_id: dict[str, dict] = {}

    for verb in VERBS:
        for person in PERSONS:
            combinations = [
                (obj, context)
                for obj in verb["objects"]
                for context in verb["contexts"]
            ]
            rng.shuffle(combinations)
            for obj, context in combinations[:samples_per_person]:
                item = build_sentence_item(person, verb, obj, context, rng)
                by_id[item["sentenceId"]] = item

    return list(by_id.values())


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    if args.samples_per_person < 1:
        raise SystemExit("--samples-per-person must be >= 1")

    pool = build_pool(args.samples_per_person, rng)
    pool.sort(key=lambda item: item["sentenceId"])

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")

    approved = sum(1 for item in pool if item["status"] == APPROVED_STATUS)
    pending = len(pool) - approved
    print(
        f"Generated {len(pool)} sentence exercises: {approved} APPROVED, {pending} PENDING_REVIEW."
    )
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
