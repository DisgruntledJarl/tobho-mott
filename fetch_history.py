#!/usr/bin/env python3
"""Fetch Trakt episode and movie watch history and save to one CSV."""

import csv
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from trakt_auth import refresh_access_token, save_tokens

OUTPUT = Path("data/watch_history.csv")
BASE = "https://api.trakt.tv"
ENV_PATH = Path(".env")

FIELDNAMES = [
    "type",
    "history_id",
    "watched_at",
    "show_id",
    "show_name",
    "season_number",
    "episode_number",
    "episode_trakt_id",
    "movie_trakt_id",
    "movie_title",
]


def _headers():
    return {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": os.environ["TRAKT_CLIENT_ID"],
        "Authorization": f"Bearer {os.environ['TRAKT_ACCESS_TOKEN']}",
    }


def trakt_get(path, params=None, _retried=False):
    response = requests.get(
        f"{BASE}{path}",
        params=params,
        headers=_headers(),
        timeout=60,
    )
    if response.status_code == 401 and not _retried:
        tokens = refresh_access_token()
        save_tokens(tokens, ENV_PATH)
        return trakt_get(path, params, _retried=True)
    response.raise_for_status()
    return response


def fetch_all_history(history_type):
    page = 1
    items = []
    while True:
        response = trakt_get(f"/sync/history/{history_type}", {"page": page, "limit": 1000})
        batch = response.json()
        items.extend(batch)
        if page >= int(response.headers.get("X-Pagination-Page-Count", 1)):
            break
        page += 1
    return items


def episode_row(item):
    show = item["show"]
    episode = item["episode"]
    return {
        "type": "episode",
        "history_id": item["id"],
        "watched_at": item["watched_at"],
        "show_id": show["ids"]["trakt"],
        "show_name": show["title"],
        "season_number": episode["season"],
        "episode_number": episode["number"],
        "episode_trakt_id": episode["ids"]["trakt"],
        "movie_trakt_id": "",
        "movie_title": "",
    }


def movie_row(item):
    movie = item["movie"]
    return {
        "type": "movie",
        "history_id": item["id"],
        "watched_at": item["watched_at"],
        "show_id": "",
        "show_name": "",
        "season_number": "",
        "episode_number": "",
        "episode_trakt_id": "",
        "movie_trakt_id": movie["ids"]["trakt"],
        "movie_title": movie["title"],
    }


def fetch_history_rows():
    load_dotenv(ENV_PATH)
    episodes = [episode_row(item) for item in fetch_all_history("episodes")]
    movies = [movie_row(item) for item in fetch_all_history("movies")]
    rows = episodes + movies
    rows.sort(key=lambda r: r["watched_at"])
    return rows


def write_watch_history(rows, output=OUTPUT):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return output


def refresh_watch_history(output=OUTPUT):
    rows = fetch_history_rows()
    path = write_watch_history(rows, output)
    return rows, path


def main():
    rows, path = refresh_watch_history()
    episodes = sum(1 for r in rows if r["type"] == "episode")
    movies = sum(1 for r in rows if r["type"] == "movie")
    print(f"Wrote {len(rows)} rows to {path} ({episodes} episodes, {movies} movies)")


if __name__ == "__main__":
    main()
