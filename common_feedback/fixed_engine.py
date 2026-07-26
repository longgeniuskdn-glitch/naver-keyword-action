from __future__ import annotations

from typing import Any

from .engine import (
    FeedbackEngine as BaseFeedbackEngine,
    RuleConflictError,
)


class FeedbackEngine(BaseFeedbackEngine):
    """트랜잭션 밖에서도 충돌 상태가 보존되도록 보강한 공개 엔진."""

    def approve_candidate(
        self,
        candidate_id: int,
        *,
        approved_by: str,
        note: str = "",
        override_conflict: bool = False,
    ) -> dict[str, Any]:
        try:
            return super().approve_candidate(
                candidate_id,
                approved_by=approved_by,
                note=note,
                override_conflict=override_conflict,
            )
        except RuleConflictError:
            now = self.now()
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    "SELECT id FROM rule_candidates WHERE id=?", (int(candidate_id),)
                ).fetchone()
                if row:
                    conn.execute(
                        "UPDATE rule_candidates SET status='conflict', updated_at=?, decision_note=? WHERE id=?",
                        (now, "기존 활성 규칙과 충돌", int(candidate_id)),
                    )
                    self._audit(
                        conn,
                        "candidate_conflict",
                        "rule_candidate",
                        int(candidate_id),
                        approved_by.strip() or "unknown",
                        {"persisted_after_conflict": True},
                    )
            raise
