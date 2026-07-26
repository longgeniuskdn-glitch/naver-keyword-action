from __future__ import annotations

import json
import re
from typing import Any, Iterable

MODULE_ID = "part05-work-intake"
MODE_RANK = {"standard": 0, "prepare_only": 1, "human_only": 2}
VALID_URGENCY = {"low", "medium", "high"}
VALID_MODES = set(MODE_RANK)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def slug_rule_key(keyword: str) -> str:
    clean = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", normalize_text(keyword))
    clean = clean.strip("-._")
    if not clean:
        raise ValueError("규칙 적용 키워드를 입력하세요.")
    return f"keyword-{clean[:80]}"


def canonical_rule_detail(
    *,
    keyword: str,
    category: str,
    assigned_team: str,
    urgency: str,
    handling_mode: str,
) -> str:
    return (
        f"제목·내용에 '{keyword.strip()}'이 포함되면 "
        f"분류를 '{category.strip()}', 담당을 '{assigned_team.strip()}', "
        f"긴급도를 '{urgency}', 처리 모드를 '{handling_mode}'로 제안한다."
    )


def build_rule_payload(
    *,
    keyword: str,
    category: str,
    assigned_team: str,
    urgency: str,
    handling_mode: str,
    source_intake_id: int,
    note: str = "",
) -> dict[str, Any]:
    keyword = normalize_text(keyword)
    category = str(category or "").strip()
    assigned_team = str(assigned_team or "").strip()
    urgency = str(urgency or "").strip()
    handling_mode = str(handling_mode or "").strip()
    if not keyword:
        raise ValueError("규칙 적용 키워드를 입력하세요.")
    if not category or not assigned_team:
        raise ValueError("수정할 분류와 담당을 입력하세요.")
    if urgency not in VALID_URGENCY:
        raise ValueError("허용되지 않은 긴급도입니다.")
    if handling_mode not in VALID_MODES:
        raise ValueError("허용되지 않은 처리 모드입니다.")
    return {
        "schema_version": 1,
        "trigger_keyword": keyword,
        "category": category,
        "assigned_team": assigned_team,
        "urgency": urgency,
        "handling_mode": handling_mode,
        "source_intake_id": int(source_intake_id),
        "note": str(note or "").strip(),
    }


def encode_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def decode_payload(value: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if isinstance(value, dict):
        data = dict(value)
    else:
        try:
            data = json.loads(str(value or ""))
        except (TypeError, json.JSONDecodeError):
            return None
    required = {"trigger_keyword", "category", "assigned_team", "urgency", "handling_mode"}
    if not isinstance(data, dict) or not required.issubset(data):
        return None
    if str(data.get("urgency")) not in VALID_URGENCY:
        return None
    if str(data.get("handling_mode")) not in VALID_MODES:
        return None
    if not normalize_text(str(data.get("trigger_keyword", ""))):
        return None
    return data


def stricter_mode(first: str, second: str) -> str:
    if first not in MODE_RANK or second not in MODE_RANK:
        raise ValueError("처리 모드가 올바르지 않습니다.")
    return first if MODE_RANK[first] >= MODE_RANK[second] else second


def protect_handling_mode(requested: str, minimum: str) -> str:
    """학습 규칙이 기존 안전 경계를 낮추지 못하게 한다."""
    return stricter_mode(requested, minimum)


def choose_matching_rule(text: str, rules: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = normalize_text(text)
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for rule in rules:
        payload = decode_payload(rule.get("revised_text") or rule.get("payload"))
        if not payload:
            continue
        keyword = normalize_text(str(payload["trigger_keyword"]))
        if keyword and keyword in normalized:
            version = int(rule.get("version", 0) or 0)
            candidates.append((len(keyword), version, {**rule, "payload": payload}))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def apply_approved_rules(
    base_result: dict[str, Any],
    *,
    subject: str,
    body: str,
    rules: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    result = dict(base_result)
    matched = choose_matching_rule(f"{subject} {body}", rules)
    if not matched:
        return result
    payload = matched["payload"]
    result["category"] = str(payload["category"])
    result["assigned_team"] = str(payload["assigned_team"])
    result["urgency"] = str(payload["urgency"])
    result["handling_mode"] = protect_handling_mode(
        str(payload["handling_mode"]),
        str(base_result.get("handling_mode", "standard")),
    )
    result["learning_rule"] = {
        "candidate_id": matched.get("candidate_id"),
        "rule_key": matched.get("rule_key"),
        "version": matched.get("version"),
        "trigger_keyword": payload["trigger_keyword"],
    }
    return result


def list_active_rule_payloads(engine: Any, module_id: str = MODULE_ID) -> list[dict[str, Any]]:
    """승인·활성 상태인 규칙과 마지막 구조화 수정 결과를 조회한다."""
    with engine._connect() as conn:  # 공통 엔진의 동일 SQLite 연결을 재사용한다.
        rows = conn.execute(
            """
            SELECT rc.id AS candidate_id, rc.module_id, rc.rule_key, rc.rule_text,
                   rc.risk_level, rv.version, rv.approved_by, rv.approved_at,
                   (
                       SELECT f.revised_text
                       FROM feedback f
                       WHERE f.module_id=rc.module_id AND f.rule_key=rc.rule_key
                       ORDER BY f.id DESC LIMIT 1
                   ) AS revised_text
            FROM rule_versions rv
            JOIN rule_candidates rc ON rc.id=rv.candidate_id
            WHERE rv.active=1 AND rc.status='approved' AND rc.module_id=?
            ORDER BY rv.version DESC, rc.id DESC
            """,
            (module_id,),
        ).fetchall()
    return [dict(row) for row in rows]
