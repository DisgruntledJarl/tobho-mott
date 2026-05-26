#!/usr/bin/env python3
"""Reschedule first-watch episodes for a show season into a date range."""

import random
from datetime import datetime, timedelta, timezone

from trakt.episodes import split_first_watch
from trakt.intervals import row_duration, row_title


def parse_date_range(start, end):
    """Return UTC start-of-day and end-of-day datetimes for ``YYYY-MM-DD`` strings."""
    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )
    if end_dt < start_dt:
        raise ValueError(f"End date {end!r} is before start date {start!r}")
    return start_dt, end_dt


def find_season_rows(rows, show_query, season):
    """Return first-watch episodes for a unique show match, sorted by episode number."""
    query = show_query.casefold()
    matched = [
        row
        for row in rows
        if row["type"] == "episode" and query in row["show_name"].casefold()
    ]

    if not matched:
        raise ValueError(f"No show matches {show_query!r}")

    show_ids = {row["show_id"] for row in matched}
    if len(show_ids) > 1:
        names = sorted({row["show_name"] for row in matched})
        raise ValueError(
            f"Multiple shows match {show_query!r}: {', '.join(names)}"
        )

    season_rows = [row for row in matched if row["season_number"] == season]
    first_watch, _ = split_first_watch(season_rows)
    first_watch.sort(key=lambda row: row["episode_number"])

    if not first_watch:
        raise ValueError(
            f"No first-watch episodes found for {show_query!r} season {season}"
        )

    return first_watch


def generate_target_times(episodes, start_dt, end_dt):
    """Return one random end time per episode, spread across equal slots in order."""
    n = len(episodes)
    if n == 0:
        return []

    range_size = end_dt - start_dt
    durations = [row_duration(episode) for episode in episodes]
    total_duration = sum(durations, timedelta())

    if total_duration > range_size:
        raise ValueError(
            f"Total episode runtime ({total_duration}) exceeds date range "
            f"({range_size})"
        )

    slot_size = range_size / n
    target_times = []

    for episode, duration in zip(episodes, durations):
        if duration > slot_size:
            raise ValueError(
                f"{row_title(episode)} runtime ({duration}) exceeds slot size "
                f"({slot_size})"
            )
        slot_index = len(target_times)
        slot_start = start_dt + slot_size * slot_index
        offset = random.random() * (slot_size - duration)
        target_times.append(slot_start + duration + offset)

    return target_times
