#!/usr/bin/env python3
"""Detect out-of-order episode watches in Trakt history."""

import csv
import json
from collections import defaultdict
from pathlib import Path

from trakt_scripts.csv_to_python import load_rows
from trakt_scripts.paths import DATA_DIR, ORDER_EXEMPTIONS
from trakt_scripts.utils import (
    build_show_name_map,
    find_show_matches,
    row_title,
)

OUTPUT = DATA_DIR / "flagged_order.csv"

_CSV_FIELDNAMES = [
    "history_id",
    "show_name",
    "season_number",
    "episode_number",
    "watched_at",
    "expected_after_title",
    "expected_after_watched_at",
]


def detect_violations(episodes):
    """Return out-of-order first-watch violations, excluding rewatches."""

    # Create a dict per show with watches of all seasons
    by_show = defaultdict(list)
    for row in episodes:
        by_show[row["show_id"]].append(row)

    violations = []
    for show_rows in by_show.values():
        # Keep only the first watch of each episode
        first_watch = {}
        for row in show_rows:
            key = (row["season_number"], row["episode_number"])
            if (
                key not in first_watch
                or row["watched_dt"] < first_watch[key]["watched_dt"]
            ):
                first_watch[key] = row

        # Walk first watches in chronological order; flag any that fall below the running max
        max_key, max_row = None, None
        for row in sorted(first_watch.values(), key=lambda r: r["watched_dt"]):
            key = (row["season_number"], row["episode_number"])
            if max_key is not None and key < max_key:
                violations.append({"row": row, "expected_after_row": max_row})
            elif max_key is None or key > max_key:
                max_key, max_row = key, row

    return violations


def write_violations_csv(violations, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES)
        writer.writeheader()
        for v in violations:
            row, ea = v["row"], v["expected_after_row"]
            writer.writerow(
                {
                    "history_id": row.get("history_id"),
                    "show_name": row.get("show_name"),
                    "season_number": row.get("season_number"),
                    "episode_number": row.get("episode_number"),
                    "watched_at": row.get("watched_at"),
                    "expected_after_title": row_title(ea) if ea else "",
                    "expected_after_watched_at": ea.get("watched_at") if ea else "",
                }
            )


def load_exemptions(episode_rows):
    """Load order exemptions from JSON, resolving entries to exempt show_ids and seasons.

    Returns (exempt_show_ids, exempt_seasons) where:
    - exempt_show_ids is a set of show_ids whose episodes are fully exempt
    - exempt_seasons is a set of (show_id, season_number) tuples for season-level exemptions
    """
    if not ORDER_EXEMPTIONS.exists():
        return set(), set()

    try:
        raw = json.loads(ORDER_EXEMPTIONS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error decoding {ORDER_EXEMPTIONS}: {exc}") from None

    if not isinstance(raw, list):
        raise SystemExit(
            f"Expected a JSON array in {ORDER_EXEMPTIONS}, got {type(raw).__name__}"
        )

    show_map = build_show_name_map(episode_rows)
    exempt_show_ids = set()
    exempt_seasons = set()

    for entry in raw:
        if not isinstance(entry, dict):
            print(f"  [warn] Skipping non-dict entry: {entry!r}")
            continue

        show_query = entry.get("show")
        if not show_query:
            print(f"  [warn] Skipping entry missing 'show' key: {entry!r}")
            continue

        matches = find_show_matches(show_query, show_map)
        if not matches:
            print(
                f"  [warn] Exemption entry {show_query!r} matched no shows in history"
            )
            continue

        season_raw = entry.get("season")
        if season_raw is not None:
            try:
                season = int(season_raw)
            except (ValueError, TypeError):
                print(
                    f"  [warn] Invalid season {season_raw!r} in entry {entry!r}, "
                    f"skipping"
                )
                continue
            for _, show_id in matches:
                exempt_seasons.add((show_id, season))
            matched_str = ", ".join(f"{n} (id {i})" for n, i in matches)
            print(f"  Resolved {show_query!r} season {season} -> {matched_str}")
        else:
            for _, show_id in matches:
                exempt_show_ids.add(show_id)
            matched_str = ", ".join(f"{n} (id {i})" for n, i in matches)
            print(f"  Resolved {show_query!r} (all seasons) -> {matched_str}")

    return exempt_show_ids, exempt_seasons


def main():
    episodes = [r for r in load_rows() if r["type"] == "episode"]

    print("Loading order exemptions...")
    exempt_show_ids, exempt_seasons = load_exemptions(episodes)
    if exempt_show_ids or exempt_seasons:
        filtered = [
            r
            for r in episodes
            if r["show_id"] not in exempt_show_ids
            and (r["show_id"], r["season_number"]) not in exempt_seasons
        ]
        print(
            f"  Filtered {len(episodes) - len(filtered)} exempt episode(s), "
            f"{len(filtered)} remaining for analysis."
        )
        episodes = filtered
    else:
        print("  No exemptions configured, analysing all episodes.")

    violations = detect_violations(episodes)

    print(f"Found {len(violations)} out-of-order first-watch episode(s).")
    for v in violations:
        row, ea = v["row"], v["expected_after_row"]
        print(
            f"  {row_title(row)} ({row['watched_at']}) — watched before {row_title(ea)} ({ea['watched_at']})"
        )

    write_violations_csv(violations, OUTPUT)
    print(f"Wrote {len(violations)} violation(s) to {OUTPUT}")

    if violations:
        print(
            "\nTo look up show_id:\n"
            '  python3 -c "from trakt_scripts.csv_to_python import load_rows; '
            "print(next(r['show_id'] for r in load_rows() if r['show_name']=='SHOW_NAME'))\"\n"
            "\nTo fix an out-of-order season, run:\n"
            "  python -m trakt_scripts.reschedule_season --show-id SHOW_ID --season N --start YYYY-MM-DD --end YYYY-MM-DD"
        )


if __name__ == "__main__":
    main()
