from __future__ import annotations

import re
from typing import Any

EDGE_CHARS = " \t\r\n\"'`.,;:()[]{}<>|\\/"
SEPARATOR_RE = re.compile(r"[-_]+")
WHITESPACE_RE = re.compile(r"\s+")
UNIT_TOKEN_RE = re.compile(r"[^A-Z0-9]+")

ENERGY_UNIT_ALIASES = {
    "KWH": "KWH",
    "KW H": "KWH",
    "KW-H": "KWH",
    "KILOWATT HOUR": "KWH",
    "KILOWATT HOURS": "KWH",
    "MWH": "MWH",
    "MW H": "MWH",
    "MW-H": "MWH",
    "MEGAWATT HOUR": "MWH",
    "MEGAWATT HOURS": "MWH",
    "TON": "TON",
    "TONS": "TON",
    "RTH": "RTH",
}

ENERGY_UNIT_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:"
    + "|".join(re.escape(alias) for alias in sorted(ENERGY_UNIT_ALIASES, key=len, reverse=True))
    + r")(?![A-Z0-9])"
)

UPPERCASE_TOKENS = {
    "A/S",
    "AS",
    "ASA",
    "BV",
    "CO",
    "CORP",
    "DMCC",
    "E.S.P",
    "E.S.P.",
    "GMBH",
    "INC",
    "KZN",
    "LLC",
    "LP",
    "LTD",
    "LT",
    "NV",
    "PLC",
    "PTY",
    "S.A",
    "S.A.",
    "SAS",
    "UK",
    "USA",
}


def clean_proper_text(value: Any) -> Any:
    cleaned = _clean_base_text(value)
    if cleaned in (None, ""):
        return cleaned
    return _smart_proper_case(cleaned)


def clean_upper_text(value: Any) -> Any:
    cleaned = _clean_base_text(value)
    if cleaned in (None, ""):
        return cleaned
    return cleaned.upper()


def clean_energy_unit(value: Any) -> Any:
    cleaned = _clean_base_text(value)
    if cleaned in (None, ""):
        return cleaned

    upper_unit = cleaned.upper()
    normalized_key = UNIT_TOKEN_RE.sub(" ", upper_unit).strip()
    normalized_key = WHITESPACE_RE.sub(" ", normalized_key)
    # Extract one distinct supported unit from descriptive OCR text.
    # Rates such as kWh/m3 and labels naming different units are not quantities.
    for match in ENERGY_UNIT_PATTERN.finditer(upper_unit):
        before = upper_unit[:match.start()].rstrip()
        after = upper_unit[match.end():].lstrip()
        if before.endswith("/") or after.startswith("/") or after.startswith("PER "):
            return ""
    units = {ENERGY_UNIT_ALIASES[match.group()] for match in ENERGY_UNIT_PATTERN.finditer(normalized_key)}
    return units.pop() if len(units) == 1 else ""


def _clean_base_text(value: Any) -> Any:
    if value is None:
        return None

    text = str(value)
    text = SEPARATOR_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    text = text.strip(EDGE_CHARS)
    text = WHITESPACE_RE.sub(" ", text)
    return text


def _smart_proper_case(text: str) -> str:
    return " ".join(_format_word(word) for word in text.split(" "))


def _format_word(word: str) -> str:
    if word.upper() in UPPERCASE_TOKENS:
        return word.upper()
    if "." in word:
        return word.upper()
    return word[:1].upper() + word[1:].lower()
