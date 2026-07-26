#!/bin/bash
set -e
cd "$(dirname "$0")"
PYTHON=""
if command -v python3 >/dev/null 2>&1; then PYTHON="python3"; fi
if [ -z "$PYTHON" ]; then
  echo "Python 3을 찾지 못했습니다. Python 3.10 이상을 설치한 뒤 다시 실행하세요."
  read -r -p "Enter를 누르면 종료합니다..."
  exit 1
fi
exec "$PYTHON" launcher.py
