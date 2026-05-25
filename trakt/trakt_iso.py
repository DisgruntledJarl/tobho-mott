"""Format datetimes as the UTC ISO string Trakt expects on POST requests."""

from datetime import timezone


def to_trakt_iso(dt):
    """Format a datetime as the millisecond-precision UTC string Trakt expects on POST."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
