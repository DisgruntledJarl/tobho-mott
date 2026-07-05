#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
ENV_FILE="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/.env.example"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  if [[ -d "$REPO_ROOT/.venv" ]]; then
    echo "Found .venv/ but it's not active. Run:"
    echo "  source .venv/bin/activate"
    echo "or:"
    echo "  uv run ./setup.sh"
    exit 1
  elif command -v uv >/dev/null 2>&1; then
    echo "No virtual environment found. Run:"
    echo "  uv sync"
    echo "Then re-run: $SCRIPT_DIR/setup.sh"
    exit 1
  else
    echo "No virtual environment found, and uv is not installed."
    echo "Install uv first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "(see https://docs.astral.sh/uv/getting-started/installation/ for other options)"
    echo "Then run:"
    echo "  uv sync"
    echo "Then re-run: $SCRIPT_DIR/setup.sh"
    exit 1
  fi
fi

echo "Installing trakt-scripts (editable)..."
if command -v uv >/dev/null 2>&1; then
  uv pip install -e "$REPO_ROOT"
else
  pip install -e "$REPO_ROOT"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "Created $ENV_FILE from .env.example"
fi

get_env() {
  grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true
}

CLIENT_ID="$(get_env TRAKT_CLIENT_ID)"
CLIENT_SECRET="$(get_env TRAKT_CLIENT_SECRET)"
ACCESS_TOKEN="$(get_env TRAKT_ACCESS_TOKEN)"

if [[ -z "$CLIENT_ID" || -z "$CLIENT_SECRET" || "$CLIENT_ID" == "your_client_id" || "$CLIENT_SECRET" == "your_client_secret" ]]; then
  echo ""
  echo "Edit $ENV_FILE and set TRAKT_CLIENT_ID and TRAKT_CLIENT_SECRET from your Trakt API app."
  echo "Then re-run: $SCRIPT_DIR/setup.sh"
  exit 1
fi

if [[ -z "$ACCESS_TOKEN" ]]; then
  echo "Starting Trakt device authentication..."
  python -m trakt_scripts.client
else
  echo "TRAKT_ACCESS_TOKEN already set; skipping login."
fi

echo ""
echo "Setup complete."
python -m trakt_scripts.run
