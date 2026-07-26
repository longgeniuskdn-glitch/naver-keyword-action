from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common_feedback.engine import FeedbackEngine, FeedbackEngineError, RuleConflictError


class FeedbackEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.engine = FeedbackEngine(root / "runtime" / "feedback.db", root / "memory", candidate_threshold=2)
        self.memory = root / "memory"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def feedback(self, detail: str = "도입부는 한 문장으로 시작한다", **overrides):
        data = {
            "module_id": "part02-threads",
            "item_ref": "thread-001",
            "original_text": "긴 도입부",
            "revised_text": "짧은 도입부",
            "reason_code": "opening",
            "reason_detail": detail,
            "reviewer": "Kris",
            "rule_key": "opening-length",
            "review_seconds": 40,
        }
        data.update(overrides)
        return self.engine.submit_feedback(data)

    def test_repeat_feedback_promotes_candidate_to_pending(self) -> None:
        first = self.feedback()
        self.assertEqual(first["candidate"]["status"], "collecting")
        second = self.feedback(item_ref="thread-002")
        self.assertEqual(second["candidate"]["status"], "pending")
        self.assertEqual(second["candidate"]["occurrences"], 2)

    def test_human_approval_writes_markdown_and_registry(self) -> None:
        result = self.feedback()
        self.feedback(item_ref="thread-002")
        approved = self.engine.approve_candidate(result["candidate"]["id"], approved_by="Kris")
        self.assertEqual(approved["status"], "approved")
        path = self.memory / "modules" / "part02-threads" / "THREADS_STYLE_RULES.md"
        self.assertIn("도입부는 한 문장으로 시작한다", path.read_text(encoding="utf-8"))
        registry = {item["path"]: item for item in self.engine.list_registry()}
        key = "modules/part02-threads/THREADS_STYLE_RULES.md"
        self.assertEqual(registry[key]["approved_by"], "Kris")

    def test_rejected_candidate_does_not_change_rule_file(self) -> None:
        result = self.feedback()
        target = self.memory / "modules" / "part02-threads" / "THREADS_STYLE_RULES.md"
        before = target.read_text(encoding="utf-8")
        rejected = self.engine.reject_candidate(result["candidate"]["id"], rejected_by="Kris", note="일회성 수정")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(target.read_text(encoding="utf-8"), before)

    def test_conflict_requires_explicit_override(self) -> None:
        first = self.feedback(detail="도입부는 한 문장으로 시작한다")
        self.feedback(detail="도입부는 한 문장으로 시작한다", item_ref="thread-002")
        self.engine.approve_candidate(first["candidate"]["id"], approved_by="Kris")
        second = self.feedback(detail="도입부는 질문 두 문장으로 시작한다", item_ref="thread-003")
        self.feedback(detail="도입부는 질문 두 문장으로 시작한다", item_ref="thread-004")
        with self.assertRaises(RuleConflictError):
            self.engine.approve_candidate(second["candidate"]["id"], approved_by="Kris")
        self.assertEqual(self.engine.get_candidate(second["candidate"]["id"])["status"], "conflict")
        approved = self.engine.approve_candidate(second["candidate"]["id"], approved_by="Kris", override_conflict=True)
        self.assertEqual(approved["status"], "approved")

    def test_rollback_restores_previous_content(self) -> None:
        first = self.feedback(detail="도입부는 한 문장으로 시작한다")
        self.feedback(detail="도입부는 한 문장으로 시작한다", item_ref="thread-002")
        self.engine.approve_candidate(first["candidate"]["id"], approved_by="Kris")
        target = self.memory / "modules" / "part02-threads" / "THREADS_STYLE_RULES.md"
        previous = target.read_text(encoding="utf-8")
        second = self.feedback(detail="도입부는 질문 두 문장으로 시작한다", item_ref="thread-003")
        self.feedback(detail="도입부는 질문 두 문장으로 시작한다", item_ref="thread-004")
        self.engine.approve_candidate(second["candidate"]["id"], approved_by="Kris", override_conflict=True)
        rolled = self.engine.rollback_candidate(second["candidate"]["id"], rolled_back_by="Kris")
        self.assertEqual(rolled["status"], "rolled_back")
        self.assertEqual(target.read_text(encoding="utf-8"), previous)
        self.assertEqual(self.engine.get_candidate(first["candidate"]["id"])["status"], "approved")

    def test_protected_feedback_requires_human_decision(self) -> None:
        result = self.feedback(
            module_id="part05-work-intake",
            reason_code="legal",
            rule_key="legal-review",
            reason_detail="법률 관련 답변은 반드시 사람이 승인한다",
        )
        self.assertEqual(result["candidate"]["risk_level"], "protected")
        self.assertNotEqual(result["candidate"]["status"], "approved")

    def test_first_10_log_and_metrics(self) -> None:
        for index in range(3):
            self.feedback(item_ref=f"thread-{index}", review_seconds=30 + index)
        metrics = self.engine.first10_metrics("part02-threads")
        self.assertEqual(metrics["count"], 3)
        self.assertEqual(metrics["review_seconds"], 93)
        log = self.memory / "modules" / "part02-threads" / "FIRST_10_LOG.md"
        self.assertIn("3/10", log.read_text(encoding="utf-8"))

    def test_audit_log_records_decisions(self) -> None:
        result = self.feedback()
        self.engine.reject_candidate(result["candidate"]["id"], rejected_by="Kris")
        actions = [item["action"] for item in self.engine.list_audit()]
        self.assertIn("feedback_submitted", actions)
        self.assertIn("candidate_rejected", actions)

    def test_approved_rule_must_be_rolled_back_before_rejection(self) -> None:
        result = self.feedback()
        self.engine.approve_candidate(result["candidate"]["id"], approved_by="Kris")
        with self.assertRaises(FeedbackEngineError):
            self.engine.reject_candidate(result["candidate"]["id"], rejected_by="Kris")


if __name__ == "__main__":
    unittest.main()
