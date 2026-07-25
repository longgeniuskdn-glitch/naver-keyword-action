#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3를 찾을 수 없습니다. https://www.python.org 에서 Python 3.10 이상을 설치하세요."
  read -r -p "Enter를 누르면 종료합니다."
  exit 1
fi
exec python3 app.py
