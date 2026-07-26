from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from launcher import LauncherManager  # noqa: E402


def fetch_text(url: str, timeout: float = 2.0) -> str:
    with urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def main() -> None:
    manager = LauncherManager(ROOT / "modules", ROOT / "runtime", ROOT / "logs")
    expected = {"part04-ai-diagnosis", "part05-work-intake", "part06-knowledge-vault"}
    actual = set(manager.specs)
    if actual != expected:
        raise AssertionError(f"모듈 탐색 결과 불일치: {actual}")

    results = manager.start_all()
    errors = [item for item in results if item.get("error")]
    if errors:
        raise AssertionError(f"모듈 시작 실패: {json.dumps(errors, ensure_ascii=False)}")

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        states = manager.list_status()
        if all(item["healthy"] for item in states):
            break
        time.sleep(0.3)
    else:
        raise AssertionError(f"건강 상태 실패: {json.dumps(manager.list_status(), ensure_ascii=False)}")

    for item in manager.list_status():
        body = fetch_text(item["url"])
        if not body.strip():
            raise AssertionError(f"빈 화면 응답: {item['id']}")

    stopped = manager.stop_all()
    errors = [item for item in stopped if item.get("error")]
    if errors:
        raise AssertionError(f"모듈 종료 실패: {json.dumps(errors, ensure_ascii=False)}")

    print("SMOKE_OK: PART 04·05·06 탐색, 실행, /health, 화면, 종료 통과")


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            manager.stop_all()  # type: ignore[name-defined]
        except Exception:
            pass
