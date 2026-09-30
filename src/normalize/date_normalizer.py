from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

REVIEW_DATE = "Review Date"


MONTH_NAMES = {
    "jan": 1,
    "ene": 1,
    "january": 1,
    "januar": 1,
    "januari": 1,
    "janvier": 1,
    "enero": 1,
    "janeiro": 1,
    "gennaio": 1,
    "feb": 2,
    "february": 2,
    "februar": 2,
    "februari": 2,
    "fevrier": 2,
    "février": 2,
    "febrero": 2,
    "febr": 2,
    "fevereiro": 2,
    "febbraio": 2,
    "mar": 3,
    "march": 3,
    "mars": 3,
    "marzo": 3,
    "março": 3,
    "marts": 3,
    "märz": 3,
    "apr": 4,
    "abr": 4,
    "april": 4,
    "avril": 4,
    "abril": 4,
    "aprile": 4,
    "may": 5,
    "mai": 5,
    "mayo": 5,
    "maggio": 5,
    "mei": 5,
    "maart": 3,
    "jun": 6,
    "june": 6,
    "juni": 6,
    "juin": 6,
    "junio": 6,
    "junho": 6,
    "giugno": 6,
    "jul": 7,
    "july": 7,
    "juli": 7,
    "juillet": 7,
    "julio": 7,
    "julho": 7,
    "luglio": 7,
    "aug": 8,
    "august": 8,
    "ago": 8,
    "aug": 8,
    "augustus": 8,
    "aout": 8,
    "août": 8,
    "agosto": 8,
    "set": 9,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "septembre": 9,
    "septiembre": 9,
    "setiembre": 9,
    "setembro": 9,
    "settembre": 9,
    "okt": 10,
    "oct": 10,
    "october": 10,
    "oktober": 10,
    "octobre": 10,
    "octubre": 10,
    "octubre": 10,
    "oct.": 10,
    "outubro": 10,
    "ottobre": 10,
    "nov": 11,
    "november": 11,
    "novembre": 11,
    "noviembre": 11,
    "novembro": 11,
    "dec": 12,
    "dic": 12,
    "december": 12,
    "des": 12,
    "desember": 12,
    "decemer" : 12,
    "dezember": 12,
    "decembre": 12,
    "décembre": 12,
    "diciembre": 12,
    "dezembro": 12,
    "dicembre": 12,
}

FILLER_TOKENS = {
    "de",
    "del",
    "den",
    "the",
}

DATE_FIELD_NAMES = [
    "invoice_date",
    "consumption_start_date_1",
    "consumption_end_date_1",
    "consumption_start_date_2",
    "consumption_end_date_2",
]

DATE_LIKE_RE = re.compile(r"\d{1,4}(?:\s*[/.\-]\s*|\s+)\d{1,2}(?:\s*[/.\-]\s*|\s+)\d{1,4}|\d{1,2}(?:\s*[/.\-]\s*|\s+)(?:[A-Za-zÀ-ÿ]+\.?\s+)*(?:[A-Za-zÀ-ÿ]+\.?)(?:\s*[/.\-]\s*|\s+)(?:[A-Za-zÀ-ÿ]+\.?\s+)*\d{2,4}|[A-Za-zÀ-ÿ]+\.?(?:\s*[/.\-]\s*|\s+)\d{2,4}|[A-Za-zÀ-ÿ]+\.?(?:\s*[/.\-]\s*|\s+)\d{1,2},?(?:\s*[/.\-]\s*|\s+)\d{2,4}")
TIME_RE = re.compile(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?\s*(?P<ampm>am|pm)?", re.IGNORECASE)
TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ]+|\d{1,4}")


@dataclass(frozen=True)
class ParsedDate:
    year: int
    month: int
    day: int
    ambiguous: bool = False


def normalize_date(value: Any) -> Any:
    if _is_blank(value):
        return value

    text = str(value).strip()
    if not _looks_date_like(text):
        return value

    add_day = _has_day_rollover_time(text)
    text_without_time = TIME_RE.sub("", text).strip()
    text_without_time = text_without_time.rstrip("T,")

    parsed = _parse_date_text(text_without_time)
    if parsed is None:
        return REVIEW_DATE

    try:
        normalized_date = date(parsed.year, parsed.month, parsed.day)
    except ValueError:
        return REVIEW_DATE

    if add_day:
        normalized_date = normalized_date + timedelta(days=1)

    return _format_normalized_date(normalized_date, parsed.ambiguous)


