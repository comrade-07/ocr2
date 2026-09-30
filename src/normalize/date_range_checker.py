from __future__ import annotations

from datetime import date
from typing import Any

from src.normalize.date_normalizer import date_candidates, normalize_date

PREFERRED_RANGE_MIN_DAYS = 20
PREFERRED_RANGE_MAX_DAYS = 45


def normalize_start_date_against_end(start_value: Any, end_value: Any) -> Any:
    selected_start, _ = normalize_date_range(start_value, end_value)
    return selected_start


def normalize_date_range(start_value: Any, end_value: Any) -> tuple[Any, Any]:
    start_candidates = date_candidates(start_value)
    end_candidates = date_candidates(end_value)

    normalized_start = normalize_date(start_value)
    normalized_end = normalize_date(end_value)
    if not start_candidates or not end_candidates:
        return normalized_start, normalized_end

    selected = _select_date_pair(start_candidates, end_candidates)
    if selected is None:
        return normalized_start, normalized_end
    selected_start, selected_end = selected
    return selected_start.isoformat(), selected_end.isoformat()


def _select_start_candidate(start_candidates: list[date], end_candidates: list[date]) -> date | None:
    selected = _select_date_pair(start_candidates, end_candidates)
    if selected is None:
        return None
    return selected[0]


def _select_date_pair(start_candidates: list[date], end_candidates: list[date]) -> tuple[date, date] | None:
    viable_pairs = [
        (start, end)
        for start in start_candidates
        for end in end_candidates
        if start <= end
    ]
    if not viable_pairs:
        return None

    preferred_pairs = [
        (start, end)
        for start, end in viable_pairs
        if PREFERRED_RANGE_MIN_DAYS <= (end - start).days <= PREFERRED_RANGE_MAX_DAYS
    ]
    if len(preferred_pairs) == 1:
        return preferred_pairs[0]

    same_month_starts = {
        start
        for start, end in viable_pairs
        if start.year == end.year and start.month == end.month
    }
    if len(same_month_starts) == 1:
        start = next(iter(same_month_starts))
        same_month_ends = [end for candidate_start, end in viable_pairs if candidate_start == start]
        return start, min(same_month_ends)

    ranked = sorted(
        viable_pairs,
        key=lambda pair: (
            pair[1] - pair[0],
            0 if pair[0].year == pair[1].year else 1,
            0 if pair[0].month == pair[1].month else 1,
        ),
    )
    best_start, best_end = ranked[0]
    best_distance = best_end - best_start
    if sum(1 for start, end in viable_pairs if end - start == best_distance) > 1:
        return None
    return best_start, best_end
