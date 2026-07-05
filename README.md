# trakt-scripts

Personal CLI tools for correcting Trakt watch history. Everything lives in the `src/trakt_scripts/` package: shared modules handle API access and CSV I/O, and the analysis/fix tools run as modules (`python -m trakt_scripts.<name>`) against a local snapshot.

All analysis runs offline against `data/watch_history.csv`. API calls happen only during history fetch and when you explicitly approve a fix.

---

## Setup

### Virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Linux / macOS / WSL
# .venv\Scripts\activate    # Windows
```

### Bootstrap

Create a Trakt app at [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications), set your credentials in `.env`, then run:

```bash
./setup.sh
```

The script:

1. Installs the repo as an editable package (`pip install -e .`)
2. Copies `.env.example` → `.env` if missing — edit `TRAKT_CLIENT_ID` and `TRAKT_CLIENT_SECRET`, then re-run
3. Runs `python -m trakt_scripts.client` for device login when `TRAKT_ACCESS_TOKEN` is empty

Device login flow:

1. Open the URL printed in the terminal (usually [https://trakt.tv/activate](https://trakt.tv/activate))
2. Enter the user code shown in the terminal
3. Wait for authorisation to complete

`TRAKT_ACCESS_TOKEN` is written to `.env` on success.

### Re-authenticate

When the access token expires:

```bash
python -m trakt_scripts.client
```

---

## Usage

Primary entry point — fetches watch history from Trakt (unless skipped), prints a summary, then offers a menu:

```bash
python -m trakt_scripts.run
python -m trakt_scripts.run --no-fetch   # reuse existing data/watch_history.csv (no API call)
```

| Choice | Action |
| --- | --- |
| `1` | Check for overlapping watch intervals (same as `trakt_scripts.detect_conflicts`) |
| `2` | Check for out-of-order episode watches (same as `trakt_scripts.detect_order`) |

Paths (`data/`, `.env`) resolve relative to the repo root automatically, so the tools work from any working directory. The default fetch step requires valid Trakt credentials; `--no-fetch` skips the fetch and uses the local CSV snapshot for menu checks.

When out-of-order violations are found, option `2` prints a static fix hint with placeholders:

```bash
python -m trakt_scripts.reschedule_season --show-id SHOW_ID --season N --start YYYY-MM-DD --end YYYY-MM-DD
```

Replace `SHOW_ID`, `N`, and the dates before running. A one-liner to look up `show_id` from the show name is included in the output.

---

## Advanced / standalone use

Individual scripts remain runnable on their own. Use these when you want a specific step without the unified menu, or when scripting.

### Fetch watch history

Every tool reads from a local CSV snapshot. Refresh it with:

```bash
python -m trakt_scripts.history
```

Writes `data/watch_history.csv` (episodes and movies, including runtimes when Trakt provides them).

Re-run after applying fixes or when you want a fresh snapshot.

---

### detect_conflicts

Detects overlapping watch intervals — pairs of entries whose computed watch windows overlap (impossible to watch both at once). Prints each pair, then optionally fixes them on Trakt.

```bash
python -m trakt_scripts.detect_conflicts
```

**Behaviour:**

- Prints overlapping pairs with titles and timestamps
- Prompts `Fix these conflicts? [y/N]` — default is no (audit only)
- On `y`, moves the second entry in each pair to start immediately after the first entry ends, re-checks until no overlaps remain, then re-fetches `data/watch_history.csv`

**Options:** none (reads `data/watch_history.csv`)

---

### detect_order

Detects out-of-order **first-watch** episodes — entries logged before a narrative predecessor in the same show (within-season or cross-season). Rewatches are ignored.

```bash
python -m trakt_scripts.detect_order
```

Prints a summary and writes violations to `data/flagged_order.csv`

When violations exist, the script prints a static `trakt_scripts.reschedule_season` command with placeholders (`SHOW_ID`, `N`, `YYYY-MM-DD`)

**Options:** none (reads `data/watch_history.csv`)

---

### reschedule_season

Moves an entire season's first-watch episodes into a date range. Episodes stay in narrative order; end times are spread randomly within equal slots across the window. Prints a preview and asks for approval before updating Trakt (two API calls: bulk remove + bulk add).

```bash
python -m trakt_scripts.reschedule_season --show-name "Breaking Bad" --season 1 --start 2020-01-01 --end 2020-12-31
```

The show name is matched against `show_name` values in `data/watch_history.csv` (case and punctuation are ignored). Partial matches work as it does a fuzzy search. If more than one show matches, you get a numbered list to pick from (or `0` to cancel). After applying, run `python -m trakt_scripts.detect_conflicts` if overlaps may remain.

**Options:**

| Flag | Purpose |
| --- | --- |
| `--show-name NAME` | Show name from watch history CSV (required) |
| `--season N` | Season number (required) |
| `--start` / `--end` | Date range `YYYY-MM-DD` (UTC start/end of day) |
