from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DEFAULT_MODULES_DIR = ROOT / "modules"
DEFAULT_RUNTIME_DIR = ROOT / "runtime"
DEFAULT_LOGS_DIR = ROOT / "logs"


@dataclass(frozen=True)
class ModuleSpec:
    module_id: str
    name: str
    version: str
    description: str
    root: Path
    entrypoint: str
    args: tuple[str, ...]
    default_port: int
    health_path: str = "/health"
    ui_path: str = "/"

    @classmethod
    def from_file(cls, path: Path) -> "ModuleSpec":
        data = json.loads(path.read_text(encoding="utf-8"))
        required = ["id", "name", "version", "entrypoint", "default_port"]
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"{path}: 필수 항목 누락: {', '.join(missing)}")
        args = data.get("args", ["--port", "{port}"])
        if not isinstance(args, list) or not all(isinstance(v, str) for v in args):
            raise ValueError(f"{path}: args는 문자열 배열이어야 합니다.")
        port = int(data["default_port"])
        if port < 1024 or port > 65535:
            raise ValueError(f"{path}: 허용되지 않은 포트입니다: {port}")
        return cls(
            module_id=str(data["id"]),
            name=str(data["name"]),
            version=str(data["version"]),
            description=str(data.get("description", "")),
            root=path.parent.resolve(),
            entrypoint=str(data["entrypoint"]),
            args=tuple(args),
            default_port=port,
            health_path=str(data.get("health_path", "/health")),
            ui_path=str(data.get("ui_path", "/")),
        )


