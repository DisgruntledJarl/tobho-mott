#!/usr/bin/env python3
"""Reschedule out-of-order episode watches flagged in data/flagged_order.csv."""

import argparse
import csv
from pathlib import Path

from datetime import timedelta

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


def earliest_successor(row, rows):
    """Return the next episode in the same season that should follow ``row``."""
    row_key = season_episode_key(row)
    successor = None
    successor_key = None

    for other in rows:
        if other["type"] != "episode":
            continue
        if other["show_id"] != row["show_id"]:
            continue
        if other["season_number"] != row["season_number"]:
            continue
        if other["history_id"] == row["history_id"]:
            continue

        key = season_episode_key(other)
        if key <= row_key:
            continue
        if successor_key is None or key < successor_key:
            successor_key = key
            successor = other

    return successor


def _slot_in_window(row, rows, *, min_end, max_end):
    """Return nearest slot end within ``[min_end, max_end]``, or ``None``."""
    original_end = row["watched_dt"]
    anchor = min_end if min_end is not None else original_end
    row["watched_dt"] = anchor
    try:
        return find_nearest_slot(row, rows, min_end=min_end, max_end=max_end)
    except ValueError:
        return None
    finally:
        row["watched_dt"] = original_end


def find_order_slot(row, rows):
    """Find a slot after the predecessor and before the earliest successor."""
    predecessor_end = latest_predecessor_end(row, rows)
    successor = earliest_successor(row, rows)
    max_end = None
    if successor is not None:
        max_end = row_interval(successor)[0]

    new_end = _slot_in_window(row, rows, min_end=predecessor_end, max_end=max_end)
    if new_end is not None or successor is None:
        return new_end, []

    successor_end = successor["watched_dt"]
    vacated_end = successor_end
    new_successor_end = find_nearest_slot(
        successor, rows, min_end=successor_end + timedelta(seconds=1)
    )
    bumped = [(successor, new_successor_end)]
    successor["watched_dt"] = new_successor_end
    successor["watched_at"] = to_trakt_iso(new_successor_end)

    new_end = _slot_in_window(row, rows, min_end=predecessor_end, max_end=vacated_end)
    if new_end is None:
        raise ValueError(
            f"No slot for {row_title(row)} between predecessor and "
            f"{row_title(successor)} even after bumping the successor"
        )
    return new_end, bumped


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
            0
            if row.get("violation_type") in ("skip_ahead", "late_watch")
            else 1,
            row["show_name"],
            int(row["season_number"]),
            -int(row["episode_number"]),
        ),
    )

    moves = 0
    for flagged in fix_rows:
        history_id = int(flagged["history_id"])
        row = by_history_id.get(history_id)
        if row is None:
            print(f"Warning: history_id {history_id} not found in watch history")
            continue

        new_end, bumped = find_order_slot(row, rows)

        for bumped_row, bumped_end in bumped:
            bumped_at = to_trakt_iso(bumped_end)
            print(
                f"Moving {row_title(bumped_row)}: "
                f"{bumped_row['watched_at']} -> {bumped_at} (making room)"
            )
            if not dry_run:
                reschedule_on_trakt(bumped_row, bumped_end)

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
