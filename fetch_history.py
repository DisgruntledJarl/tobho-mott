#!/usr/bin/env python3
"""Fetch Trakt episode and movie watch history and save to one CSV."""

from trakt.client import TraktRateLimitError
from trakt.history import fetch_watch_history


def main():
    try:
        path, stats = fetch_watch_history()
    except TraktRateLimitError as exc:
        raise SystemExit(str(exc)) from None
    print(
        f"Wrote {stats['episodes']} episode(s) from {stats['shows']} show(s) "
        f"and {stats['movies']} movie(s) to {path}"
    )


if __name__ == "__main__":
    main()
