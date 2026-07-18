#!/bin/sh
set -eu

cd "$(dirname "$0")"
. ./prepare-python-env.sh

export PYTHONDONTWRITEBYTECODE=1
exec "$HANKO_VENV_PYTHON" -m uvicorn app:app --host 127.0.0.1 --port 8787
