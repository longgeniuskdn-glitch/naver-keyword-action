#!/bin/bash
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3가 필요합니다. python.org에서 설치한 뒤 다시 실행하세요."
  read -r -p "Enter를 누르면 종료합니다."
  exit 1
fi
python3 app.py
