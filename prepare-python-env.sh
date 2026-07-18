#!/bin/sh
# ビルドと開発起動で同じ、Pythonバージョン専用の仮想環境を使う。
# 過去に別のPythonで作られたネイティブ拡張子を混在させないためのもの。
set -eu

HANKO_PYTHON="${PYTHON_BIN:-python3}"
HANKO_PYTHON_TAG="$("$HANKO_PYTHON" -c 'import sys; print(f"py{sys.version_info.major}{sys.version_info.minor}")')"
HANKO_VENV_DIR="${HANKO_VENV_DIR:-.hanko-venv-$HANKO_PYTHON_TAG}"
HANKO_VENV_PYTHON="$HANKO_VENV_DIR/bin/python"

if [ ! -x "$HANKO_VENV_PYTHON" ]; then
  "$HANKO_PYTHON" -m venv "$HANKO_VENV_DIR"
fi

"$HANKO_VENV_PYTHON" -m pip install --disable-pip-version-check -r requirements.txt

export HANKO_PYTHON HANKO_VENV_DIR HANKO_VENV_PYTHON
