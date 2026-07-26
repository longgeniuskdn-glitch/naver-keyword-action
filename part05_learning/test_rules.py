from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common_feedback import FeedbackEngine
from part05_learning.rules import (
    MODULE_ID,
    apply_approved_rules,
    build_rule_payload,
    encode_payload,
    list_active_rule_payloads,
    protect_handling_mode,
    slug_rule_key,
)


class Part05LearningRuleTests(unittest.TestCase):
    def test_rule_key_supports_korean_keyword(self) -> None:
        self.assertEqual(slug_rule_key(" 파트너 문의 "), "keyword-파트너-문의")

    def test_approved_rule_changes_classification(self) -> None:
        rule = {
            "candidate_id": 1,
            "rule_key": "keyword-파트너",
            "version": 2,
            "revised_text": encode_payload(
                build_rule_payload(
                    keyword="파트너",
                    category="제휴·콘텐츠",
                    assigned_team="마케팅",
                    urgency="medium",
                    handling_mode="standard",
                    source_intake_id=1,
                )
            ),
        }
        base = {
            "category": "기타",
            "assigned_team": "운영",
            "urgency": "low",
            "handling_mode": "standard",
            "risk_flags": [],
            "approval_required": 1,
        }
        result = apply_approved_rules(base, subject="파트너 질문", body="협력 방식이 궁금합니다", rules=[rule])
        self.assertEqual(result["category"], "제휴·콘텐츠")
        self.assertEqual(result["assigned_team"], "마케팅")
        self.assertEqual(result["urgency"], "medium")
        self.assertEqual(result["learning_rule"]["candidate_id"], 1)

    def test_more_specific_keyword_wins(self) -> None:
        generic = {
            "candidate_id": 1,
            "version": 9,
            "revised_text": json.dumps({
                "trigger_keyword": "세금",
                "category": "기타",
                "assigned_team": "운영",
                "urgency": "low",
                "handling_mode": "standard",
            }, ensure_ascii=False),
        }
        specific = {
            "candidate_id": 2,
            "version": 1,
            "revised_text": json.dumps({
                "trigger_keyword": "세금계산서",
                "category": "결제·증빙",
                "assigned_team": "회계",
                "urgency": "medium",
                "handling_mode": "prepare_only",
            }, ensure_ascii=False),
        }
        base = {"category": "기타", "assigned_team": "운영", "urgency": "low", "handling_mode": "standard"}
        result = apply_approved_rules(base, subject="세금계산서 발급", body="요청", rules=[generic, specific])
        self.assertEqual(result["category"], "결제·증빙")
        self.assertEqual(result["assigned_team"], "회계")

    def test_learning_rule_cannot_lower_human_only_boundary(self) -> None:
        self.assertEqual(protect_handling_mode("standard", "human_only"), "human_only")
        rule = {
            "candidate_id": 3,
            "version": 1,
            "revised_text": json.dumps({
                "trigger_keyword": "계약",
                "category": "기타",
                "assigned_team": "운영",
                "urgency": "low",
                "handling_mode": "standard",
            }, ensure_ascii=False),
        }
        base = {"category": "계약·법무", "assigned_team": "대표 검토", "urgency": "medium", "handling_mode": "human_only"}
        result = apply_approved_rules(base, subject="계약 검토", body="내용증명", rules=[rule])
        self.assertEqual(result["handling_mode"], "human_only")

    def test_only_approved_active_rule_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = FeedbackEngine(root / "runtime" / "feedback.db", root / "memory", candidate_threshold=2)
            payload = encode_payload(
                build_rule_payload(
                    keyword="파트너",
                    category="제휴·콘텐츠",
                    assigned_team="마케팅",
                    urgency="low",
                    handling_mode="standard",
                    source_intake_id=1,
                )
            )
            data = {
                "module_id": MODULE_ID,
                "item_ref": "intake-1",
                "original_text": "{}",
                "revised_text": payload,
                "reason_code": "routing",
                "reason_detail": "파트너 문의는 제휴·콘텐츠로 분류한다",
                "reviewer": "Kris",
                "rule_key": "keyword-파트너",
                "review_seconds": 10,
            }
            first = engine.submit_feedback(data)
            data["item_ref"] = "intake-2"
            engine.submit_feedback(data)
            self.assertEqual(list_active_rule_payloads(engine), [])
            engine.approve_candidate(first["candidate"]["id"], approved_by="Kris")
            active = list_active_rule_payloads(engine)
            self.assertEqual(len(active), 1)
            self.assertEqual(json.loads(active[0]["revised_text"])["trigger_keyword"], "파트너")


if __name__ == "__main__":
    unittest.main()
