#!/usr/bin/env python3
"""Detect overlapping watch intervals and optionally reschedule them on Trakt."""

from trakt.utils import safe_input as input, row_duration, row_interval, row_title
from trakt.client import TraktRateLimitError, to_trakt_iso, trakt_post
from trakt.csv_to_python import load_rows
from trakt.history import fetch_watch_history

def detect_conflicts(rows):
    """Return (row_a, row_b) for each pair of overlapping watch intervals."""
    intervals = sorted(
        ((*row_interval(row), row) for row in rows),
        key=lambda item: item[0],
    )
    conflicts = []
    for i, (_, a_end, row_a) in enumerate(intervals):
        for b_start, _, row_b in intervals[i + 1 :]:
            if b_start >= a_end:
                break
            conflicts.append((row_a, row_b))
    return conflicts


def reschedule_on_trakt(row, new_end):
    trakt_post("/sync/history/remove", {"ids": [row["history_id"]]})
    watched_at = to_trakt_iso(new_end)
    if row["type"] == "episode":
        trakt_post(
            "/sync/history",
            {
                "shows": [
                    {
                        "ids": {"trakt": row["show_id"]},
                        "seasons": [
                            {
                                "number": row["season_number"],
                                "episodes": [
                                    {
                                        "number": row["episode_number"],
                                        "watched_at": watched_at,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        )
    else:
        trakt_post(
            "/sync/history",
            {
                "movies": [
                    {
                        "ids": {"trakt": row["item_trakt_id"]},
                        "watched_at": watched_at,
                    }
                ],
            },
        )


def main():
    try:
        rows = load_rows()
        conflicts = detect_conflicts(rows)
        if not conflicts:
            print("No overlapping watch intervals found.")
            return

        print(f"Found {len(conflicts)} overlapping pair(s).")
        for row_a, row_b in conflicts:
            print(
                f"{row_title(row_a)} ({row_a['watched_at']}) vs "
                f"{row_title(row_b)} ({row_b['watched_at']})"
            )
        if input("Fix these conflicts? [y/N]: ").strip().casefold() not in ("y", "yes"):
            return

        moves = 0
        while conflicts:
            row_a, row_b = conflicts[0]
            
            # Calculate the new end time for row_b by adding its duration to the end time of row_a,
            # ensuring the two intervals no longer overlap.
            new_end = row_a["watched_dt"] + row_duration(row_b)
   
            new_at = to_trakt_iso(new_end)
            print(f"Moving {row_title(row_b)}: {row_b['watched_at']} -> {new_at}")
            reschedule_on_trakt(row_b, new_end)
            row_b["watched_dt"] = new_end
            row_b["watched_at"] = new_at
            moves += 1
            conflicts = detect_conflicts(rows)

        path, _ = fetch_watch_history()
    except TraktRateLimitError as exc:
        raise SystemExit(str(exc)) from None

    remaining = len(detect_conflicts(load_rows()))
    print(f"Moved {moves} entr{'y' if moves == 1 else 'ies'}.")
    print(f"Refreshed watch history at {path}")
    print(f"Remaining conflicts: {remaining}")


if __name__ == "__main__":
    main()