def date_candidates(value: Any) -> list[date]:
    if _is_blank(value):
        return []

    text = str(value).strip()
    if not _looks_date_like(text):
        return []

    add_day = _has_day_rollover_time(text)
    text_without_time = TIME_RE.sub("", text).strip()
    text_without_time = text_without_time.rstrip("T,")

    parsed_dates = _parse_date_candidates(text_without_time)
    candidates = []
    for parsed in parsed_dates:
        try:
            candidate = date(parsed.year, parsed.month, parsed.day)
        except ValueError:
            continue
        if add_day:
            candidate = candidate + timedelta(days=1)
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def _looks_date_like(text: str) -> bool:
    if DATE_LIKE_RE.search(text):
        return True

    tokens = _meaningful_tokens(_clean_text(text))
    if len(tokens) < 2:
        return False
    has_month_name = any(_month_number(token) for token in tokens)
    digit_count = sum(1 for token in tokens if token.isdigit())
    return has_month_name and digit_count >= 1


def _format_normalized_date(normalized_date: date, ambiguous: bool) -> str:
    return normalized_date.isoformat()


def _has_day_rollover_time(text: str) -> bool:
    match = TIME_RE.search(text)
    if not match:
        return False

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second") or "0")
    ampm = match.group("ampm")

    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

    return hour == 23 and minute == 59 and 0 <= second <= 59


def _parse_date_text(text: str) -> ParsedDate | None:
    text = _clean_text(text)
    tokens = _meaningful_tokens(text)
    if len(tokens) < 2:
        return None

    first_three = tokens[:3]
    month_positions = [_month_number(token) for token in first_three]
    if any(month_positions):
        return _parse_month_name_tokens(first_three, month_positions)

    if len(first_three) < 3:
        return None
    if not all(token.isdigit() for token in first_three):
        return None
    return _parse_numeric_tokens([int(token) for token in first_three])


def _parse_date_candidates(text: str) -> list[ParsedDate]:
    parsed = _parse_date_text(text)
    if parsed is None:
        return []

    candidates = [parsed]
    if parsed.ambiguous:
        swapped = ParsedDate(
            year=parsed.year,
            month=parsed.day,
            day=parsed.month,
            ambiguous=True,
        )
        candidates.append(swapped)
    return candidates


def _clean_text(text: str) -> str:
    cleaned = text.strip()
    if "T" in cleaned:
        cleaned = cleaned.split("T", 1)[0]
    return cleaned.replace(",", " ")


def _month_number(token: str) -> int | None:
    key = token.lower().rstrip(".")
    return MONTH_NAMES.get(key)


def _meaningful_tokens(text: str) -> list[str]:
    tokens = TOKEN_RE.findall(text)
    return [token for token in tokens if token.lower().rstrip(".") not in FILLER_TOKENS]


def _parse_month_name_tokens(tokens: list[str], month_positions: list[int | None]) -> ParsedDate | None:
    month_index = next(index for index, month in enumerate(month_positions) if month is not None)
    month = month_positions[month_index]
    numeric_tokens = [(index, int(token)) for index, token in enumerate(tokens) if index != month_index and token.isdigit()]
    if month is None:
        return None

    if len(numeric_tokens) == 1:
        _, year_number = numeric_tokens[0]
        return ParsedDate(year=_expand_year(year_number), month=month, day=1)

    if len(numeric_tokens) != 2:
        return None

    first_index, first_number = numeric_tokens[0]
    second_index, second_number = numeric_tokens[1]

    if month_index == 0:
        day = first_number
        year = _expand_year(second_number)
    elif month_index == 1:
        if first_number > 31:
            year = _expand_year(first_number)
            day = second_number
        else:
            day = first_number
            year = _expand_year(second_number)
    elif second_index < month_index:
        year = _expand_year(first_number)
        day = second_number
    else:
        return None

    return ParsedDate(year=year, month=month, day=day)


def _parse_numeric_tokens(parts: list[int]) -> ParsedDate | None:
    first, second, third = parts

    if first > 999:
        return ParsedDate(year=_expand_year(first), month=second, day=third)

    if _is_minguo_year(first, second, third):
        return ParsedDate(year=first + 1911, month=second, day=third)

    if third > 31:
        year = _expand_year(third)
        if first <= 12 and second <= 12:
            return ParsedDate(year=year, month=first, day=second, ambiguous=True)
        if first > 12:
            return ParsedDate(year=year, month=second, day=first)
        return ParsedDate(year=year, month=first, day=second)

    if third <= 99:
        year = _expand_year(third)
        if first <= 12 and second <= 12:
            return ParsedDate(year=year, month=first, day=second, ambiguous=True)
        if first > 12:
            return ParsedDate(year=year, month=second, day=first)
        return ParsedDate(year=year, month=first, day=second)

    return None


def _is_minguo_year(first: int, second: int, third: int) -> bool:
    return 100 <= first <= 199 and 1 <= second <= 12 and 1 <= third <= 31


def _expand_year(year: int) -> int:
    if year < 100:
        return 2000 + year
    return year
