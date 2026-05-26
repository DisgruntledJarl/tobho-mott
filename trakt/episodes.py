"""Episode watch helpers shared across scripts."""


def split_first_watch(entries):
    """Split episode entries into ``(first_watch, rewatches)``.

    Entries are sorted by ``watched_dt``. The first time each episode number
    appears it counts toward the first-watch run; repeats before the season is
    complete are rewatches. After every episode number in the season has been
    first-watched once, all later entries are rewatches.
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
        if entry["episode_number"] in seen:
            rewatches.append(entry)
            continue
        first_watch.append(entry)
        seen.add(entry["episode_number"])
        if seen >= all_episodes:
            complete = True

    return first_watch, rewatches
