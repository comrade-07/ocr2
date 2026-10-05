#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
APP="$PROJECT_ROOT/review_app.py"
SETTINGS="$PROJECT_ROOT/config/settings.yaml"

if [[ ! -x "$PYTHON" ]]; then
    echo "Python was not found at $PYTHON." >&2
    echo "Create a Linux virtual environment and install dependencies:" >&2
    echo "  python3 -m venv .venv" >&2
    echo "  .venv/bin/python -m pip install -r requirements.txt" >&2
    exit 1
fi

if [[ ! -f "$APP" ]]; then
    echo "Review app was not found at $APP." >&2
    exit 1
fi

if [[ ! -f "$SETTINGS" ]]; then
    echo "Runtime configuration was not found at $SETTINGS." >&2
    echo "Copy config/settings.example.yaml to config/settings.yaml and configure it for this deployment." >&2
    exit 1
fi

cd "$PROJECT_ROOT"

exec "$PYTHON" -m streamlit run "$APP" \
    --server.address=0.0.0.0 \
    --server.port=8501 \
    --server.headless=true \
    --server.runOnSave=false
