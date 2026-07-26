#!/usr/bin/env python3
"""PART 05 직접 학습 루프 어댑터.

기존 업무 접수·분류실의 핵심 로직과 SQLite를 유지하면서 다음 기능을 연결한다.
- 업무별 분류 수정 화면
- 수정 전/후와 이유를 공통 피드백 엔진에 저장
- 반복 수정 후보 생성과 사람 승인
- 승인된 규칙을 다음 분류에 우선 적용
- 계약·법률·결제·환불·개인정보 안전 경계 유지
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

MODULE_ROOT = Path(__file__).resolve().parent


def _find_system_root() -> Path:
    candidates = [MODULE_ROOT, MODULE_ROOT.parent, MODULE_ROOT.parent.parent]
    for candidate in candidates:
        if (candidate / "common_feedback").is_dir():
            return candidate
    raise RuntimeError("common_feedback 폴더를 찾지 못했습니다.")


SYSTEM_ROOT = _find_system_root()
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

import app_core as base  # noqa: E402
from common_feedback import FeedbackEngine, FeedbackEngineError, RuleConflictError  # noqa: E402
from learning_rules import (  # noqa: E402
    MODE_RANK,
    MODULE_ID,
    apply_approved_rules,
    build_rule_payload,
    canonical_rule_detail,
    decode_payload,
    encode_payload,
    list_active_rule_payloads,
    slug_rule_key,
)

APP_VERSION = "1.2.0-learning"
base.APP_VERSION = APP_VERSION

FEEDBACK_DB = Path(os.environ.get("AI_FEEDBACK_DB", SYSTEM_ROOT / "runtime" / "feedback.db"))
MEMORY_ROOT = Path(os.environ.get("AI_MEMORY_ROOT", SYSTEM_ROOT / "memory"))
_ENGINE: FeedbackEngine | None = None
_ENGINE_LOCK = threading.RLock()
_ORIGINAL_CLASSIFY = base.classify_intake
_ORIGINAL_ADD_INTAKE = base.add_intake


def feedback_engine() -> FeedbackEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = FeedbackEngine(FEEDBACK_DB, MEMORY_ROOT, candidate_threshold=2)
        return _ENGINE


def learned_classify_intake(subject: str, body: str) -> dict[str, Any]:
    original = _ORIGINAL_CLASSIFY(subject, body)
    rules = list_active_rule_payloads(feedback_engine(), MODULE_ID)
    return apply_approved_rules(original, subject=subject, body=body, rules=rules)


def _classification_snapshot(row: Any) -> dict[str, Any]:
    return {
        "intake_id": int(row["id"]),
        "subject": str(row["subject"]),
        "body": str(row["body"]),
        "category": str(row["category"]),
        "assigned_team": str(row["assigned_team"]),
        "urgency": str(row["urgency"]),
        "handling_mode": str(row["handling_mode"]),
        "risk_flags": json.loads(row["risk_flags"] or "[]"),
    }


def _protected_reason_code(row: Any) -> str:
    try:
        flags = set(json.loads(row["risk_flags"] or "[]"))
    except json.JSONDecodeError:
        flags = set()
    for code in ("legal", "contract", "payment", "refund", "personal_data", "public_response"):
        if code in flags:
            return "privacy" if code == "personal_data" else code
    return "routing"


def add_intake(data: dict[str, Any], db_path: Path | str = base.DB_PATH) -> int:
    subject = str(data.get("subject", ""))
    body = str(data.get("body", ""))
    baseline = _ORIGINAL_CLASSIFY(subject, body)
    intake_id = _ORIGINAL_ADD_INTAKE(data, db_path)
    row = base.get_intake(intake_id, db_path)
    if row is not None:
        changed = any(
            str(row[key]) != str(baseline.get(key, ""))
            for key in ("category", "assigned_team", "urgency", "handling_mode")
        )
        if changed:
            with base.connect(db_path) as conn:
                base.log_action(
                    conn,
                    intake_id,
                    "approved_learning_rule_applied",
                    json.dumps(
                        {
                            "before": baseline,
                            "after": _classification_snapshot(row),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
    return intake_id


def correct_intake(
    intake_id: int,
    data: dict[str, Any],
    db_path: Path | str = base.DB_PATH,
    engine: FeedbackEngine | None = None,
) -> dict[str, Any]:
    row = base.get_intake(intake_id, db_path)
    if row is None:
        raise ValueError("수정할 업무를 찾지 못했습니다.")

    reviewer = str(data.get("reviewer", "")).strip()
    keyword = str(data.get("trigger_keyword", "")).strip()
    category = str(data.get("category", "")).strip()
    assigned_team = str(data.get("assigned_team", "")).strip()
    urgency = str(data.get("urgency", "")).strip()
    handling_mode = str(data.get("handling_mode", "")).strip()
    note = str(data.get("note", "")).strip()
    review_seconds = int(data.get("review_seconds", 0) or 0)
    if not reviewer:
        raise ValueError("검토자 이름을 입력하세요.")

    minimum = _ORIGINAL_CLASSIFY(str(row["subject"]), str(row["body"]))
    minimum_mode = str(minimum["handling_mode"])
    if handling_mode not in MODE_RANK:
        raise ValueError("처리 모드가 올바르지 않습니다.")
    if MODE_RANK[handling_mode] < MODE_RANK[minimum_mode]:
        raise ValueError(
            f"이 업무는 안전상 최소 '{base.MODE_LABELS[minimum_mode]}'가 필요합니다. "
            "학습 규칙으로 계약·법률·결제·개인정보 경계를 낮출 수 없습니다."
        )

    payload = build_rule_payload(
        keyword=keyword,
        category=category,
        assigned_team=assigned_team,
        urgency=urgency,
        handling_mode=handling_mode,
        source_intake_id=intake_id,
        note=note,
    )
    before = _classification_snapshot(row)
    timestamp = base.now_text()
    with base.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE intakes
            SET category=?, urgency=?, assigned_team=?, handling_mode=?, status='triaged', updated_at=?
            WHERE id=?
            """,
            (category, urgency, assigned_team, handling_mode, timestamp, intake_id),
        )
        base.log_action(
            conn,
            intake_id,
            "classification_corrected",
            json.dumps(
                {"before": before, "after": payload, "reviewer": reviewer, "note": note},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    detail = canonical_rule_detail(
        keyword=keyword,
        category=category,
        assigned_team=assigned_team,
        urgency=urgency,
        handling_mode=handling_mode,
    )
    result = (engine or feedback_engine()).submit_feedback(
        {
            "module_id": MODULE_ID,
            "item_ref": f"intake-{intake_id}",
            "original_text": json.dumps(before, ensure_ascii=False, sort_keys=True),
            "revised_text": encode_payload(payload),
            "reason_code": _protected_reason_code(row),
            "reason_detail": detail,
            "reviewer": reviewer,
            "rule_key": slug_rule_key(keyword),
            "review_seconds": max(0, review_seconds),
        }
    )
    return result


def _options(values: list[str], selected: str) -> str:
    return "".join(
        f"<option value='{base.escape(value)}'{' selected' if value == selected else ''}>{base.escape(value)}</option>"
        for value in values
    )


def render_correction_page(intake_id: int, db_path: Path | str = base.DB_PATH, notice: str = "") -> str:
    row = base.get_intake(intake_id, db_path)
    if row is None:
        raise ValueError("수정할 업무를 찾지 못했습니다.")
    categories = list(base.TEAM_MAP.keys())
    teams = sorted(set(base.TEAM_MAP.values()))
    notice_html = f"<div class='notice error'>{base.escape(notice)}</div>" if notice else ""
    return base.layout(
        f"""
{notice_html}
<div class='card'>
  <div class='toolbar'><a class='button secondary' href='/'>← 대기열로 돌아가기</a></div>
  <h2>분류 수정과 AI 교육</h2>
  <div class='notice'>이 수정은 현재 업무에 즉시 반영되고, 같은 수정이 반복되면 규칙 후보가 됩니다. 규칙은 사람 승인 전에는 다음 업무에 적용되지 않습니다.</div>
  <div class='form-grid'>
    <div class='full'><label>현재 업무</label><strong>{base.escape(row['subject'])}</strong><div>{base.escape(row['body'])}</div></div>
    <div><label>현재 분류</label><div class='badge'>{base.escape(row['category'])}</div></div>
    <div><label>현재 담당</label><div class='badge'>{base.escape(row['assigned_team'])}</div></div>
    <div><label>현재 처리 모드</label><div class='badge'>{base.escape(base.MODE_LABELS[row['handling_mode']])}</div></div>
  </div>
  <form method='post' action='/correct/{intake_id}' class='section'>
    <div class='form-grid'>
      <div><label>수정 분류</label><select name='category'>{_options(categories, str(row['category']))}</select></div>
      <div><label>수정 담당</label><select name='assigned_team'>{_options(teams, str(row['assigned_team']))}</select></div>
      <div><label>수정 긴급도</label><select name='urgency'>{_options(['low','medium','high'], str(row['urgency']))}</select></div>
      <div><label>수정 처리 모드</label><select name='handling_mode'>{_options(['standard','prepare_only','human_only'], str(row['handling_mode']))}</select></div>
      <div class='wide'><label>이 규칙을 적용할 핵심 키워드</label><input name='trigger_keyword' required placeholder='예: 배송, 파트너, 세금계산서'></div>
      <div><label>검토자</label><input name='reviewer' required placeholder='예: Kris'></div>
      <div><label>검토 시간(초)</label><input name='review_seconds' type='number' min='0' value='0'></div>
      <div class='full'><label>이번 수정 메모</label><textarea name='note' placeholder='왜 수정했는지 추가 메모를 남깁니다.'></textarea></div>
      <div class='full'><button class='green' type='submit'>현재 업무 수정 + 피드백 저장</button></div>
    </div>
  </form>
  <div class='notice error'>계약·법률·결제·환불·개인정보 업무의 처리 모드는 더 안전하게 높일 수 있지만 낮출 수 없습니다.</div>
</div>
"""
    )


def render_home(db_path: Path | str = base.DB_PATH, notice: str = "", error: bool = False) -> str:
    rows = base.list_intakes(db_path)
    stats = base.summary(db_path)
    engine = feedback_engine()
    active_rules = list_active_rule_payloads(engine, MODULE_ID)
    pending = engine.list_candidates(MODULE_ID, statuses=["pending", "conflict"], limit=30)
    notice_html = f"<div class='notice{' error' if error else ''}'>{base.escape(notice)}</div>" if notice else ""
    table_rows: list[str] = []
    for row in rows:
        actions = f"<a class='button secondary' href='/correct/{row['id']}'>분류 수정</a> "
        if row["status"] == "triaged":
            actions += f"<form method='post' action='/approve/{row['id']}' style='display:inline'><button class='green'>분류 승인</button></form> <form method='post' action='/reject/{row['id']}' style='display:inline'><button class='red'>보류</button></form>"
        elif row["status"] == "approved":
            actions += f"<form method='post' action='/done/{row['id']}' style='display:inline'><button>완료</button></form>"
        table_rows.append(
            f"""
<tr><td><strong>{base.escape(row['subject'])}</strong><div class='muted'>{base.escape(row['channel'])} · {base.escape(row['sender'])}</div><div>{base.escape(row['body'][:120])}</div></td>
<td>{base.escape(row['category'])}<div class='muted'>{base.escape(row['assigned_team'])}</div></td>
<td class='urgency-{row['urgency']}'>{row['urgency']}</td>
<td class='mode-{row['handling_mode']}'>{base.MODE_LABELS[row['handling_mode']]}<div class='muted'>{base.escape(base.flag_text(row['risk_flags']))}</div></td>
<td>{base.escape(row['status'])}</td><td>{actions}</td></tr>"""
        )
    table_body = "".join(table_rows) if table_rows else "<tr><td colspan='6' class='empty'>접수된 업무가 없습니다. 샘플을 넣거나 첫 업무를 등록하세요.</td></tr>"

    pending_rows: list[str] = []
    for item in pending:
        pending_rows.append(
            f"""
<tr><td>{base.escape(item['rule_key'])}<div class='muted'>{base.escape(item['rule_text'])}</div></td><td>{item['occurrences']}회</td><td>{base.escape(item['risk_level'])}</td>
<td><form method='post' action='/learning/approve/{item['id']}' style='display:inline'><input name='actor' required placeholder='승인자' style='width:110px'><button class='green'>승인</button></form>
<form method='post' action='/learning/reject/{item['id']}' style='display:inline'><input name='actor' required placeholder='거절자' style='width:110px'><button class='red'>거절</button></form></td></tr>"""
        )
    pending_body = "".join(pending_rows) if pending_rows else "<tr><td colspan='4' class='empty'>사람 승인을 기다리는 반복 규칙이 없습니다.</td></tr>"

    active_rows: list[str] = []
    for item in active_rules:
        payload = decode_payload(item.get("revised_text")) or {}
        active_rows.append(
            f"<tr><td>{base.escape(payload.get('trigger_keyword'))}</td><td>{base.escape(payload.get('category'))}</td><td>{base.escape(payload.get('assigned_team'))}</td><td>{base.escape(payload.get('urgency'))}</td><td>{base.escape(payload.get('handling_mode'))}</td><td>v{item.get('version')}</td></tr>"
        )
    active_body = "".join(active_rows) if active_rows else "<tr><td colspan='6' class='empty'>아직 승인되어 다음 분류에 적용되는 규칙이 없습니다.</td></tr>"

    return base.layout(
        f"""
{notice_html}<div class='grid'>
<div class='card metric'><strong>{stats['total']}</strong><span>전체 접수</span></div>
<div class='card metric'><strong>{stats['pending_count']}</strong><span>승인 대기</span></div>
<div class='card metric'><strong>{stats['high_count']}</strong><span>긴급</span></div>
<div class='card metric'><strong>{stats['human_count']}</strong><span>사람 직접 처리</span></div>
</div>
<div class='section card'><h2>업무 한 건 접수</h2><form method='post' action='/intakes'><div class='form-grid'>
<div><label>유입 채널</label><select name='channel'><option>email</option><option>webform</option><option>memo</option><option>chat</option><option>csv</option></select></div>
<div><label>보낸 사람</label><input name='sender' placeholder='이름 또는 이메일'></div>
<div class='wide'><label>제목</label><input name='subject' required placeholder='예: 배송이 아직 도착하지 않았습니다'></div>
<div class='full'><label>내용</label><textarea name='body' required></textarea></div>
<div class='full'><button type='submit'>접수하고 분류</button></div></div></form></div>
<div class='section card'><h2>CSV 붙여넣기</h2><div class='muted'>첫 줄: channel,sender,subject,body · subject와 body는 필수입니다.</div><form method='post' action='/import'><textarea name='csv_text' placeholder='channel,sender,subject,body&#10;email,user@example.com,배송 문의,운송장 조회가 안 됩니다'></textarea><button type='submit'>CSV 가져오기</button></form></div>
<div class='section card'><h2>분류 대기열</h2><div class='toolbar'><a class='button secondary' href='/demo'>샘플 넣기</a><a class='button secondary' href='/export.csv'>CSV 내보내기</a><a class='button secondary' href='/backup'>DB 백업</a><a class='button red' href='/reset' onclick=\"return confirm('모든 데이터를 초기화할까요?')\">초기화</a></div>
<div class='table-wrap'><table><thead><tr><th>접수 내용</th><th>분류·담당</th><th>긴급도</th><th>처리 모드·위험</th><th>상태</th><th>결정</th></tr></thead><tbody>{table_body}</tbody></table></div></div>
<div class='section card'><h2>반복 수정 규칙 후보</h2><div class='notice'>같은 수정이 2회 반복돼도 자동 적용되지 않습니다. 승인자가 확인한 뒤에만 MD와 다음 분류에 반영됩니다.</div><div class='table-wrap'><table><thead><tr><th>규칙</th><th>반복</th><th>위험</th><th>사람 결정</th></tr></thead><tbody>{pending_body}</tbody></table></div></div>
<div class='section card'><h2>현재 적용 중인 승인 규칙</h2><div class='table-wrap'><table><thead><tr><th>키워드</th><th>분류</th><th>담당</th><th>긴급도</th><th>처리 모드</th><th>버전</th></tr></thead><tbody>{active_body}</tbody></table></div></div>
"""
    )


base.classify_intake = learned_classify_intake
base.add_intake = add_intake
base.render_home = render_home


class LearningHandler(base.AppHandler):
    server_version = "IntakeClassifierLearning/1.2"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/correct/"):
            try:
                intake_id = int(parsed.path.rsplit("/", 1)[-1])
                query = urllib.parse.parse_qs(parsed.query)
                notice = query.get("notice", [""])[0]
                body = render_correction_page(intake_id, self.db_path, notice).encode("utf-8")
                self.send_bytes(body, "text/html; charset=utf-8")
            except (ValueError, OSError) as exc:
                self.redirect("/?error=1&notice=" + urllib.parse.quote(str(exc)))
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(payload, keep_blank_values=True)
        flat = {key: values[0] for key, values in form.items()}
        try:
            if parsed.path.startswith("/correct/"):
                intake_id = int(parsed.path.rsplit("/", 1)[-1])
                result = correct_intake(intake_id, flat, self.db_path)
                candidate = result["candidate"]
                message = f"분류를 수정했습니다. 규칙 후보 상태: {candidate['status']} · 반복 {candidate['occurrences']}회"
                self.redirect("/?notice=" + urllib.parse.quote(message))
                return
            if parsed.path.startswith("/learning/approve/"):
                candidate_id = int(parsed.path.rsplit("/", 1)[-1])
                actor = str(flat.get("actor", "")).strip()
                feedback_engine().approve_candidate(candidate_id, approved_by=actor)
                self.redirect("/?notice=" + urllib.parse.quote("규칙을 승인하고 다음 분류에 적용했습니다."))
                return
            if parsed.path.startswith("/learning/reject/"):
                candidate_id = int(parsed.path.rsplit("/", 1)[-1])
                actor = str(flat.get("actor", "")).strip()
                feedback_engine().reject_candidate(candidate_id, rejected_by=actor, note="PART 05 화면에서 거절")
                self.redirect("/?notice=" + urllib.parse.quote("규칙 후보를 거절했습니다."))
                return
        except (ValueError, OSError, KeyError, FeedbackEngineError, RuleConflictError) as exc:
            self.redirect("/?error=1&notice=" + urllib.parse.quote(str(exc)))
            return

        # BaseHTTPRequestHandler는 요청 본문을 다시 읽을 수 없으므로 기존 POST 경로를 직접 처리한다.
        try:
            if parsed.path == "/intakes":
                base.add_intake(flat, self.db_path)
                self.redirect("/?notice=" + urllib.parse.quote("업무를 접수하고 분류했습니다."))
                return
            if parsed.path == "/import":
                result = base.import_csv_text(flat.get("csv_text", ""), self.db_path)
                message = f"CSV 가져오기: 추가 {result['inserted']}건, 중복 {result['duplicates']}건, 오류 {result['errors']}건"
                self.redirect("/?notice=" + urllib.parse.quote(message))
                return
            for prefix, status in (("/approve/", "approved"), ("/reject/", "rejected"), ("/done/", "done")):
                if parsed.path.startswith(prefix):
                    intake_id = int(parsed.path.rsplit("/", 1)[-1])
                    base.change_status(intake_id, status, self.db_path)
                    self.redirect("/?notice=" + urllib.parse.quote(f"상태를 {status}로 변경했습니다."))
                    return
        except (ValueError, OSError) as exc:
            self.redirect("/?error=1&notice=" + urllib.parse.quote(str(exc)))
            return
        self.send_error(404)


def create_server(
    host: str = base.DEFAULT_HOST,
    port: int = base.DEFAULT_PORT,
    db_path: Path | str = base.DB_PATH,
    backup_dir: Path | str = base.BACKUP_DIR,
) -> ThreadingHTTPServer:
    base.init_db(db_path)
    feedback_engine()
    server = ThreadingHTTPServer((host, port), LearningHandler)
    server.db_path = str(db_path)  # type: ignore[attr-defined]
    server.backup_dir = str(backup_dir)  # type: ignore[attr-defined]
    return server


def open_browser_later(url: str) -> None:
    def _open() -> None:
        time.sleep(0.7)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=base.APP_TITLE)
    parser.add_argument("--host", default=base.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", base.DEFAULT_PORT)))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--restore", metavar="DB_FILE")
    args = parser.parse_args(argv)

    if args.preflight:
        result = base.preflight(base.DB_PATH, args.host, args.port)
        result["feedback_db"] = str(FEEDBACK_DB)
        result["memory_root"] = str(MEMORY_ROOT)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ready"] else 1
    if args.demo:
        print(f"샘플 {base.insert_demo(base.DB_PATH)}건 추가")
        return 0
    if args.backup:
        print(base.create_backup(base.DB_PATH, base.BACKUP_DIR))
        return 0
    if args.restore:
        print(base.restore_backup(args.restore, base.DB_PATH))
        return 0

    server = create_server(args.host, args.port, base.DB_PATH, base.BACKUP_DIR)
    url = f"http://{args.host}:{server.server_address[1]}"
    print(f"{base.APP_TITLE} v{APP_VERSION}")
    print(f"브라우저 주소: {url}")
    print("종료: 이 창에서 Ctrl+C")
    if not args.no_browser and os.environ.get("AUTO_OPEN_BROWSER", "1") != "0":
        open_browser_later(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n앱을 종료합니다.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
