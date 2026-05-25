#!/usr/bin/env python3
"""Detect out-of-order episode watches in Trakt history."""

import argparse
from collections import defaultdict
from pathlib import Path

from trakt.csv_to_python import DEFAULT_CSV, load_rows


def split_first_watch(entries):
    """Split episode entries into ``(first_watch, rewatches)``.

    Entries are sorted by ``watched_dt``. The first-watch run ends once every
    episode number in the set has appeared exactly once; all later entries are
    rewatches. Both returned lists preserve chronological order.
    """
    entries = sorted(entries, key=lambda e: e["watched_dt"])
    all_episodes = {e["episode_number"] for e in entries}
    seen = set()
    first_watch = []
    rewatches = []
    complete = False

    for entry in entries:
        if complete:
            rewatches.append(entry)
            continue
        first_watch.append(entry)
        seen.add(entry["episode_number"])
        if seen >= all_episodes:
            complete = True

    return first_watch, rewatches


def parse_exclusion(value):
    """Parse ``show_id:season:episode`` into a tuple of ints."""
    parts = value.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"Expected show_id:season:episode, got {value!r}"
        )
    try:
        return tuple(int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Expected show_id:season:episode, got {value!r}"
        ) from exc


def episode_key(row):
    return (row["show_id"], row["season_number"], row["episode_number"])


def detect_order(episodes, exclusions=None):
    """Return out-of-order first-watch entries grouped by show and season."""
    exclusions = exclusions or set()
    by_show_season = defaultdict(list)
    for row in episodes:
        if episode_key(row) in exclusions:
            continue
        by_show_season[(row["show_id"], row["season_number"])].append(row)

    out_of_order = []
    for (show_id, season_number), season_entries in sorted(by_show_season.items()):
        first_watch, _ = split_first_watch(season_entries)
        prev_episode = None
        for row in first_watch:
            episode_number = row["episode_number"]
            if prev_episode is not None and episode_number < prev_episode:
                out_of_order.append(row)
            prev_episode = episode_number

    return out_of_order


def print_summary(out_of_order):
    print(f"Found {len(out_of_order)} out-of-order first-watch episode(s).")
    for row in out_of_order:
        print(
            f"  {row['show_name']} "
            f"S{row['season_number']:02d}E{row['episode_number']:02d} "
            f"({row['watched_at']})"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CSV, help="Watch history CSV")
    parser.add_argument(
        "--exclude",
        action="append",
        type=parse_exclusion,
        default=[],
        metavar="SHOW_ID:SEASON:EPISODE",
        help="Skip a specific episode from order checks (repeatable)",
    )
    args = parser.parse_args()

    episodes = [r for r in load_rows(args.input) if r["type"] == "episode"]
    exclusions = set(args.exclude)
    out_of_order = detect_order(episodes, exclusions=exclusions)
    print_summary(out_of_order)


if __name__ == "__main__":
    main()
