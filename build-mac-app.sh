#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

. ./prepare-python-env.sh

PYTHONNOUSERSITE=1 "$HANKO_VENV_PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  "Hanko PDF.spec"

APP_PATH="dist/Hanko PDF.app"
if [[ -z "$(find "$APP_PATH/Contents" -type f -path '*pydantic_core/_pydantic_core*.so' -print -quit)" ]]; then
  print -u2 "pydantic_core のネイティブ部品がアプリに同梱されていません。"
  exit 1
fi

print "作成しました: dist/Hanko PDF.app"
