from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from ai_launcher_v03.launcher import build_services, make_handler


class LauncherV03Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "modules").mkdir()
        manager, engine = build_services(self.root)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(manager, engine))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def get_json(self, path: str):
        with urlopen(self.base + path, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post_json(self, path: str, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.base + path,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_health_reports_feedback_engine(self) -> None:
        status, body = self.get_json("/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["version"], "0.3")
        self.assertEqual(body["feedback_engine"], "ok")

    def test_feedback_api_creates_candidate(self) -> None:
        payload = {
            "module_id": "part05-work-intake",
            "item_ref": "inquiry-1",
            "original_text": "기타 문의",
            "revised_text": "계약 문의",
            "reason_code": "routing",
            "reason_detail": "계약이라는 단어가 있으면 계약 검토로 분류한다",
            "reviewer": "Kris",
            "rule_key": "contract-routing",
            "review_seconds": 25,
        }
        status, created = self.post_json("/api/feedback", payload)
        self.assertEqual(status, 201)
        self.assertEqual(created["candidate"]["status"], "collecting")
        _, listed = self.get_json("/api/rules/candidates")
        self.assertEqual(len(listed["candidates"]), 1)

    def test_registry_is_available_without_modules(self) -> None:
        status, body = self.get_json("/api/memory/registry")
        self.assertEqual(status, 200)
        paths = {item["path"] for item in body["files"]}
        self.assertIn("common/APPROVAL_POLICY.md", paths)


if __name__ == "__main__":
    unittest.main()
