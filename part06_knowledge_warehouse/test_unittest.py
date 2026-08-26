from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import app


class KnowledgeWarehouseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "data" / "knowledge.db"
        self.knowledge = self.root / "knowledge"
        self.output = self.root / "output"
        self.backups = self.root / "backups"
        app.init_db(self.db)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_01_tokens_support_korean_and_english(self) -> None:
        self.assertEqual(app.tokens("환불 Policy 7일"), ["환불", "policy", "7일"])

    def test_02_ingest_and_search_with_source(self) -> None:
        result = app.ingest_text("환불 정책", "policy/refund.md", "단순 변심 환불은 7일 이내 접수한다.", "", self.db)
        self.assertTrue(result["changed"])
        rows = app.search_documents("환불 7일", self.db)
        self.assertEqual(rows[0]["title"], "환불 정책")
        self.assertEqual(rows[0]["source"], "policy/refund.md")

    def test_03_same_content_does_not_increment_version(self) -> None:
        first = app.ingest_text("정책", "a.md", "같은 내용", "", self.db)
        second = app.ingest_text("정책", "a.md", "같은 내용", "", self.db)
        self.assertEqual(first["version"], 1)
        self.assertFalse(second["changed"])
        self.assertEqual(second["version"], 1)

    def test_04_changed_content_increments_version(self) -> None:
        app.ingest_text("정책", "a.md", "첫 내용", "", self.db)
        second = app.ingest_text("정책", "a.md", "수정 내용", "", self.db)
        self.assertEqual(second["version"], 2)
        self.assertIn("수정", app.search_documents("수정", self.db)[0]["content"])

    def test_05_stale_review_due_is_flagged(self) -> None:
        due = (date.today() - timedelta(days=1)).isoformat()
        app.ingest_text("오래된 가격표", "price.md", "가격은 10000원", due, self.db)
        self.assertTrue(app.search_documents("가격", self.db)[0]["stale"])

    def test_06_evidence_markdown_cites_source_and_missing(self) -> None:
        app.ingest_text("배송", "shipping.md", "오후 2시 이전 주문은 당일 출고 목표", "", self.db)
        text = app.build_evidence_markdown("출고", app.search_documents("출고", self.db))
        self.assertIn("shipping.md", text)
        self.assertIn("자료에 없는 내용은 추측하지 말고", text)
        empty = app.build_evidence_markdown("없는질문", [])
        self.assertIn("검색 결과가 없습니다", empty)

    def test_07_folder_scan_add_update_unchanged(self) -> None:
        self.knowledge.mkdir(parents=True)
        path = self.knowledge / "guide.md"
        path.write_text("첫 자료", encoding="utf-8")
        first = app.scan_knowledge_folder(self.knowledge, self.db)
        self.assertEqual(first["added"], 1)
        second = app.scan_knowledge_folder(self.knowledge, self.db)
        self.assertEqual(second["unchanged"], 1)
        path.write_text("수정 자료", encoding="utf-8")
        third = app.scan_knowledge_folder(self.knowledge, self.db)
        self.assertEqual(third["updated"], 1)

    def test_08_backup_restore_keeps_data(self) -> None:
        app.ingest_text("정책", "a.md", "복구할 자료", "", self.db)
        backup = app.create_backup(self.db, self.backups)
        app.reset_data(self.db)
        self.assertEqual(len(app.list_documents(self.db)), 0)
        app.restore_backup(backup, self.db)
        self.assertEqual(len(app.list_documents(self.db)), 1)

    def test_09_module_info_contract(self) -> None:
        info = app.module_info()
        self.assertEqual(info["module_id"], "part06_knowledge")
        self.assertTrue(info["standalone"])
        self.assertIn("knowledge.search", info["capabilities"])

    def test_10_server_health_search_and_home(self) -> None:
        app.ingest_text("회사 문체", "tone.md", "고객에게 존댓말을 사용한다.", "", self.db)
        server = app.create_server("127.0.0.1", 0, self.db)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/health", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            with urllib.request.urlopen(base + "/api/search?q=" + urllib.parse.quote("존댓말"), timeout=3) as response:
                results = json.loads(response.read().decode("utf-8"))
            self.assertEqual(results[0]["source"], "tone.md")
            with urllib.request.urlopen(base + "/", timeout=3) as response:
                body = response.read().decode("utf-8")
            self.assertIn("회사 자료를 기억하는 AI 지식 창고", body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
