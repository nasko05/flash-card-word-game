import re
import unicodedata

SPANISH_VOWELS = {"a", "e", "i", "o", "u"}
EDGE_PUNCTUATION = " .,!?:;\"'()[]{}\u00bf\u00a1"


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def strip_edge_punctuation(value: str) -> str:
    return value.strip(EDGE_PUNCTUATION)


def normalize_sentence_strict(value: str) -> str:
    normalized = normalize_whitespace(value)
    normalized = strip_edge_punctuation(normalized)
    return unicodedata.normalize("NFC", normalized)


def remove_vowel_diacritics(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    rebuilt: list[str] = []
    previous_base = ""

    for char in decomposed:
        if unicodedata.combining(char):
            if previous_base in SPANISH_VOWELS:
                continue
            rebuilt.append(char)
            continue

        rebuilt.append(char)
        previous_base = char

    return unicodedata.normalize("NFC", "".join(rebuilt))


def normalize_sentence_relaxed(value: str) -> str:
    strict = normalize_sentence_strict(value).lower()
    return remove_vowel_diacritics(strict)


def safe_sentence_list(value) -> list[str]:
    if not isinstance(value, list):
        return []

    cleaned: list[str] = []
    for candidate in value:
        if isinstance(candidate, str) and candidate.strip():
            cleaned.append(candidate)
    return cleaned


def evaluate_spanish_answer(answer: str, accepted_answers: list[str]) -> tuple[str, str]:
    strict_answer = normalize_sentence_strict(answer)
    strict_expected = {normalize_sentence_strict(candidate) for candidate in accepted_answers}
    if strict_answer in strict_expected:
        return "exact", "Correct."

    relaxed_answer = normalize_sentence_relaxed(answer)
    relaxed_expected = {normalize_sentence_relaxed(candidate) for candidate in accepted_answers}
    if relaxed_answer in relaxed_expected:
        return "warning", "Correct, but be careful with accent or case."

    return "wrong", "Incorrect. Review the expected answer and continue."
