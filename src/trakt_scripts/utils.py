"""utility helpers"""

import difflib
import re
import sys
from datetime import timedelta

EPISODE_DURATION = timedelta(hours=1)
MOVIE_DURATION = timedelta(hours=3)

"""Input Helper to deal with EOF Error"""


def safe_input(prompt=""):
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def row_duration(row):
    if row["runtime"]:
        return timedelta(minutes=row["runtime"])
    return MOVIE_DURATION if row["type"] == "movie" else EPISODE_DURATION


def row_interval(row):
    end = row["watched_dt"]
    return end - row_duration(row), end


def row_title(row):
    if row["type"] == "episode":
        return (
            f"{row['show_name']} "
            f"S{row['season_number']:02d}E{row['episode_number']:02d}"
        )
    return row["movie_title"]


def normalize_show_name(name):
    """Return lowercase name with punctuation removed for matching."""
    return re.sub(r"[^\w\s]", "", name.casefold())


def build_show_name_map(rows):
    """Return normalized show name -> (original show name, show_id)."""
    show_map = {}
    for row in rows:
        if row["type"] != "episode":
            continue
        show_name = row["show_name"]
        if not show_name:
            continue
        show_map[normalize_show_name(show_name)] = (show_name, row["show_id"])
    return show_map


def find_show_matches(query, show_map):
    """Return (show_name, show_id) candidates: exact, then substring, then fuzzy."""
    normalized = normalize_show_name(query)

    if normalized in show_map:
        return [show_map[normalized]]

    # SubString matching if exact match not found
    # Searches for multiple entries and returns all of them. Only adds to candidates if the value is not already in the set.
    candidates = []
    seen_ids = set()
    for key, value in show_map.items():
        if normalized in key or key in normalized:
            show_id = value[1]
            if show_id not in seen_ids:
                seen_ids.add(show_id)
                candidates.append(value)
    if candidates:
        return candidates

    # Fuzzy matching
    for key in difflib.get_close_matches(normalized, show_map, n=5, cutoff=0.6):
        value = show_map[key]
        show_id = value[1]
        if show_id not in seen_ids:
            seen_ids.add(show_id)
            candidates.append(value)
    return candidates
