from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

import launcher


class LauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.modules = self.root / "modules"
        self.module = self.modules / "part_test"
        self.module.mkdir(parents=True)
        self.manifest = {
            "module_id": "part_test",
            "name": "테스트 모듈",
            "version": "1.0.0",
            "category": "test",
            "standalone": True,
            "start_command": ["python3", "app.py", "--no-browser"],
            "health_url": "http://127.0.0.1:65530/health",
            "home_url": "http://127.0.0.1:65530/",
            "default_port": 65530,
        }
        (self.module / "module.json").write_text(json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        launcher.stop_all()
        self.temp.cleanup()

    def test_01_discover_module_manifest(self) -> None:
        modules = launcher.discover_modules([self.modules])
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0]["module_id"], "part_test")
        self.assertEqual(modules[0]["module_dir"], str(self.module.resolve()))

    def test_02_invalid_manifest_is_reported(self) -> None:
        (self.module / "module.json").write_text("{}", encoding="utf-8")
        modules = launcher.discover_modules([self.modules])
        self.assertEqual(modules[-1]["module_id"], "__errors__")
        self.assertIn("필수 항목 누락", modules[-1]["errors"][0])

    def test_03_resolve_python_uses_current_interpreter(self) -> None:
        module = launcher.discover_modules([self.modules])[0]
        command = launcher.resolve_command(module)
        self.assertEqual(command[0], launcher.sys.executable)

    def test_04_health_status_stopped(self) -> None:
        module = launcher.discover_modules([self.modules])[0]
        self.assertEqual(launcher.health_status(module, timeout=0.1), "stopped")

    def test_05_launcher_health_and_home(self) -> None:
        original = launcher.MODULES_DIR
        launcher.MODULES_DIR = self.modules
        server = launcher.create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/health", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["modules"], 1)
            with urllib.request.urlopen(base + "/", timeout=3) as response:
                body = response.read().decode("utf-8")
            self.assertIn("우리 회사 AI 운영실", body)
            self.assertIn("테스트 모듈", body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            launcher.MODULES_DIR = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
