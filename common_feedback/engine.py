from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MODULE_PROFILES: dict[str, dict[str, str]] = {
    "part02-threads": {
        "name": "PART 02｜Threads",
        "target_file": "THREADS_STYLE_RULES.md",
    },
    "part03-blog": {
        "name": "PART 03｜블로그",
        "target_file": "BLOG_STYLE_RULES.md",
    },
    "part04-ai-diagnosis": {
        "name": "PART 04｜AI 자동화 진단실",
        "target_file": "QUALITY_CRITERIA.md",
    },
    "part05-work-intake": {
        "name": "PART 05｜업무 접수·분류실",
        "target_file": "INTAKE_RULES.md",
    },
    "part06-knowledge-vault": {
        "name": "PART 06｜회사 자료 AI 지식 창고",
        "target_file": "KNOWLEDGE_POLICY.md",
    },
}

COMMON_FILES = {
    "COMPANY_PROFILE.md": "# 회사 프로필\n\n회사 공통 정보와 변하지 않는 사실을 기록합니다.\n",
    "APPROVAL_POLICY.md": "# 승인 정책\n\n외부 발행, 결제, 계약, 법률, 개인정보 관련 작업은 사람 승인을 유지합니다.\n",
    "AI_WORK_RULES.md": "# AI 공통 업무 규칙\n\n모든 모듈에 적용되는 짧고 명확한 공통 규칙만 기록합니다.\n",
}

MODULE_SUPPORT_FILES = {
    "RULE_CANDIDATES.md": "# 규칙 후보\n\n사람이 승인하기 전에는 실제 업무에 적용하지 않습니다.\n",
    "FIRST_10_LOG.md": "# 첫 10건 교육 기록\n\n초기 10건의 수정 이유와 검토 시간을 기록합니다.\n",
    "APPROVED_EXAMPLES.md": "# 승인 사례\n\n대표성이 있고 재사용 가치가 있는 승인 사례만 기록합니다.\n",
    "REJECTED_PATTERNS.md": "# 거절 패턴\n\n반복해서 피해야 하는 결과와 이유를 기록합니다.\n",
}

RISK_REASON_CODES = {
    "legal",
    "contract",
    "payment",
    "refund",
    "privacy",
    "public_response",
    "security",
}


class FeedbackEngineError(RuntimeError):
    pass


class RuleConflictError(FeedbackEngineError):
    pass


class InvalidMemoryPathError(FeedbackEngineError):
    pass


@dataclass(frozen=True)
class FeedbackRecord:
    module_id: str
    item_ref: str
    original_text: str
    revised_text: str
    reason_code: str
    reason_detail: str
    reviewer: str
    rule_key: str
    review_seconds: int = 0


