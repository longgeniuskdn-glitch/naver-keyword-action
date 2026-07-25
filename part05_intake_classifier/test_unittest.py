from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

import app


class IntakeClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.db = self.root / "data" / "intake.db"
        self.backups = self.root / "backups"
        app.init_db(self.db)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_01_classify_delivery_normal(self) -> None:
        result = app.classify_intake("배송 문의", "운송장 조회가 안 됩니다")
        self.assertEqual(result["category"], "배송")
        self.assertEqual(result["assigned_team"], "물류")
        self.assertEqual(result["urgency"], "low")
        self.assertEqual(result["handling_mode"], "standard")

    def test_02_urgent_refund_is_prepare_only(self) -> None:
        result = app.classify_intake("긴급 환불 요청", "결제 오류가 발생했습니다. 오늘까지 환불해 주세요")
        self.assertEqual(result["category"], "환불·취소")
        self.assertEqual(result["urgency"], "high")
        self.assertEqual(result["handling_mode"], "prepare_only")
        self.assertIn("refund", result["risk_flags"])
        self.assertIn("payment", result["risk_flags"])

    def test_03_contract_legal_is_human_only(self) -> None:
        result = app.classify_intake("계약 분쟁", "내용증명과 법률 판단이 필요합니다")
        self.assertEqual(result["category"], "계약·법무")
        self.assertEqual(result["handling_mode"], "human_only")
        self.assertIn("contract", result["risk_flags"])
        self.assertIn("legal", result["risk_flags"])

    def test_04_duplicate_is_blocked(self) -> None:
        data = {"channel": "email", "sender": "a@example.com", "subject": "배송 문의", "body": "도착하지 않았습니다"}
        app.add_intake(data, self.db)
        with self.assertRaisesRegex(ValueError, "이미 접수"):
            app.add_intake(data, self.db)
        self.assertEqual(len(app.list_intakes(self.db)), 1)

    def test_05_csv_import_counts_duplicates(self) -> None:
        csv_text = "channel,sender,subject,body\nemail,a@example.com,배송 문의,운송장 조회 오류\nemail,a@example.com,배송 문의,운송장 조회 오류\nwebform,b@example.com,협업 제안,콘텐츠 인터뷰 제안"
        result = app.import_csv_text(csv_text, self.db)
        self.assertEqual(result, {"inserted": 2, "duplicates": 1, "errors": 0})
        self.assertEqual(len(app.list_intakes(self.db)), 2)

    def test_06_approval_and_audit_log(self) -> None:
        intake_id = app.add_intake({"channel": "memo", "subject": "제휴 제안", "body": "공동 콘텐츠 협업을 제안합니다"}, self.db)
        app.change_status(intake_id, "approved", self.db)
        row = app.get_intake(intake_id, self.db)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "approved")
        with app.connect(self.db) as conn:
            actions = [item[0] for item in conn.execute("SELECT action FROM audit_logs WHERE intake_id=? ORDER BY id", (intake_id,)).fetchall()]
        self.assertEqual(actions, ["intake_created", "status_approved"])

    def test_07_backup_restore_and_export(self) -> None:
        app.add_intake({"channel": "email", "subject": "영수증 요청", "body": "현금영수증 발급 확인"}, self.db)
        backup = app.create_backup(self.db, self.backups)
        self.assertTrue(backup.exists())
        app.reset_data(self.db)
        self.assertEqual(len(app.list_intakes(self.db)), 0)
        app.restore_backup(backup, self.db)
        self.assertEqual(len(app.list_intakes(self.db)), 1)
        exported = app.export_csv_bytes(self.db).decode("utf-8-sig")
        self.assertIn("영수증 요청", exported)
        self.assertIn("결제·증빙", exported)

    def test_08_server_health_and_home(self) -> None:
        server = app.create_server("127.0.0.1", 0, self.db, self.backups)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
                page = response.read().decode("utf-8")
            self.assertIn("업무 접수·분류실", page)
            self.assertIn("CSV 붙여넣기", page)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
