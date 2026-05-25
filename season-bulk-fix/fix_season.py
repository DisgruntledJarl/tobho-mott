#!/usr/bin/env python3
"""Spread first-watch episode timestamps across a date range and apply to Trakt."""

import argparse
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from trakt.csv import DEFAULT_CSV, find_show, load_rows, split_first_watch
from trakt.dt import to_trakt_iso
from trakt.episodes import fetch_season_premiere
from trakt.sync import apply_plan, apply_state_path, load_apply_state, write_preview

IST = ZoneInfo("Asia/Kolkata")

EPISODE_DURATION = timedelta(hours=1)
MOVIE_DURATION = timedelta(hours=3)
MIN_GAP = timedelta(minutes=2)
EVENING_WINDOW_RATIO = 0.85


def prompt_yes_no(prompt, default=True):
    """Prompt for ``y``/``n`` and return the boolean result.

    Empty input returns ``default``. ``EOFError`` (non-interactive stdin)
    raises ``SystemExit``.
    """
    suffix = "Y/n" if default else "y/N"
    while True:
        try:
            value = input(f"{prompt} [{suffix}]: ").strip().lower()
        except EOFError:
            raise SystemExit("\nCancelled.")
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Enter y or n.")


def prompt_date(label):
    """Prompt for a ``YYYY-MM-DD`` date string and return a ``date`` object.

    Re-prompts on empty input or malformed dates. ``EOFError`` raises
    ``SystemExit``.
    """
    while True:
        try:
            value = input(f"{label} (IST, YYYY-MM-DD): ").strip()
        except EOFError:
            raise SystemExit("\nCancelled.")
        if not value:
            print("Enter a date in YYYY-MM-DD format.")
            continue
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date. Use YYYY-MM-DD.")


def prompt_custom_dates():
    """Prompt for a start and end date, enforcing ``end >= start``.

    Returns ``(start_date, end_date)`` as ``date`` objects.
    """
    start_date = prompt_date("Start date")
    end_date = prompt_date("End date")
    if end_date < start_date:
        raise SystemExit("--end must be on or after --start.")
    return start_date, end_date


def watch_interval(watched_at, duration=EPISODE_DURATION):
    """Return ``(start, end)`` for a watch event that ends at ``watched_at``."""
    return watched_at - duration, watched_at


def intervals_overlap(a_start, a_end, b_start, b_end):
    """Return ``True`` when two intervals share any time."""
    return a_start < b_end and b_start < a_end


def build_blocked_intervals(rows, exclude_history_ids):
    """Build ``(start, end)`` clash intervals from all history except excluded IDs.

    Uses each row's ``runtime`` (minutes) when present; otherwise episodes use
    ``EPISODE_DURATION`` and movies use ``MOVIE_DURATION``. The excluded IDs are
    the entries being rescheduled — they must not block themselves.
    """
    blocked = []
    for row in rows:
        if row["history_id"] in exclude_history_ids:
            continue
        raw_rt = row.get("runtime")
        if raw_rt:
            duration = timedelta(minutes=raw_rt)
        elif row["type"] == "movie":
            duration = MOVIE_DURATION
        else:
            duration = EPISODE_DURATION
        start, end = watch_interval(row["watched_dt"], duration)
        blocked.append((start, end))
    return blocked


def _pick_evening_time(day, rng):
    """Return a random IST evening timestamp on ``day``.

    ~85 % of picks land in the evening window (19:00–02:00 the next day);
    the remaining 15 % are spread across daytime hours. All minutes are
    rounded to 0/15/30/45.
    """
    if rng.random() < EVENING_WINDOW_RATIO:
        if rng.random() < 0.8:
            hour = rng.randint(19, 23)
            minute = rng.choice([0, 15, 30, 45] if hour < 23 else [0, 15, 30])
            return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)
        next_day = day + timedelta(days=1)
        hour = rng.randint(0, 2)
        minute = rng.choice([0, 15, 30, 45] if hour < 2 else [0, 15, 30])
        return datetime(next_day.year, next_day.month, next_day.day, hour, minute, tzinfo=IST)
    hour = rng.choice(list(range(10, 19)) + list(range(3, 10)))
    minute = rng.choice([0, 15, 30, 45])
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)


