"""Trakt API calls for episode and movie metadata."""

from trakt.client import trakt_get


def fetch_episode_durations(show_id, season_number):
    """Return a dict mapping ``episode_number`` → runtime in minutes (or ``None``).

    Uses the ``runtime`` field from
    ``GET /shows/{id}/seasons/{n}/episodes?extended=full``.
    Episodes where Trakt has no runtime data map to ``None``.

    Used by the conflict fixer to determine accurate per-episode watch windows
    instead of the fixed 1-hour assumption used elsewhere.
    """
    response = trakt_get(
        f"/shows/{show_id}/seasons/{season_number}/episodes",
        {"extended": "full"},
        context=f"fetching episode durations for show {show_id} season {season_number}",
    )
    return {episode["number"]: episode.get("runtime") for episode in response.json()}


def fetch_movie_runtime(movie_id):
    """Return runtime in minutes (or ``None``) for a movie.

    Uses the ``runtime`` field from ``GET /movies/{id}?extended=full``.
    Returns ``None`` when Trakt has no runtime data for the movie.
    """
    response = trakt_get(
        f"/movies/{movie_id}",
        {"extended": "full"},
        context=f"fetching runtime for movie {movie_id}",
    )
    return response.json().get("runtime")
