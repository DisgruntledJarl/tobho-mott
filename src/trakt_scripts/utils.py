"""utility helpers"""

from datetime import timedelta
import sys

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
