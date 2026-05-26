# trakt-scripts

Personal CLI tools for correcting Trakt watch history. A shared `trakt/` package handles API access and CSV I/O; root-level scripts run analysis and fixes against a local snapshot.

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
3. Runs `python trakt/client.py` for device login when `TRAKT_ACCESS_TOKEN` is empty

Device login flow:

1. Open the URL printed in the terminal (usually [https://trakt.tv/activate](https://trakt.tv/activate))
2. Enter the user code shown in the terminal
3. Wait for authorisation to complete

`TRAKT_ACCESS_TOKEN` is written to `.env` on success.

### Re-authenticate

When the access token expires:

```bash
python trakt/client.py
```

---

## Usage

Primary entry point — fetches watch history from Trakt (unless skipped), prints a summary, then offers a menu:

```bash
python run.py
python run.py --no-fetch   # reuse existing data/watch_history.csv (no API call)
```

| Choice | Action |
| --- | --- |
| `1` | Check for overlapping watch intervals (same as `detect_conflicts.py`) |
| `2` | Check for out-of-order episode watches (same as `detect_order.py`) |

Run from the repo root (paths are relative to the current working directory). The default fetch step requires valid Trakt credentials; `--no-fetch` skips the fetch and uses the local CSV snapshot for menu checks.

When out-of-order violations are found, option `2` prints a static fix hint with placeholders:

```bash
python reschedule_season.py --show-id SHOW_ID --season N --start YYYY-MM-DD --end YYYY-MM-DD
```

Replace `SHOW_ID`, `N`, and the dates before running. A one-liner to look up `show_id` from the show name is included in the output.

---

## Advanced / standalone use

Individual scripts remain runnable on their own. Use these when you want a specific step without the unified menu, or when scripting.

### Fetch watch history

Every tool reads from a local CSV snapshot. Refresh it with:

```bash
python trakt/history.py
```

Writes `data/watch_history.csv` (episodes and movies, including runtimes when Trakt provides them).

Re-run after applying fixes or when you want a fresh snapshot.

---

### detect_conflicts

Detects overlapping watch intervals — pairs of entries whose computed watch windows overlap (impossible to watch both at once). Prints each pair, then optionally fixes them on Trakt.

```bash
python detect_conflicts.py
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
python detect_order.py
```

Prints a summary and writes violations to `data/flagged_order.csv` with an `action` column for manual review.

**Review workflow:**

1. Open `data/flagged_order.csv`
2. Set `action = exclude` for intentional non-linear watches (e.g. anthology shows)
3. Re-run `detect_order.py` — existing `action` values are preserved

When violations exist, the script prints a static `reschedule_season.py` command with placeholders (`SHOW_ID`, `N`, `YYYY-MM-DD`) plus a one-liner to look up `show_id` from a show name.

**Options:** none (reads `data/watch_history.csv`)

---

### reschedule_season

Moves an entire season's first-watch episodes into a date range. Episodes stay in narrative order; end times are spread randomly within equal slots across the window. Prints a preview and asks for approval before updating Trakt (two API calls: bulk remove + bulk add).

```bash
python reschedule_season.py --show-id 13855 --season 1 --start 2020-01-01 --end 2020-12-31
```

Use the `show_id` column from `data/watch_history.csv`. After applying, run `detect_conflicts.py` if new overlaps may exist.

**Options:**


| Flag                | Purpose                                               |
| ------------------- | ----------------------------------------------------- |
| `--show-id ID`      | Trakt show ID from watch history CSV (required)       |
| `--season N`        | Season number (required)                              |
| `--start` / `--end` | Date range `YYYY-MM-DD` (UTC start/end of day)        |
| `--csv PATH`        | Watch history CSV (default: `data/watch_history.csv`) |


---

## Typical workflow

```bash
source .venv/bin/activate

python run.py                      # fetch snapshot, then pick conflicts or order check
python run.py --no-fetch           # re-check order/conflicts on existing CSV (optional)
python reschedule_season.py ...    # bulk-reschedule a season when order check suggests it (optional)

python run.py                      # confirm final state
```

For step-by-step control without the menu, use the standalone scripts under [Advanced / standalone use](#advanced--standalone-use).

