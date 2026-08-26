#!/bin/zsh
set -e
cd "$(dirname "$0")"
PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "Python 3가 필요합니다. https://www.python.org 에서 설치한 뒤 다시 실행하세요."
  read -k 1 "?아무 키나 누르면 종료합니다."
  exit 1
fi
"$PYTHON" app.py --preflight || {
  echo "사전 점검에 실패했습니다. 위 오류를 복사해 보관하세요."
  read -k 1 "?아무 키나 누르면 종료합니다."
  exit 1
}
open "http://127.0.0.1:8796" >/dev/null 2>&1 || true
"$PYTHON" app.py --no-browser
