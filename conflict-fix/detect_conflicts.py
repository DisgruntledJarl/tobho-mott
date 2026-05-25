#!/usr/bin/env python3
"""Detect overlapping watch intervals in Trakt history."""

import argparse
import csv
from datetime import timedelta
from pathlib import Path

from trakt.csv import DEFAULT_CSV, load_rows

EPISODE_DURATION = timedelta(hours=1)
MOVIE_DURATION = timedelta(hours=3)


def watch_interval(watched_at, duration=EPISODE_DURATION):
    """Return ``(start, end)`` for a watch event that ends at ``watched_at``."""
    return watched_at - duration, watched_at


def intervals_overlap(a_start, a_end, b_start, b_end):
    """Return ``True`` when two intervals share any time."""
    return a_start < b_end and b_start < a_end

OUTPUT = Path(__file__).resolve().parent / "data" / "flagged_conflicts.csv"


def detect_conflicts(rows):
    """Return conflict dicts for every pair of overlapping watch intervals.

    Each dict has keys: row_a, row_b, overlap_minutes, a_start, b_start.
    Uses runtime from the row when present; falls back to MOVIE_DURATION /
    EPISODE_DURATION the same way build_blocked_intervals does.

    3-way (or N-way) pile-ups produce one dict per overlapping pair, so a
    3-way conflict yields three dicts: (A,B), (A,C), (B,C).
    """
    intervals = []
    for row in rows:
        raw_rt = row.get("runtime")
        if raw_rt:
            duration = timedelta(minutes=raw_rt)
        elif row["type"] == "movie":
            duration = MOVIE_DURATION
        else:
            duration = EPISODE_DURATION
        start, end = watch_interval(row["watched_dt"], duration)
        intervals.append((start, end, row))

    intervals.sort(key=lambda x: x[0])

    conflicts = []
    for i, (a_start, a_end, row_a) in enumerate(intervals):
        for j in range(i + 1, len(intervals)):
            b_start, b_end, row_b = intervals[j]
            if b_start >= a_end:
                break
            if intervals_overlap(a_start, a_end, b_start, b_end):
                overlap_min = round(
                    (min(a_end, b_end) - max(a_start, b_start)).total_seconds() / 60,
                    1,
                )
                conflicts.append(
                    dict(
                        row_a=row_a,
                        row_b=row_b,
                        overlap_minutes=overlap_min,
                        a_start=a_start,
                        b_start=b_start,
                    )
                )
    return conflicts


def row_runtime_minutes(row):
    raw_rt = row.get("runtime")
    if raw_rt:
        return raw_rt
    if row["type"] == "movie":
        return int(MOVIE_DURATION.total_seconds() // 60)
    return int(EPISODE_DURATION.total_seconds() // 60)


def row_title(row):
    if row["type"] == "episode":
        return (
            f"{row['show_name']} "
            f"S{row['season_number']:02d}E{row['episode_number']:02d}"
        )
    return row["movie_title"]


def conflict_to_csv_row(conflict):
    row_a = conflict["row_a"]
    row_b = conflict["row_b"]
    runtime_a = row_runtime_minutes(row_a)
    runtime_b = row_runtime_minutes(row_b)
    return {
        "history_id_a": row_a["history_id"],
        "history_id_b": row_b["history_id"],
        "type_a": row_a["type"],
        "type_b": row_b["type"],
        "title_a": row_title(row_a),
        "title_b": row_title(row_b),
        "watched_at_a": row_a["watched_at"],
        "watched_at_b": row_b["watched_at"],
        "runtime_a": runtime_a,
        "runtime_b": runtime_b,
        "computed_start_a": conflict["a_start"].isoformat(),
        "computed_start_b": conflict["b_start"].isoformat(),
        "overlap_minutes": conflict["overlap_minutes"],
    }


def print_summary(conflicts):
    print(f"Found {len(conflicts)} overlapping pair(s).")
    if not conflicts:
        return

    worst = max(conflicts, key=lambda c: c["overlap_minutes"])
    print(
        "Worst overlap: "
        f"{worst['overlap_minutes']} min — "
        f"{row_title(worst['row_a'])} vs {row_title(worst['row_b'])}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV, help="Watch history CSV")
    args = parser.parse_args()

    conflicts = detect_conflicts(load_rows(args.input))
    print_summary(conflicts)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "history_id_a",
        "history_id_b",
        "type_a",
        "type_b",
        "title_a",
        "title_b",
        "watched_at_a",
        "watched_at_b",
        "runtime_a",
        "runtime_b",
        "computed_start_a",
        "computed_start_b",
        "overlap_minutes",
    ]
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for conflict in conflicts:
            writer.writerow(conflict_to_csv_row(conflict))

    print(f"Wrote {len(conflicts)} conflict pair(s) to {OUTPUT}")


if __name__ == "__main__":
    main()