def _assign_days(start_date, end_date, count, rng):
    """Spread ``count`` episodes roughly evenly across ``start_date``..``end_date``.

    Each episode offset gets ±1 day of jitter and is clamped so the sequence
    stays monotonically non-decreasing.
    """
    total_days = (end_date - start_date).days
    if count == 1:
        return [start_date + timedelta(days=total_days // 2)]
    days = []
    prev_offset = 0
    for i in range(count):
        offset = round(i * total_days / (count - 1))
        jitter = rng.randint(-1, 1)
        offset = max(0, min(total_days, offset + jitter))
        offset = max(prev_offset, offset)
        prev_offset = offset
        days.append(start_date + timedelta(days=offset))
    return days


def _has_clash(completion_time, blocked, scheduled, duration=EPISODE_DURATION):
    """Return ``True`` when placing an episode at ``completion_time`` overlaps any interval."""
    start, end = watch_interval(completion_time, duration)
    for other_start, other_end in blocked + scheduled:
        if intervals_overlap(start, end, other_start, other_end):
            return True
        if abs((end - other_end).total_seconds()) < MIN_GAP.total_seconds():
            return True
        if abs((end - other_start).total_seconds()) < MIN_GAP.total_seconds():
            return True
    return False


def _find_completion_time(day, blocked, scheduled, rng, earliest=None, duration=EPISODE_DURATION):
    """Find a clash-free completion timestamp on or near ``day``.

    Attempts random evening picks first (40 tries on target day), then
    progressively expands the search window. ``earliest`` enforces a lower
    bound so episodes stay in episode-number order.

    Raises ``SystemExit`` when no slot can be found.
    """
    def valid(candidate):
        if earliest is not None and candidate < earliest:
            return False
        return not _has_clash(candidate, blocked, scheduled, duration)

    for _ in range(40):
        candidate = _pick_evening_time(day, rng)
        if valid(candidate):
            return candidate

    if earliest is not None:
        start_offset = max(0, (earliest.date() - day).days)
        for day_offset in range(start_offset, 4):
            for _ in range(20):
                candidate = _pick_evening_time(day + timedelta(days=day_offset), rng)
                if valid(candidate):
                    return candidate

        search_day = max(day, earliest.date())
        for day_offset in range(0, 8):
            candidate_day = search_day + timedelta(days=day_offset)
            for hour in range(24):
                for minute in (0, 30):
                    candidate = datetime(
                        candidate_day.year,
                        candidate_day.month,
                        candidate_day.day,
                        hour,
                        minute,
                        tzinfo=IST,
                    )
                    if valid(candidate):
                        return candidate
    else:
        for day_offset in range(-3, 4):
            for _ in range(20):
                candidate = _pick_evening_time(day + timedelta(days=day_offset), rng)
                if valid(candidate):
                    return candidate

        for hour in range(24):
            for minute in (0, 30):
                candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)
                if valid(candidate):
                    return candidate

    raise SystemExit("Could not find clash-free timestamp. Try a wider date range.")


def schedule_episodes(entries, start_date, end_date, blocked, seed):
    """Assign clash-free IST timestamps to ``entries`` spread across ``start_date``..``end_date``.

    ``entries`` are sorted by ``episode_number`` before scheduling so that
    episode order is always preserved. Returns a list of plan dicts with
    ``old_watched_at``, ``new_watched_at``, ``new_watched_dt``, and the
    original row fields needed for the Trakt sync payload.
    """
    rng = random.Random(seed)
    entries = sorted(entries, key=lambda e: e["episode_number"])
    days = _assign_days(start_date, end_date, len(entries), rng)
    scheduled = []
    plan = []

    earliest = None
    for entry, day in zip(entries, days):
        raw_rt = entry.get("runtime")
        duration = timedelta(minutes=raw_rt) if raw_rt else EPISODE_DURATION
        completion = _find_completion_time(
            day, blocked, scheduled, rng, earliest=earliest, duration=duration
        )
        start, end = watch_interval(completion, duration)
        scheduled.append((start, end))
        earliest = completion + MIN_GAP
        plan.append(
            {
                "history_id": entry["history_id"],
                "show_id": entry["show_id"],
                "show_name": entry["show_name"],
                "season_number": entry["season_number"],
                "episode_number": entry["episode_number"],
                "old_watched_at": entry["watched_at"],
                "new_watched_at": to_trakt_iso(completion),
                "new_watched_dt": completion.astimezone(timezone.utc),
            }
        )

    return plan


WINDOW_START = datetime(2018, 1, 1, tzinfo=timezone.utc)
WINDOW_END = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

RELEASE_LAG_MIN = 30
RELEASE_LAG_MAX = 45
RELEASE_SPAN_MIN = 60
RELEASE_SPAN_MAX = 90


def in_window(dt):
    return WINDOW_START <= dt <= WINDOW_END


def release_date_range(premiere_date, seed):
    rng = random.Random(seed)
    start_date = premiere_date + timedelta(days=rng.randint(RELEASE_LAG_MIN, RELEASE_LAG_MAX))
    end_date = start_date + timedelta(days=rng.randint(RELEASE_SPAN_MIN, RELEASE_SPAN_MAX))
    return start_date, end_date


def prepare_season(rows, show_name, show_id, season_number):
    show_id = find_show(rows, show_name=show_name, show_id=show_id)
    season_entries = [
        row
        for row in rows
        if row["type"] == "episode"
        and row["show_id"] == show_id
        and row["season_number"] == season_number
    ]
    if not season_entries:
        raise SystemExit(f"No episode history found for show_id={show_id} season={season_number}.")

    first_watch, _ = split_first_watch(season_entries)
    to_fix = [entry for entry in first_watch if in_window(entry["watched_dt"])]
    if not to_fix:
        raise SystemExit("No first-watch entries in 2018–2024 for this season.")

    exclude_ids = {entry["history_id"] for entry in to_fix}
    blocked = build_blocked_intervals(rows, exclude_ids)
    show_name = to_fix[0]["show_name"]
    return show_id, to_fix, blocked, show_name


def build_plan(to_fix, blocked, start_date, end_date, seed):
    return schedule_episodes(to_fix, start_date, end_date, blocked, seed)


def print_plan(plan, show_id, season_number, start_date, end_date, *, premiere=None):
    preview_path = write_preview(plan, show_id, season_number)
    show_name = plan[0]["show_name"]
    print(f"\n{show_name} S{season_number:02d}: scheduling {len(plan)} first-watch episode(s)")
    if premiere is not None:
        print(f"Season premiere: {premiere.isoformat()}")
    print(f"Date range (IST): {start_date} → {end_date}")
    print(f"Preview written to {preview_path}")
    for row in plan:
        print(
            f"  E{row['episode_number']:02d}  {row['old_watched_at']}  ->  {row['new_watched_at']}"
        )
    return preview_path


def rebuild_plan_from_state(state, to_fix, blocked, show_id, season_number, seed):
    date_mode = state.get("date_mode")
    if date_mode == "custom":
        start_date = datetime.strptime(state["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(state["end_date"], "%Y-%m-%d").date()
        return build_plan(to_fix, blocked, start_date, end_date, seed), start_date, end_date, date_mode

    premiere = fetch_season_premiere(show_id, season_number)
    if premiere is None:
        raise SystemExit(
            f"Cannot rebuild release-date plan for resume (no premiere on Trakt). "
            f"Check state at {apply_state_path(show_id, season_number)}."
        )
    start_date, end_date = release_date_range(premiere, seed)
    return build_plan(to_fix, blocked, start_date, end_date, seed), start_date, end_date, "release"


def parse_args():
    parser = argparse.ArgumentParser(description="Fix bulk-imported season watch timestamps.")
    parser.add_argument("--show", help="Show title (case-insensitive exact match)")
    parser.add_argument("--show-id", type=int, help="Trakt show ID")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible schedules")
    parser.add_argument(
        "--resume-apply",
        action="store_true",
        help="Continue an interrupted apply using the saved state file (skips prompts)",
    )
    parser.add_argument(
        "--refresh-after-apply",
        action="store_true",
        help="Refresh data/watch_history.csv after a successful apply (may hit GET rate limits)",
    )
    args = parser.parse_args()

    if not args.show and args.show_id is None:
        parser.error("Provide --show or --show-id.")
    if args.show and args.show_id is not None:
        parser.error("Use only one of --show or --show-id.")

    return args


def main():
    args = parse_args()
    rows = load_rows(DEFAULT_CSV)
    show_id, to_fix, blocked, show_name = prepare_season(
        rows, args.show, args.show_id, args.season
    )

    if args.resume_apply:
        state_path = apply_state_path(show_id, args.season)
        state = load_apply_state(state_path)
        if not state:
            raise SystemExit(f"No apply state at {state_path}. Approve a plan first.")
        plan, start_date, end_date, date_mode = rebuild_plan_from_state(
            state, to_fix, blocked, show_id, args.season, args.seed
        )
        preview_path = print_plan(plan, show_id, args.season, start_date, end_date, premiere=None)
        print("\nResuming interrupted apply...")
        apply_plan(
            show_id,
            args.season,
            plan,
            preview_path,
            resume=True,
            refresh_after=args.refresh_after_apply,
            start_date=start_date,
            end_date=end_date,
            date_mode=date_mode,
        )
        return

    premiere = fetch_season_premiere(show_id, args.season)
    if premiere is not None:
        start_date, end_date = release_date_range(premiere, args.seed)
        plan = build_plan(to_fix, blocked, start_date, end_date, args.seed)
        preview_path = print_plan(plan, show_id, args.season, start_date, end_date, premiere=premiere)
        if prompt_yes_no("Apply this release-date plan to Trakt?"):
            print("\nApplying changes to Trakt...")
            apply_plan(
                show_id,
                args.season,
                plan,
                preview_path,
                refresh_after=args.refresh_after_apply,
                start_date=start_date,
                end_date=end_date,
                date_mode="release",
            )
            return
        print("\nEnter custom start/end dates instead.")
    else:
        print(f"\nNo season premiere found on Trakt for {show_name} S{args.season:02d}.")
        print("Enter custom start/end dates instead.")

    start_date, end_date = prompt_custom_dates()
    plan = build_plan(to_fix, blocked, start_date, end_date, args.seed)
    preview_path = print_plan(plan, show_id, args.season, start_date, end_date)
    if prompt_yes_no("Apply this plan to Trakt?"):
        print("\nApplying changes to Trakt...")
        apply_plan(
            show_id,
            args.season,
            plan,
            preview_path,
            refresh_after=args.refresh_after_apply,
            start_date=start_date,
            end_date=end_date,
            date_mode="custom",
        )
    else:
        print("Cancelled. No changes written to Trakt.")


if __name__ == "__main__":
    main()
