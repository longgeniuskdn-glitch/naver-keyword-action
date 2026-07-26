#!/bin/sh
set -eu
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  exec python3 launcher.py
fi
echo "Python 3을 찾지 못했습니다. Python 3.10 이상을 설치한 뒤 다시 실행하세요."
exit 1