class LauncherManager:
    def __init__(
        self,
        modules_dir: Path = DEFAULT_MODULES_DIR,
        runtime_dir: Path = DEFAULT_RUNTIME_DIR,
        logs_dir: Path = DEFAULT_LOGS_DIR,
    ) -> None:
        self.modules_dir = Path(modules_dir).resolve()
        self.runtime_dir = Path(runtime_dir).resolve()
        self.logs_dir = Path(logs_dir).resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.pid_file = self.runtime_dir / "pids.json"
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[Any]] = {}
        self._specs = self.discover_modules()

    def discover_modules(self) -> dict[str, ModuleSpec]:
        specs: dict[str, ModuleSpec] = {}
        if not self.modules_dir.exists():
            return specs
        for manifest in sorted(self.modules_dir.glob("*/module.json")):
            spec = ModuleSpec.from_file(manifest)
            if spec.module_id in specs:
                raise ValueError(f"중복 모듈 ID: {spec.module_id}")
            entrypoint = spec.root / spec.entrypoint
            if not entrypoint.exists():
                raise FileNotFoundError(f"{spec.module_id}: 실행 파일 없음: {entrypoint}")
            specs[spec.module_id] = spec
        return specs

    def reload(self) -> None:
        with self._lock:
            self._specs = self.discover_modules()

    @property
    def specs(self) -> dict[str, ModuleSpec]:
        return dict(self._specs)

    def _load_pid_map(self) -> dict[str, int]:
        if not self.pid_file.exists():
            return {}
        try:
            raw = json.loads(self.pid_file.read_text(encoding="utf-8"))
            return {str(k): int(v) for k, v in raw.items()}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _save_pid_map(self, values: dict[str, int]) -> None:
        temp = self.pid_file.with_suffix(".tmp")
        temp.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.pid_file)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def _http_json(url: str, timeout: float = 0.8) -> tuple[bool, Any]:
        try:
            req = Request(url, headers={"User-Agent": "AI-Operations-Launcher/0.2"})
            with urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                try:
                    payload: Any = json.loads(body)
                except json.JSONDecodeError:
                    payload = body[:500]
                return 200 <= response.status < 300, payload
        except (OSError, URLError, TimeoutError):
            return False, None

    def health(self, spec: ModuleSpec) -> tuple[bool, Any]:
        return self._http_json(f"http://127.0.0.1:{spec.default_port}{spec.health_path}")

    def status(self, module_id: str) -> dict[str, Any]:
        spec = self._specs[module_id]
        healthy, payload = self.health(spec)
        pid_map = self._load_pid_map()
        pid = pid_map.get(module_id)
        process = self._processes.get(module_id)
        running = healthy or (process is not None and process.poll() is None) or (pid is not None and self._pid_alive(pid))
        return {
            "id": spec.module_id,
            "name": spec.name,
            "version": spec.version,
            "description": spec.description,
            "port": spec.default_port,
            "running": bool(running),
            "healthy": bool(healthy),
            "pid": pid,
            "url": f"http://127.0.0.1:{spec.default_port}{spec.ui_path}",
            "health": payload,
            "log": str((self.logs_dir / f"{spec.module_id}.log").relative_to(ROOT)) if self.logs_dir.is_relative_to(ROOT) else str(self.logs_dir / f"{spec.module_id}.log"),
        }

    def list_status(self) -> list[dict[str, Any]]:
        return [self.status(module_id) for module_id in sorted(self._specs)]

    def _command(self, spec: ModuleSpec) -> list[str]:
        values = [value.replace("{port}", str(spec.default_port)) for value in spec.args]
        return [sys.executable, str(spec.root / spec.entrypoint), *values]

    def start(self, module_id: str, wait_seconds: float = 12.0) -> dict[str, Any]:
        with self._lock:
            if module_id not in self._specs:
                raise KeyError(f"등록되지 않은 모듈: {module_id}")
            spec = self._specs[module_id]
            current = self.status(module_id)
            if current["healthy"]:
                current["message"] = "이미 실행 중입니다."
                return current

            old_pid = self._load_pid_map().get(module_id)
            if old_pid and self._pid_alive(old_pid):
                raise RuntimeError(f"{module_id}: PID {old_pid}가 남아 있지만 상태 점검에 실패했습니다. 먼저 종료하십시오.")

            log_path = self.logs_dir / f"{module_id}.log"
            log_handle = log_path.open("a", encoding="utf-8")
            log_handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] START {' '.join(self._command(spec))}\n")
            log_handle.flush()
            creationflags = 0
            start_new_session = os.name != "nt"
            if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(
                self._command(spec),
                cwd=spec.root,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=start_new_session,
                creationflags=creationflags,
            )
            log_handle.close()
            self._processes[module_id] = process
            pid_map = self._load_pid_map()
            pid_map[module_id] = process.pid
            self._save_pid_map(pid_map)

        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"{spec.name}이 시작 중 종료됐습니다. 로그를 확인하십시오: {log_path}")
            healthy, _ = self.health(spec)
            if healthy:
                result = self.status(module_id)
                result["message"] = "실행했습니다."
                return result
            time.sleep(0.2)
        raise TimeoutError(f"{spec.name}이 {wait_seconds:.0f}초 안에 준비되지 않았습니다. 로그: {log_path}")

    def _terminate_pid(self, pid: int) -> None:
        if not self._pid_alive(pid):
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
            return
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self._pid_alive(pid):
            time.sleep(0.1)
        if self._pid_alive(pid):
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                os.kill(pid, signal.SIGKILL)

    def stop(self, module_id: str) -> dict[str, Any]:
        with self._lock:
            if module_id not in self._specs:
                raise KeyError(f"등록되지 않은 모듈: {module_id}")
            process = self._processes.pop(module_id, None)
            pid_map = self._load_pid_map()
            pid = process.pid if process is not None else pid_map.get(module_id)
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            elif pid:
                self._terminate_pid(pid)
            pid_map.pop(module_id, None)
            self._save_pid_map(pid_map)
            result = self.status(module_id)
            result["message"] = "종료했습니다."
            return result

    def start_all(self) -> list[dict[str, Any]]:
        results = []
        for module_id in sorted(self._specs):
            try:
                results.append(self.start(module_id))
            except Exception as exc:  # 각 모듈 실패가 전체 런처를 멈추지 않게 한다.
                results.append({"id": module_id, "error": str(exc)})
        return results

    def stop_all(self) -> list[dict[str, Any]]:
        results = []
        for module_id in reversed(sorted(self._specs)):
            try:
                results.append(self.stop(module_id))
            except Exception as exc:
                results.append({"id": module_id, "error": str(exc)})
        return results


