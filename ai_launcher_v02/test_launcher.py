from __future__ import annotations

import json
import socket
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from launcher import LauncherManager, ModuleSpec, find_free_port


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


MINI_APP = r'''
import argparse, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({"status":"ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        body = b"mini"
        self.send_response(200); self.send_header("Content-Length",str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass

p=argparse.ArgumentParser(); p.add_argument("--port",type=int,required=True); a=p.parse_args()
ThreadingHTTPServer(("127.0.0.1",a.port),H).serve_forever()
'''


class LauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.modules = self.root / "modules"
        self.runtime = self.root / "runtime"
        self.logs = self.root / "logs"
        self.modules.mkdir()
        self.port1 = free_port()
        self.port2 = free_port()
        self.make_module("alpha", "알파", self.port1)
        self.make_module("beta", "베타", self.port2)
        self.manager = LauncherManager(self.modules, self.runtime, self.logs)

    def tearDown(self) -> None:
        try:
            self.manager.stop_all()
        finally:
            self.tmp.cleanup()

    def make_module(self, module_id: str, name: str, port: int) -> None:
        folder = self.modules / module_id
        folder.mkdir()
        (folder / "mini_app.py").write_text(textwrap.dedent(MINI_APP), encoding="utf-8")
        (folder / "module.json").write_text(
            json.dumps({
                "schema_version": 1,
                "id": module_id,
                "name": name,
                "version": "1.0",
                "description": "테스트",
                "entrypoint": "mini_app.py",
                "args": ["--port", "{port}"],
                "default_port": port,
                "health_path": "/health",
                "ui_path": "/",
            }, ensure_ascii=False), encoding="utf-8")

    def test_discover_two_modules(self) -> None:
        self.assertEqual(set(self.manager.specs), {"alpha", "beta"})

    def test_manifest_parsing(self) -> None:
        spec = ModuleSpec.from_file(self.modules / "alpha" / "module.json")
        self.assertEqual(spec.module_id, "alpha")
        self.assertEqual(spec.default_port, self.port1)

    def test_start_and_health(self) -> None:
        result = self.manager.start("alpha", wait_seconds=5)
        self.assertTrue(result["healthy"])
        self.assertTrue(result["running"])

    def test_duplicate_start_is_idempotent(self) -> None:
        first = self.manager.start("alpha", wait_seconds=5)
        second = self.manager.start("alpha", wait_seconds=5)
        self.assertEqual(first["pid"], second["pid"])
        self.assertEqual(second["message"], "이미 실행 중입니다.")

    def test_stop_module(self) -> None:
        self.manager.start("alpha", wait_seconds=5)
        result = self.manager.stop("alpha")
        deadline = time.monotonic() + 3
        while result["healthy"] and time.monotonic() < deadline:
            time.sleep(0.1)
            result = self.manager.status("alpha")
        self.assertFalse(result["healthy"])

    def test_start_all_and_stop_all(self) -> None:
        started = self.manager.start_all()
        self.assertEqual(len(started), 2)
        self.assertTrue(all(item.get("healthy") for item in started))
        stopped = self.manager.stop_all()
        self.assertEqual(len(stopped), 2)

    def test_pid_file_created_and_cleaned(self) -> None:
        self.manager.start("alpha", wait_seconds=5)
        values = json.loads((self.runtime / "pids.json").read_text(encoding="utf-8"))
        self.assertIn("alpha", values)
        self.manager.stop("alpha")
        values = json.loads((self.runtime / "pids.json").read_text(encoding="utf-8"))
        self.assertNotIn("alpha", values)

    def test_log_file_created(self) -> None:
        self.manager.start("alpha", wait_seconds=5)
        log_path = self.logs / "alpha.log"
        self.assertTrue(log_path.exists())
        self.assertIn("START", log_path.read_text(encoding="utf-8"))

    def test_find_free_port(self) -> None:
        port = find_free_port(free_port())
        self.assertGreater(port, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