class FeedbackEngine:
    """SQLite 사건 기록 + 승인형 Markdown 규칙 관리를 담당한다.

    이 엔진은 LLM 없이 동작한다. 반복 후보는 동일한 모듈·규칙 키·수정 이유가
    누적되는지를 결정론적으로 계산한다. 후보가 생성돼도 사람 승인 전에는 MD에
    반영하지 않는다.
    """

    def __init__(
        self,
        db_path: Path | str,
        memory_root: Path | str,
        candidate_threshold: int = 2,
    ) -> None:
        self.db_path = Path(db_path).resolve()
        self.memory_root = Path(memory_root).resolve()
        self.candidate_threshold = max(2, int(candidate_threshold))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()
        self.ensure_memory_layout()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module_id TEXT NOT NULL,
                    item_ref TEXT NOT NULL,
                    original_text TEXT NOT NULL,
                    revised_text TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    reason_detail TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    rule_key TEXT NOT NULL,
                    review_seconds INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rule_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module_id TEXT NOT NULL,
                    rule_key TEXT NOT NULL,
                    rule_text TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    reason_detail TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    occurrences INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'collecting',
                    risk_level TEXT NOT NULL DEFAULT 'normal',
                    target_file TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    decided_by TEXT,
                    decision_note TEXT
                );

                CREATE TABLE IF NOT EXISTS rule_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER NOT NULL,
                    module_id TEXT NOT NULL,
                    rule_key TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    previous_content TEXT NOT NULL,
                    new_content TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    approved_by TEXT NOT NULL,
                    approved_at TEXT NOT NULL,
                    rollback_by TEXT,
                    rollback_at TEXT,
                    FOREIGN KEY(candidate_id) REFERENCES rule_candidates(id)
                );

                CREATE TABLE IF NOT EXISTS memory_registry (
                    path TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    module_id TEXT,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    owner TEXT NOT NULL,
                    approved_by TEXT,
                    last_reviewed_at TEXT,
                    content_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_feedback_module ON feedback(module_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_candidate_status ON rule_candidates(status, module_id);
                CREATE INDEX IF NOT EXISTS idx_rule_active ON rule_versions(module_id, rule_key, active);
                """
            )

    @staticmethod
    def _slug(value: str) -> str:
        clean = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", value.strip())
        clean = clean.strip("-._")
        if not clean:
            raise ValueError("비어 있는 식별자는 사용할 수 없습니다.")
        return clean[:120]

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    @staticmethod
    def _hash_text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _profile(self, module_id: str) -> dict[str, str]:
        module_id = self._slug(module_id)
        return MODULE_PROFILES.get(
            module_id,
            {"name": module_id, "target_file": "AI_WORK_RULES.md"},
        )

    def module_root(self, module_id: str) -> Path:
        module_id = self._slug(module_id)
        return self.memory_root / "modules" / module_id

    def _safe_memory_path(self, relative_path: str | Path) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute():
            raise InvalidMemoryPathError("절대 경로는 사용할 수 없습니다.")
        target = (self.memory_root / relative).resolve()
        if target != self.memory_root and self.memory_root not in target.parents:
            raise InvalidMemoryPathError("기억 저장소 밖의 경로는 사용할 수 없습니다.")
        return target

    def ensure_memory_layout(self, module_ids: Iterable[str] | None = None) -> None:
        common = self.memory_root / "common"
        common.mkdir(parents=True, exist_ok=True)
        for name, content in COMMON_FILES.items():
            path = common / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")
            self._register_file(path, scope="common", module_id=None, owner="common")
        for module_id in module_ids or MODULE_PROFILES.keys():
            self.ensure_module_files(module_id)

    def ensure_module_files(self, module_id: str) -> None:
        module_id = self._slug(module_id)
        root = self.module_root(module_id)
        root.mkdir(parents=True, exist_ok=True)
        profile = self._profile(module_id)
        target = root / profile["target_file"]
        if not target.exists():
            target.write_text(
                f"# {profile['name']} 규칙\n\n사람이 승인한 규칙만 이 파일에 기록합니다.\n",
                encoding="utf-8",
            )
        for name, content in MODULE_SUPPORT_FILES.items():
            path = root / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        for path in root.glob("*.md"):
            self._register_file(path, scope="module", module_id=module_id, owner=module_id)

    def _relative(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.memory_root)).replace("\\", "/")

    def _register_file(
        self,
        path: Path,
        *,
        scope: str,
        module_id: str | None,
        owner: str,
        approved_by: str | None = None,
        increment: bool = False,
    ) -> None:
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        rel = self._relative(path)
        now = self.now()
        with self._connect() as conn:
            current = conn.execute(
                "SELECT version FROM memory_registry WHERE path = ?", (rel,)
            ).fetchone()
            version = (int(current["version"]) + 1) if current and increment else (int(current["version"]) if current else 1)
            conn.execute(
                """
                INSERT INTO memory_registry(path, scope, module_id, status, version, owner,
                    approved_by, last_reviewed_at, content_hash, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    scope=excluded.scope,
                    module_id=excluded.module_id,
                    status=excluded.status,
                    version=excluded.version,
                    owner=excluded.owner,
                    approved_by=COALESCE(excluded.approved_by, memory_registry.approved_by),
                    last_reviewed_at=COALESCE(excluded.last_reviewed_at, memory_registry.last_reviewed_at),
                    content_hash=excluded.content_hash,
                    updated_at=excluded.updated_at
                """,
                (
                    rel,
                    scope,
                    module_id,
                    version,
                    owner,
                    approved_by,
                    now if approved_by else None,
                    self._hash_text(content),
                    now,
                ),
            )

    def _audit(
        self,
        conn: sqlite3.Connection,
        action: str,
        entity_type: str,
        entity_id: str | int,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            "INSERT INTO audit_log(action, entity_type, entity_id, actor, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                action,
                entity_type,
                str(entity_id),
                actor,
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                self.now(),
            ),
        )

    def submit_feedback(self, record: FeedbackRecord | dict[str, Any]) -> dict[str, Any]:
        if isinstance(record, dict):
            record = FeedbackRecord(
                module_id=str(record.get("module_id", "")),
                item_ref=str(record.get("item_ref", "")),
                original_text=str(record.get("original_text", "")),
                revised_text=str(record.get("revised_text", "")),
                reason_code=str(record.get("reason_code", "general")),
                reason_detail=str(record.get("reason_detail", "")),
                reviewer=str(record.get("reviewer", "")),
                rule_key=str(record.get("rule_key", record.get("reason_code", "general"))),
                review_seconds=int(record.get("review_seconds", 0) or 0),
            )
        values = asdict(record)
        for key in ("module_id", "item_ref", "revised_text", "reason_code", "reason_detail", "reviewer", "rule_key"):
            if not str(values[key]).strip():
                raise ValueError(f"필수 입력값이 비었습니다: {key}")
        module_id = self._slug(record.module_id)
        rule_key = self._slug(record.rule_key)
        reason_code = self._slug(record.reason_code)
        self.ensure_module_files(module_id)
        rule_text = record.reason_detail.strip()
        fingerprint_source = "|".join(
            (module_id, rule_key, self._normalize(reason_code), self._normalize(rule_text))
        )
        fingerprint = self._hash_text(fingerprint_source)
        risk_level = "protected" if reason_code in RISK_REASON_CODES else "normal"
        now = self.now()
        target_file = self._profile(module_id)["target_file"]

        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO feedback(module_id, item_ref, original_text, revised_text,
                    reason_code, reason_detail, reviewer, rule_key, review_seconds, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    module_id,
                    record.item_ref.strip(),
                    record.original_text,
                    record.revised_text,
                    reason_code,
                    record.reason_detail.strip(),
                    record.reviewer.strip(),
                    rule_key,
                    max(0, int(record.review_seconds)),
                    now,
                ),
            )
            feedback_id = int(cursor.lastrowid)
            candidate = conn.execute(
                "SELECT * FROM rule_candidates WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
            if candidate:
                occurrences = int(candidate["occurrences"]) + 1
                next_status = candidate["status"]
                if next_status in {"collecting", "pending"} and occurrences >= self.candidate_threshold:
                    next_status = "pending"
                conn.execute(
                    "UPDATE rule_candidates SET occurrences=?, status=?, updated_at=? WHERE id=?",
                    (occurrences, next_status, now, candidate["id"]),
                )
                candidate_id = int(candidate["id"])
            else:
                initial_status = "pending" if self.candidate_threshold <= 1 else "collecting"
                c = conn.execute(
                    """
                    INSERT INTO rule_candidates(module_id, rule_key, rule_text, reason_code,
                        reason_detail, fingerprint, occurrences, status, risk_level, target_file,
                        created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        module_id,
                        rule_key,
                        rule_text,
                        reason_code,
                        record.reason_detail.strip(),
                        fingerprint,
                        initial_status,
                        risk_level,
                        target_file,
                        now,
                        now,
                    ),
                )
                candidate_id = int(c.lastrowid)
            self._audit(
                conn,
                "feedback_submitted",
                "feedback",
                feedback_id,
                record.reviewer.strip(),
                {"module_id": module_id, "candidate_id": candidate_id, "rule_key": rule_key},
            )
        self._write_first10_log(module_id)
        self._write_candidate_queue(module_id)
        return {
            "feedback_id": feedback_id,
            "candidate": self.get_candidate(candidate_id),
        }

    def create_manual_candidate(
        self,
        *,
        module_id: str,
        rule_key: str,
        rule_text: str,
        reason_detail: str,
        actor: str,
        reason_code: str = "manual",
        target_file: str | None = None,
    ) -> dict[str, Any]:
        module_id = self._slug(module_id)
        rule_key = self._slug(rule_key)
        reason_code = self._slug(reason_code)
        if not rule_text.strip() or not reason_detail.strip() or not actor.strip():
            raise ValueError("규칙 문장, 근거, 작성자는 필수입니다.")
        self.ensure_module_files(module_id)
        fingerprint = self._hash_text(
            "manual|" + module_id + "|" + rule_key + "|" + self._normalize(rule_text)
        )
        now = self.now()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM rule_candidates WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            if existing:
                return self.get_candidate(int(existing["id"]))
            cursor = conn.execute(
                """
                INSERT INTO rule_candidates(module_id, rule_key, rule_text, reason_code,
                    reason_detail, fingerprint, occurrences, status, risk_level, target_file,
                    created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, 'pending', ?, ?, ?, ?)
                """,
                (
                    module_id,
                    rule_key,
                    rule_text.strip(),
                    reason_code,
                    reason_detail.strip(),
                    fingerprint,
                    "protected" if reason_code in RISK_REASON_CODES else "normal",
                    target_file or self._profile(module_id)["target_file"],
                    now,
                    now,
                ),
            )
            candidate_id = int(cursor.lastrowid)
            self._audit(conn, "candidate_created", "rule_candidate", candidate_id, actor, {"manual": True})
        self._write_candidate_queue(module_id)
        return self.get_candidate(candidate_id)

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def get_candidate(self, candidate_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM rule_candidates WHERE id=?", (int(candidate_id),)
            ).fetchone()
        if not row:
            raise KeyError(f"규칙 후보를 찾지 못했습니다: {candidate_id}")
        return dict(row)

    def list_feedback(self, module_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = min(max(1, int(limit)), 500)
        with self._connect() as conn:
            if module_id:
                rows = conn.execute(
                    "SELECT * FROM feedback WHERE module_id=? ORDER BY id DESC LIMIT ?",
                    (self._slug(module_id), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM feedback ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(row) for row in rows]

    def list_candidates(
        self,
        module_id: str | None = None,
        statuses: Iterable[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if module_id:
            clauses.append("module_id=?")
            values.append(self._slug(module_id))
        statuses_list = [str(value) for value in statuses or [] if str(value)]
        if statuses_list:
            clauses.append("status IN (" + ",".join("?" for _ in statuses_list) + ")")
            values.extend(statuses_list)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        values.append(min(max(1, int(limit)), 500))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM rule_candidates" + where + " ORDER BY updated_at DESC, id DESC LIMIT ?",
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def _target_for_candidate(self, candidate: sqlite3.Row | dict[str, Any]) -> Path:
        module_id = self._slug(str(candidate["module_id"]))
        target_file = Path(str(candidate["target_file"]))
        if target_file.name != str(target_file) or target_file.suffix.lower() != ".md":
            raise InvalidMemoryPathError("대상 파일은 모듈 폴더 바로 아래의 MD 파일이어야 합니다.")
        return self._safe_memory_path(Path("modules") / module_id / target_file.name)

    @staticmethod
    def _rule_block(candidate: sqlite3.Row | dict[str, Any], approved_by: str, approved_at: str) -> str:
        risk = "보호 규칙·항상 사람 승인" if candidate["risk_level"] == "protected" else "일반 규칙"
        return (
            f"\n\n## {candidate['rule_key']}\n\n"
            f"- 규칙: {str(candidate['rule_text']).strip()}\n"
            f"- 근거: 동일 수정 {candidate['occurrences']}건 · {str(candidate['reason_detail']).strip()}\n"
            f"- 위험 수준: {risk}\n"
            f"- 승인자: {approved_by}\n"
            f"- 승인 시각: {approved_at}\n"
            f"- 규칙 후보 ID: {candidate['id']}\n"
        )

    def approve_candidate(
        self,
        candidate_id: int,
        *,
        approved_by: str,
        note: str = "",
        override_conflict: bool = False,
    ) -> dict[str, Any]:
        if not approved_by.strip():
            raise ValueError("승인자는 필수입니다.")
        now = self.now()
        with self._lock, self._connect() as conn:
            candidate = conn.execute(
                "SELECT * FROM rule_candidates WHERE id=?", (int(candidate_id),)
            ).fetchone()
            if not candidate:
                raise KeyError(f"규칙 후보를 찾지 못했습니다: {candidate_id}")
            if candidate["status"] == "approved":
                return dict(candidate)
            if candidate["status"] not in {"pending", "conflict", "collecting"}:
                raise FeedbackEngineError(f"승인할 수 없는 상태입니다: {candidate['status']}")

            conflict = conn.execute(
                """
                SELECT rv.*, rc.rule_text AS active_rule_text
                FROM rule_versions rv
                JOIN rule_candidates rc ON rc.id = rv.candidate_id
                WHERE rv.module_id=? AND rv.rule_key=? AND rv.active=1
                ORDER BY rv.id DESC LIMIT 1
                """,
                (candidate["module_id"], candidate["rule_key"]),
            ).fetchone()
            if conflict and self._normalize(str(conflict["active_rule_text"])) != self._normalize(str(candidate["rule_text"])):
                if not override_conflict:
                    conn.execute(
                        "UPDATE rule_candidates SET status='conflict', updated_at=?, decision_note=? WHERE id=?",
                        (now, "기존 활성 규칙과 충돌", candidate_id),
                    )
                    self._audit(
                        conn,
                        "candidate_conflict",
                        "rule_candidate",
                        candidate_id,
                        approved_by.strip(),
                        {"active_candidate_id": conflict["candidate_id"]},
                    )
                    raise RuleConflictError("같은 규칙 키에 다른 활성 규칙이 있습니다. 기존 규칙을 확인한 뒤 충돌 덮어쓰기를 승인하십시오.")
                conn.execute(
                    "UPDATE rule_versions SET active=0 WHERE module_id=? AND rule_key=? AND active=1",
                    (candidate["module_id"], candidate["rule_key"]),
                )

            target = self._target_for_candidate(candidate)
            target.parent.mkdir(parents=True, exist_ok=True)
            previous = target.read_text(encoding="utf-8") if target.exists() else ""
            new_content = previous.rstrip() + self._rule_block(candidate, approved_by.strip(), now) + "\n"
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(new_content, encoding="utf-8")
            temporary.replace(target)
            current_version = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS value FROM rule_versions WHERE target_path=?",
                (self._relative(target),),
            ).fetchone()
            version = int(current_version["value"]) + 1
            conn.execute(
                """
                INSERT INTO rule_versions(candidate_id, module_id, rule_key, target_path,
                    version, previous_content, new_content, active, approved_by, approved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    candidate_id,
                    candidate["module_id"],
                    candidate["rule_key"],
                    self._relative(target),
                    version,
                    previous,
                    new_content,
                    approved_by.strip(),
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE rule_candidates
                SET status='approved', updated_at=?, decided_by=?, decision_note=?
                WHERE id=?
                """,
                (now, approved_by.strip(), note.strip(), candidate_id),
            )
            self._audit(
                conn,
                "candidate_approved",
                "rule_candidate",
                candidate_id,
                approved_by.strip(),
                {"target_path": self._relative(target), "version": version, "override_conflict": bool(override_conflict)},
            )
        self._register_file(
            target,
            scope="module",
            module_id=str(candidate["module_id"]),
            owner=str(candidate["module_id"]),
            approved_by=approved_by.strip(),
            increment=True,
        )
        self._write_candidate_queue(str(candidate["module_id"]))
        return self.get_candidate(candidate_id)

    def reject_candidate(self, candidate_id: int, *, rejected_by: str, note: str = "") -> dict[str, Any]:
        if not rejected_by.strip():
            raise ValueError("거절자는 필수입니다.")
        now = self.now()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM rule_candidates WHERE id=?", (candidate_id,)).fetchone()
            if not row:
                raise KeyError(f"규칙 후보를 찾지 못했습니다: {candidate_id}")
            if row["status"] == "approved":
                raise FeedbackEngineError("활성 규칙은 먼저 롤백해야 합니다.")
            conn.execute(
                "UPDATE rule_candidates SET status='rejected', updated_at=?, decided_by=?, decision_note=? WHERE id=?",
                (now, rejected_by.strip(), note.strip(), candidate_id),
            )
            self._audit(conn, "candidate_rejected", "rule_candidate", candidate_id, rejected_by.strip(), {"note": note})
        self._write_candidate_queue(str(row["module_id"]))
        return self.get_candidate(candidate_id)

    def rollback_candidate(self, candidate_id: int, *, rolled_back_by: str, note: str = "") -> dict[str, Any]:
        if not rolled_back_by.strip():
            raise ValueError("롤백 실행자는 필수입니다.")
        now = self.now()
        with self._lock, self._connect() as conn:
            candidate = conn.execute("SELECT * FROM rule_candidates WHERE id=?", (candidate_id,)).fetchone()
            if not candidate:
                raise KeyError(f"규칙 후보를 찾지 못했습니다: {candidate_id}")
            version = conn.execute(
                "SELECT * FROM rule_versions WHERE candidate_id=? AND active=1 ORDER BY id DESC LIMIT 1",
                (candidate_id,),
            ).fetchone()
            if not version:
                raise FeedbackEngineError("롤백할 활성 규칙 버전이 없습니다.")
            target = self._safe_memory_path(version["target_path"])
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(str(version["previous_content"]), encoding="utf-8")
            temporary.replace(target)
            conn.execute(
                "UPDATE rule_versions SET active=0, rollback_by=?, rollback_at=? WHERE id=?",
                (rolled_back_by.strip(), now, version["id"]),
            )
            conn.execute(
                "UPDATE rule_candidates SET status='rolled_back', updated_at=?, decided_by=?, decision_note=? WHERE id=?",
                (now, rolled_back_by.strip(), note.strip(), candidate_id),
            )
            previous = conn.execute(
                """
                SELECT id, candidate_id FROM rule_versions
                WHERE module_id=? AND rule_key=? AND id < ?
                ORDER BY id DESC LIMIT 1
                """,
                (candidate["module_id"], candidate["rule_key"], version["id"]),
            ).fetchone()
            if previous:
                conn.execute("UPDATE rule_versions SET active=1 WHERE id=?", (previous["id"],))
                conn.execute(
                    "UPDATE rule_candidates SET status='approved', updated_at=? WHERE id=?",
                    (now, previous["candidate_id"]),
                )
            self._audit(
                conn,
                "candidate_rolled_back",
                "rule_candidate",
                candidate_id,
                rolled_back_by.strip(),
                {"target_path": version["target_path"], "version": version["version"], "note": note},
            )
        self._register_file(
            target,
            scope="module",
            module_id=str(candidate["module_id"]),
            owner=str(candidate["module_id"]),
            approved_by=rolled_back_by.strip(),
            increment=True,
        )
        self._write_candidate_queue(str(candidate["module_id"]))
        return self.get_candidate(candidate_id)

    def list_registry(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM memory_registry ORDER BY scope, module_id, path").fetchall()
        return [dict(row) for row in rows]

    def list_audit(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                (min(max(1, int(limit)), 1000),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item.pop("details_json"))
            except json.JSONDecodeError:
                item["details"] = {"raw": item.pop("details_json")}
            result.append(item)
        return result

    def first10_metrics(self, module_id: str) -> dict[str, Any]:
        module_id = self._slug(module_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM feedback WHERE module_id=? ORDER BY id ASC LIMIT 10", (module_id,)
            ).fetchall()
        total_seconds = sum(int(row["review_seconds"]) for row in rows)
        return {
            "module_id": module_id,
            "count": len(rows),
            "review_seconds": total_seconds,
            "average_review_seconds": round(total_seconds / len(rows), 1) if rows else 0,
            "reason_counts": {
                code: sum(1 for row in rows if row["reason_code"] == code)
                for code in sorted({str(row["reason_code"]) for row in rows})
            },
        }

    def _write_first10_log(self, module_id: str) -> None:
        module_id = self._slug(module_id)
        rows = list(reversed(self.list_feedback(module_id, limit=10)))
        metrics = self.first10_metrics(module_id)
        path = self.module_root(module_id) / "FIRST_10_LOG.md"
        lines = [
            "# 첫 10건 교육 기록",
            "",
            f"- 모듈: `{module_id}`",
            f"- 기록 수: {metrics['count']}/10",
            f"- 총 검토 시간: {metrics['review_seconds']}초",
            f"- 평균 검토 시간: {metrics['average_review_seconds']}초",
            "",
            "## 수정 기록",
            "",
        ]
        if not rows:
            lines.append("아직 기록이 없습니다.")
        for index, row in enumerate(rows, 1):
            lines.extend(
                [
                    f"### {index}. {row['item_ref']}",
                    "",
                    f"- 수정 이유 코드: `{row['reason_code']}`",
                    f"- 규칙 키: `{row['rule_key']}`",
                    f"- 수정 이유: {row['reason_detail']}",
                    f"- 검토자: {row['reviewer']}",
                    f"- 검토 시간: {row['review_seconds']}초",
                    f"- 기록 시각: {row['created_at']}",
                    "",
                ]
            )
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self._register_file(path, scope="module", module_id=module_id, owner=module_id, increment=True)

    def _write_candidate_queue(self, module_id: str) -> None:
        module_id = self._slug(module_id)
        candidates = self.list_candidates(module_id=module_id, limit=500)
        path = self.module_root(module_id) / "RULE_CANDIDATES.md"
        lines = [
            "# 규칙 후보",
            "",
            "> 이 파일은 검토용입니다. 상태가 `approved`가 되기 전에는 실제 규칙으로 사용하지 않습니다.",
            "",
        ]
        if not candidates:
            lines.append("후보가 없습니다.")
        for item in candidates:
            lines.extend(
                [
                    f"## 후보 {item['id']} · {item['rule_key']}",
                    "",
                    f"- 상태: `{item['status']}`",
                    f"- 반복 횟수: {item['occurrences']}",
                    f"- 규칙 문장: {item['rule_text']}",
                    f"- 근거: {item['reason_detail']}",
                    f"- 위험 수준: `{item['risk_level']}`",
                    f"- 대상 파일: `{item['target_file']}`",
                    "",
                ]
            )
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self._register_file(path, scope="module", module_id=module_id, owner=module_id, increment=True)