DASHBOARD_HTML = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>우리 회사 AI 운영실</title>
<style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif;color:#172033;background:#f3f6fa}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1180px;margin:auto;padding:32px 20px 60px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:24px}h1{font-size:30px;margin:0 0 8px}.sub{color:#667085}.actions{display:flex;gap:8px;flex-wrap:wrap}
button,a.btn{border:0;border-radius:10px;padding:10px 14px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}.primary{background:#155eef;color:white}.dark{background:#25324b;color:white}.light{background:white;color:#344054;border:1px solid #d0d5dd}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}.card{background:white;border:1px solid #e4e7ec;border-radius:16px;padding:20px;box-shadow:0 4px 16px rgba(16,24,40,.05)}
.top{display:flex;justify-content:space-between;gap:12px}.name{font-size:20px;font-weight:800}.version{color:#667085;font-size:13px}.desc{color:#475467;min-height:48px;line-height:1.55}.status{display:inline-flex;align-items:center;gap:7px;font-weight:800}.dot{width:10px;height:10px;border-radius:50%;background:#98a2b3}.healthy .dot{background:#12b76a}.starting .dot{background:#f79009}.error .dot{background:#f04438}
.meta{font-size:13px;color:#667085;margin:12px 0}.row{display:flex;gap:8px;flex-wrap:wrap}.msg{margin-top:18px;padding:12px;border-radius:10px;background:#eef4ff;display:none;white-space:pre-wrap}.empty{padding:40px;text-align:center;background:white;border-radius:16px;color:#667085}
@media(max-width:700px){header{align-items:flex-start;flex-direction:column}.actions{width:100%}.actions button{flex:1}}
</style></head><body><div class="wrap"><header><div><h1>우리 회사 AI 운영실</h1><div class="sub">PART별 독립 프로그램을 한 화면에서 실행하고 상태를 확인합니다.</div></div><div class="actions"><button class="primary" onclick="post('/api/start-all')">전체 실행</button><button class="dark" onclick="post('/api/stop-all')">전체 종료</button><button class="light" onclick="refresh()">새로고침</button></div></header><main id="grid" class="grid"></main><div id="msg" class="msg"></div></div>
<script>
const grid=document.getElementById('grid'),msg=document.getElementById('msg');
function esc(v){return String(v??'').replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));}
async function refresh(){const r=await fetch('/api/modules');const d=await r.json();if(!d.modules.length){grid.innerHTML='<div class="empty">등록된 모듈이 없습니다.</div>';return;}grid.innerHTML=d.modules.map(m=>`<section class="card"><div class="top"><div><div class="name">${esc(m.name)}</div><div class="version">${esc(m.version)} · 포트 ${m.port}</div></div><div class="status ${m.healthy?'healthy':m.running?'starting':''}"><span class="dot"></span>${m.healthy?'정상':m.running?'시작 중':'중지'}</div></div><p class="desc">${esc(m.description)}</p><div class="meta">ID: ${esc(m.id)} · PID: ${esc(m.pid||'-')}<br>로그: ${esc(m.log)}</div><div class="row"><button class="primary" onclick="post('/api/start/${encodeURIComponent(m.id)}')">실행</button><button class="dark" onclick="post('/api/stop/${encodeURIComponent(m.id)}')">종료</button><a class="btn light" href="${esc(m.url)}" target="_blank">화면 열기</a></div></section>`).join('');}
async function post(path){msg.style.display='block';msg.textContent='처리 중...';try{const r=await fetch(path,{method:'POST'});const d=await r.json();msg.textContent=JSON.stringify(d,null,2);}catch(e){msg.textContent=String(e);}await refresh();}
refresh();setInterval(refresh,2500);
</script></body></html>'''


def make_handler(manager: LauncherManager) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "AIOperationsLauncher/0.2"

        def _json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                body = DASHBOARD_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/health":
                self._json({"status": "ok", "modules": len(manager.specs), "version": "0.2"})
                return
            if self.path == "/api/modules":
                self._json({"modules": manager.list_status()})
                return
            self._json({"error": "not_found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            try:
                if self.path == "/api/start-all":
                    self._json({"results": manager.start_all()})
                    return
                if self.path == "/api/stop-all":
                    self._json({"results": manager.stop_all()})
                    return
                if self.path.startswith("/api/start/"):
                    self._json(manager.start(self.path.removeprefix("/api/start/")))
                    return
                if self.path.startswith("/api/stop/"):
                    self._json(manager.stop(self.path.removeprefix("/api/stop/")))
                    return
                self._json({"error": "not_found"}, 404)
            except KeyError as exc:
                self._json({"error": str(exc)}, 404)
            except Exception as exc:
                self._json({"error": str(exc)}, 500)

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler


def find_free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("사용 가능한 런처 포트를 찾지 못했습니다.")


def run_server(port: int, open_browser: bool = True) -> None:
    manager = LauncherManager()
    actual_port = find_free_port(port)
    server = ThreadingHTTPServer(("127.0.0.1", actual_port), make_handler(manager))
    url = f"http://127.0.0.1:{actual_port}"
    print(f"우리 회사 AI 운영실 v0.2: {url}")
    print(f"등록 모듈: {', '.join(manager.specs) or '없음'}")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n런처를 종료합니다. 실행 중인 모듈은 별도로 종료하십시오.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="우리 회사 AI 운영실 통합 런처")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--list", action="store_true", help="모듈 상태를 JSON으로 출력")
    parser.add_argument("--start-all", action="store_true")
    parser.add_argument("--stop-all", action="store_true")
    args = parser.parse_args()
    manager = LauncherManager()
    if args.list:
        print(json.dumps(manager.list_status(), ensure_ascii=False, indent=2))
        return
    if args.start_all:
        print(json.dumps(manager.start_all(), ensure_ascii=False, indent=2))
        return
    if args.stop_all:
        print(json.dumps(manager.stop_all(), ensure_ascii=False, indent=2))
        return
    run_server(args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
