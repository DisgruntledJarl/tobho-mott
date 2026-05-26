#!/usr/bin/env python3
"""Detect overlapping watch intervals in Trakt history."""

from trakt.csv_to_python import load_rows
from trakt.intervals import row_interval


def detect_conflicts(rows):
    """Return conflict dicts for every pair of overlapping watch intervals.

    Each dict has keys: row_a, row_b.
    Uses runtime from the row when present; falls back to default episode/movie
    durations from trakt.intervals.

    3-way (or N-way) pile-ups produce one dict per overlapping pair, so a
    3-way conflict yields three dicts: (A,B), (A,C), (B,C).
    """
    intervals = sorted(
        ((*row_interval(row), row) for row in rows),
        key=lambda item: item[0],
    )
    conflicts = []

    # Sweep line: sorted by start time; stop inner loop once b starts at/after a ends.
    for i, (_, a_end, row_a) in enumerate(intervals):
        for b_start, _, row_b in intervals[i + 1 :]:
            if b_start >= a_end:
                break
            conflicts.append({"row_a": row_a, "row_b": row_b})
    return conflicts


def main():
    conflicts = detect_conflicts(load_rows())
    n = len(conflicts)
    if n == 0:
        print("No overlapping watch intervals found.")
        return
    print(f"Found {n} overlapping pair(s).")


if __name__ == "__main__":
    main()
