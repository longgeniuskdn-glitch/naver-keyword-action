#!/bin/zsh
set -e
cd "$(dirname "$0")"
PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "Python 3가 필요합니다."
  read -k 1 "?아무 키나 누르면 종료합니다."
  exit 1
fi
open "http://127.0.0.1:8780" >/dev/null 2>&1 || true
"$PYTHON" launcher.py --no-browser
