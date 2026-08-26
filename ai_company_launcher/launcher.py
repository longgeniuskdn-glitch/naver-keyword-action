#!/usr/bin/env python3
"""우리 회사 AI 운영실 - 통합 런처 MVP.

module.json을 가진 독립 PART를 자동 탐색하고 실행·종료·상태 확인합니다.
각 모듈의 핵심 데이터베이스는 분리된 상태로 유지합니다.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_TITLE = "우리 회사 AI 운영실"
APP_VERSION = "0.1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8780
ROOT = Path(__file__).resolve().parent
MODULES_DIR = Path(os.environ.get("AI_COMPANY_MODULES_DIR", ROOT / "modules"))
LOG_DIR = Path(os.environ.get("AI_COMPANY_LAUNCHER_LOG_DIR", ROOT / "logs"))
PROCESSES: dict[str, subprocess.Popen] = {}
PROCESS_LOGS: dict[str, object] = {}
LOCK = threading.RLock()

CSS = """
:root{--navy:#173b58;--blue:#1669ad;--line:#d7e1e8;--green:#21765b;--red:#b23a45;--amber:#9b6500;--text:#24323d;--muted:#65737e}
*{box-sizing:border-box}body{margin:0;background:#f5f7f9;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",Arial,sans-serif;line-height:1.55}header{background:var(--navy);color:#fff;padding:22px 0}.wrap{width:min(1120px,94vw);margin:0 auto}.brand{display:flex;justify-content:space-between;gap:16px;align-items:center}.brand h1{margin:0;font-size:28px}.badge{background:#e9f3ff;color:#084a84;padding:6px 11px;border-radius:999px;font-weight:800;font-size:13px}main{padding:24px 0 60px}.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 5px 18px rgba(25,55,78,.05);margin-bottom:15px}.module{display:grid;grid-template-columns:1.5fr .8fr .8fr 1.2fr;gap:14px;align-items:center}.title{font-size:19px;font-weight:800;color:var(--navy)}.muted{font-size:13px;color:var(--muted)}.status{font-weight:800}.running{color:var(--green)}.stopped{color:var(--muted)}.unhealthy{color:var(--red)}button,.button{display:inline-block;border:0;border-radius:8px;padding:9px 13px;background:var(--blue);color:#fff;font-weight:750;text-decoration:none;cursor:pointer;margin:2px}.stop{background:var(--red)}.secondary{background:#657987}.notice{padding:12px 14px;border-left:5px solid var(--blue);background:#edf5ff;margin-bottom:15px}.empty{text-align:center;padding:35px;color:var(--muted)}@media(max-width:800px){.module{grid-template-columns:1fr}.brand{align-items:flex-start;flex-direction:column}}
"""


def module_search_roots() -> list[Path]:
    roots = [MODULES_DIR]
    extra = os.environ.get("AI_COMPANY_MODULE_PATHS", "")
    for value in extra.split(os.pathsep):
        if value.strip():
            roots.append(Path(value).expanduser())
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root.absolute())
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def validate_manifest(data: dict, module_dir: Path) -> dict:
    required = ["module_id", "name", "version", "start_command", "health_url", "home_url", "default_port"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{module_dir}: module.json 필수 항목 누락: {', '.join(missing)}")
    if not isinstance(data["start_command"], list) or not data["start_command"]:
        raise ValueError(f"{module_dir}: start_command는 문자열 목록이어야 합니다.")
    item = dict(data)
    item["module_dir"] = str(module_dir.resolve())
    item["manifest_path"] = str((module_dir / "module.json").resolve())
    return item


def discover_modules(roots: list[Path] | None = None) -> list[dict]:
    modules: dict[str, dict] = {}
    errors: list[str] = []
    for root in roots or module_search_roots():
        if not root.exists():
            continue
        candidates = [root / "module.json"] if (root / "module.json").exists() else sorted(root.rglob("module.json"))
        for manifest in candidates:
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                item = validate_manifest(data, manifest.parent)
                modules[item["module_id"]] = item
            except Exception as exc:
                errors.append(str(exc))
    result = sorted(modules.values(), key=lambda item: (item.get("category", ""), item["name"]))
    if errors:
        result.append({"module_id": "__errors__", "name": "모듈 읽기 오류", "errors": errors, "version": "", "module_dir": "", "health_url": "", "home_url": "", "start_command": [], "default_port": 0})
    return result


def process_running(module_id: str) -> bool:
    with LOCK:
        process = PROCESSES.get(module_id)
        if process is None:
            return False
        if process.poll() is None:
            return True
        PROCESSES.pop(module_id, None)
        handle = PROCESS_LOGS.pop(module_id, None)
        if handle:
            try:
                handle.close()
            except Exception:
                pass
        return False


def health_status(module: dict, timeout: float = 0.8) -> str:
    if module.get("module_id") == "__errors__":
        return "invalid"
    try:
        with urllib.request.urlopen(module["health_url"], timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return "healthy" if payload.get("ok") else "unhealthy"
    except Exception:
        return "starting" if process_running(module["module_id"]) else "stopped"


def resolve_command(module: dict) -> list[str]:
    command = list(module["start_command"])
    if os.name == "nt" and module.get("windows_start_command"):
        command = list(module["windows_start_command"])
    if command and command[0] in {"python", "python3"}:
        command[0] = sys.executable
    return command


def start_module(module: dict) -> str:
    module_id = module["module_id"]
    if module_id == "__errors__":
        raise ValueError("잘못된 모듈은 실행할 수 없습니다.")
    with LOCK:
        if process_running(module_id):
            return "이미 실행 중입니다."
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{module_id}.log"
        handle = log_path.open("a", encoding="utf-8")
        command = resolve_command(module)
        kwargs: dict = {"cwd": module["module_dir"], "stdout": handle, "stderr": subprocess.STDOUT, "text": True}
        if os.name != "nt":
            kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **kwargs)
        PROCESSES[module_id] = process
        PROCESS_LOGS[module_id] = handle
    return f"{module['name']} 실행을 시작했습니다."


def stop_module(module_id: str) -> str:
    with LOCK:
        process = PROCESSES.get(module_id)
        if process is None or process.poll() is not None:
            PROCESSES.pop(module_id, None)
            return "런처가 시작한 실행 프로세스가 없습니다."
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
        PROCESSES.pop(module_id, None)
        handle = PROCESS_LOGS.pop(module_id, None)
        if handle:
            handle.close()
    return "모듈을 종료했습니다."


def stop_all() -> None:
    for module_id in list(PROCESSES):
        try:
            stop_module(module_id)
        except Exception:
            pass


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def render_home(notice: str = "") -> str:
    modules = discover_modules()
    cards: list[str] = []
    for module in modules:
        if module["module_id"] == "__errors__":
            cards.append(f"<div class='card'><div class='title'>모듈 읽기 오류</div><div class='unhealthy'>{'<br>'.join(esc(x) for x in module.get('errors', []))}</div></div>")
            continue
        status = health_status(module)
        label = {"healthy": "정상 실행", "starting": "시작 중", "stopped": "중지", "unhealthy": "응답 오류"}.get(status, status)
        css = "running" if status == "healthy" else "unhealthy" if status == "unhealthy" else "stopped"
        buttons = f"<form method='post' action='/start/{urllib.parse.quote(module['module_id'])}' style='display:inline'><button type='submit'>실행</button></form><form method='post' action='/stop/{urllib.parse.quote(module['module_id'])}' style='display:inline'><button class='stop' type='submit'>종료</button></form><a class='button secondary' href='{esc(module['home_url'])}' target='_blank'>화면 열기</a>"
        cards.append(f"<div class='card module'><div><div class='title'>{esc(module['name'])}</div><div class='muted'>{esc(module['module_id'])} · v{esc(module['version'])}</div></div><div><span class='status {css}'>{label}</span></div><div class='muted'>포트 {esc(module['default_port'])}<br>{esc(module.get('category',''))}</div><div>{buttons}</div></div>")
    content = "".join(cards) if cards else "<div class='card empty'>설치된 모듈을 찾지 못했습니다. modules 폴더에 PART 폴더를 넣으세요.</div>"
    notice_html = f"<div class='notice'>{esc(notice)}</div>" if notice else ""
    return f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{APP_TITLE}</title><style>{CSS}</style></head><body><header><div class='wrap brand'><div><h1>{APP_TITLE}</h1><div>독립 모듈을 한곳에서 실행하고 상태를 확인합니다.</div></div><span class='badge'>LAUNCHER MVP · v{APP_VERSION}</span></div></header><main><div class='wrap'>{notice_html}{content}<div class='card'><strong>현재 범위</strong><div class='muted'>이 버전은 실행·종료·상태 확인을 담당합니다. 공통 승인 대기열과 공통 로그 대시보드는 다음 통합 단계에서 연결합니다.</div></div></div></main></body></html>"""


class LauncherHandler(BaseHTTPRequestHandler):
    server_version = "AICompanyLauncher/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        if os.environ.get("LAUNCHER_QUIET") != "1":
            super().log_message(fmt, *args)

    def send_bytes(self, body: bytes, content_type: str = "text/html; charset=utf-8", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, path: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", path)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/health":
            body = json.dumps({"ok": True, "app": APP_TITLE, "version": APP_VERSION, "modules": len([m for m in discover_modules() if m['module_id'] != '__errors__'])}, ensure_ascii=False).encode("utf-8")
            self.send_bytes(body, "application/json; charset=utf-8")
            return
        if parsed.path == "/api/modules":
            payload = []
            for module in discover_modules():
                if module["module_id"] != "__errors__":
                    payload.append({**module, "status": health_status(module)})
            self.send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/":
            notice = query.get("notice", [""])[0]
            self.send_bytes(render_home(notice).encode("utf-8"))
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        modules = {item["module_id"]: item for item in discover_modules() if item["module_id"] != "__errors__"}
        if self.path.startswith("/start/"):
            module_id = urllib.parse.unquote(self.path.rsplit("/", 1)[-1])
            try:
                message = start_module(modules[module_id])
            except Exception as exc:
                message = f"실행 실패: {exc}"
            self.redirect("/?notice=" + urllib.parse.quote(message))
            return
        if self.path.startswith("/stop/"):
            module_id = urllib.parse.unquote(self.path.rsplit("/", 1)[-1])
            try:
                message = stop_module(module_id)
            except Exception as exc:
                message = f"종료 실패: {exc}"
            self.redirect("/?notice=" + urllib.parse.quote(message))
            return
        self.send_error(404)


def create_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), LauncherHandler)


def open_browser_later(url: str) -> None:
    def _open() -> None:
        time.sleep(0.7)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=int(os.environ.get("LAUNCHER_PORT", DEFAULT_PORT)))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    if args.list:
        print(json.dumps(discover_modules(), ensure_ascii=False, indent=2))
        return 0
    MODULES_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    server = create_server(args.host, args.port)
    url = f"http://{args.host}:{server.server_address[1]}"
    print(f"{APP_TITLE} v{APP_VERSION}")
    print(f"브라우저 주소: {url}")
    if not args.no_browser and os.environ.get("AUTO_OPEN_BROWSER", "1") != "0":
        open_browser_later(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n런처를 종료합니다.")
    finally:
        stop_all()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
