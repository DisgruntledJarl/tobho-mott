#!/usr/bin/env python3
"""Reschedule out-of-order episode watches flagged in data/flagged_order.csv."""

import argparse
import csv
from pathlib import Path

from trakt.client import TraktRateLimitError, to_trakt_iso
from trakt.csv_to_python import DEFAULT_CSV, load_rows
from trakt.history import fetch_watch_history
from trakt.intervals import row_interval, row_title
from trakt.scheduler import find_nearest_slot, reschedule_on_trakt

INPUT = Path(__file__).resolve().parent / "data" / "flagged_order.csv"


def season_episode_key(row):
    return (row["season_number"], row["episode_number"])


def latest_predecessor_end(row, rows):
    """Return the watch end of the latest episode that should precede ``row``."""
    row_key = season_episode_key(row)
    predecessor = None
    predecessor_key = None

    for other in rows:
        if other["type"] != "episode":
            continue
        if other["show_id"] != row["show_id"]:
            continue
        if other["history_id"] == row["history_id"]:
            continue

        key = season_episode_key(other)
        if key >= row_key:
            continue
        if predecessor_key is None or key > predecessor_key:
            predecessor_key = key
            predecessor = other

    if predecessor is None:
        return None
    _, end = row_interval(predecessor)
    return end


def load_fix_rows(path):
    """Return flagged CSV rows with ``action=fix``."""
    fix_rows = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            action = row.get("action", "").strip().lower()
            if not action:
                continue
            if action == "exclude":
                continue
            if action != "fix":
                print(
                    f"Warning: unknown action {action!r} "
                    f"for history_id {row['history_id']}"
                )
                continue
            fix_rows.append(row)
    return fix_rows


def index_rows_by_history_id(rows):
    return {row["history_id"]: row for row in rows}


def fix_order_rows(flagged_rows, rows, *, dry_run=False):
    """Move each flagged row to the nearest slot after its narrative predecessor."""
    by_history_id = index_rows_by_history_id(rows)
    fix_rows = sorted(
        flagged_rows,
        key=lambda row: (
            row["show_name"],
            int(row["season_number"]),
            int(row["episode_number"]),
        ),
    )

    moves = 0
    for flagged in fix_rows:
        history_id = int(flagged["history_id"])
        row = by_history_id.get(history_id)
        if row is None:
            print(f"Warning: history_id {history_id} not found in watch history")
            continue

        predecessor_end = latest_predecessor_end(row, rows)
        original_end = row["watched_dt"]
        if predecessor_end is not None:
            row["watched_dt"] = predecessor_end

        try:
            new_end = find_nearest_slot(row, rows)
        finally:
            row["watched_dt"] = original_end

        new_at = to_trakt_iso(new_end)
        print(f"Moving {row_title(row)}: {row['watched_at']} -> {new_at}")
        if dry_run:
            moves += 1
            continue

        reschedule_on_trakt(row, new_end)
        row["watched_dt"] = new_end
        row["watched_at"] = new_at
        moves += 1

    return moves


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help="Watch history CSV (default: data/watch_history.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned moves without calling the Trakt API",
    )
    args = parser.parse_args()

    flagged_rows = load_fix_rows(INPUT)
    if not flagged_rows:
        print("No rows with action=fix.")
        return

    try:
        rows = load_rows(args.csv)
        print(f"Found {len(flagged_rows)} row(s) marked fix.")
        moves = fix_order_rows(flagged_rows, rows, dry_run=args.dry_run)
        if not args.dry_run:
            path = fetch_watch_history()
    except TraktRateLimitError as exc:
        raise SystemExit(str(exc)) from None

    if args.dry_run:
        print(f"Would move {moves} entr{'y' if moves == 1 else 'ies'}.")
        return

    print(f"Moved {moves} entr{'y' if moves == 1 else 'ies'}.")
    print(f"Refreshed watch history at {path}")


if __name__ == "__main__":
    main()
