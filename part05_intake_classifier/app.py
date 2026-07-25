#!/usr/bin/env python3
"""PART 05 - 업무 접수·분류실.

외부 패키지 없이 실행되는 로컬 웹앱입니다. 이메일, 문의폼, 메모, CSV에서
들어온 업무를 한곳에 접수하고 유형·긴급도·담당·승인 필요 여부로 분류합니다.
실제 메일 발송이나 외부 답변은 수행하지 않습니다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import shutil
import socket
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable

APP_TITLE = "업무 접수·분류실"
APP_VERSION = "1.0.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8795


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = app_root()
DATA_DIR = Path(os.environ.get("INTAKE_DATA_DIR", ROOT / "data"))
OUTPUT_DIR = Path(os.environ.get("INTAKE_OUTPUT_DIR", ROOT / "output"))
BACKUP_DIR = Path(os.environ.get("INTAKE_BACKUP_DIR", ROOT / "backups"))
DB_PATH = Path(os.environ.get("INTAKE_DB", DATA_DIR / "intake.db"))

CATEGORY_RULES = [
    ("환불·취소", ("환불", "취소", "반품", "교환", "보상")),
    ("배송", ("배송", "택배", "출고", "도착", "운송장")),
    ("결제·증빙", ("결제", "카드", "입금", "영수증", "세금계산서", "현금영수증")),
    ("예약·일정", ("예약", "일정", "방문", "상담", "미팅", "시간 변경")),
    ("불만·분쟁", ("불만", "항의", "신고", "분쟁", "피해", "소비자원")),
    ("계약·법무", ("계약", "약관", "법률", "소송", "내용증명")),
    ("제휴·콘텐츠", ("제휴", "협업", "광고", "콘텐츠", "인터뷰", "원고")),
    ("제품·사용법", ("사용법", "설치", "오류", "작동", "기능", "문의")),
]
TEAM_MAP = {
    "환불·취소": "고객지원",
    "배송": "물류",
    "결제·증빙": "회계",
    "예약·일정": "운영",
    "불만·분쟁": "대표 검토",
    "계약·법무": "대표 검토",
    "제휴·콘텐츠": "마케팅",
    "제품·사용법": "고객지원",
    "기타": "운영",
}
HIGH_URGENCY_WORDS = ("긴급", "즉시", "지금", "장애", "결제 오류", "오늘까지", "마감 임박")
MEDIUM_URGENCY_WORDS = ("오늘", "내일", "빠르게", "급합니다", "이번 주")
FLAG_RULES = {
    "refund": ("환불", "보상", "반품", "교환"),
    "payment": ("결제", "카드", "입금", "계좌", "송금"),
    "contract": ("계약", "약관", "서명"),
    "legal": ("법률", "소송", "내용증명", "신고", "소비자원"),
    "personal_data": ("주민번호", "전화번호", "주소", "계좌번호", "개인정보"),
    "public_response": ("공개 답변", "게시판 답변", "SNS 답변"),
}
FLAG_LABELS = {
    "refund": "환불·보상",
    "payment": "결제·송금",
    "contract": "계약",
    "legal": "법률·분쟁",
    "personal_data": "개인정보",
    "public_response": "외부 공개 답변",
}
MODE_LABELS = {
    "standard": "분류 후 사람 승인",
    "prepare_only": "AI 준비만 가능",
    "human_only": "사람 직접 처리",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS intakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    sender TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    dedupe_hash TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    urgency TEXT NOT NULL,
    assigned_team TEXT NOT NULL,
    approval_required INTEGER NOT NULL,
    risk_flags TEXT NOT NULL DEFAULT '[]',
    handling_mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'triaged',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intake_id INTEGER,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(intake_id) REFERENCES intakes(id)
);
"""

CSS = """
:root{--navy:#173b58;--blue:#1669ad;--pale:#edf5fb;--line:#d7e1e8;--green:#21765b;--red:#b23a45;--amber:#9b6500;--text:#24323d;--muted:#65737e}
*{box-sizing:border-box}body{margin:0;background:#f5f7f9;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",Arial,sans-serif;line-height:1.55}header{background:var(--navy);color:#fff;padding:22px 0}.wrap{width:min(1220px,94vw);margin:0 auto}.brand{display:flex;justify-content:space-between;gap:16px;align-items:center}.brand h1{margin:0;font-size:28px}.badge{background:#e9f3ff;color:#084a84;padding:6px 11px;border-radius:999px;font-weight:800;font-size:13px}main{padding:24px 0 60px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:13px}.card{background:white;border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 5px 18px rgba(25,55,78,.05)}.metric strong{display:block;font-size:28px;color:var(--navy)}.metric span{color:var(--muted)}h2{margin:0 0 14px;color:var(--navy);font-size:22px}.section{margin-top:20px}.form-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.wide{grid-column:span 2}.full{grid-column:1/-1}label{font-size:13px;font-weight:750;color:#405462;display:block;margin-bottom:5px}input,select,textarea{width:100%;border:1px solid #ccd8e0;border-radius:8px;padding:10px 11px;background:#fff;font:inherit}textarea{min-height:100px;resize:vertical}button,.button{display:inline-block;border:0;border-radius:8px;padding:9px 13px;background:var(--blue);color:#fff;font-weight:750;text-decoration:none;cursor:pointer}.button.secondary{background:#657987}.button.green,button.green{background:var(--green)}.button.red,button.red{background:var(--red)}.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.notice{padding:12px 14px;border-left:5px solid var(--blue);background:#edf5ff;margin-bottom:15px}.notice.error{border-color:var(--red);background:#fff0f1}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;background:#fff;font-size:14px}th,td{border-bottom:1px solid var(--line);padding:10px 8px;text-align:left;vertical-align:top}th{background:var(--navy);color:#fff;position:sticky;top:0}.urgency-high{color:var(--red);font-weight:800}.urgency-medium{color:var(--amber);font-weight:800}.urgency-low{color:var(--green);font-weight:800}.mode-human_only{color:var(--red);font-weight:800}.mode-prepare_only{color:var(--amber);font-weight:800}.mode-standard{color:var(--green);font-weight:800}.muted{color:var(--muted);font-size:13px}.empty{text-align:center;padding:38px;color:var(--muted)}code{background:#edf2f5;padding:2px 5px;border-radius:4px}@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.form-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
"""


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def make_dedupe_hash(channel: str, sender: str, subject: str, body: str) -> str:
    raw = "|".join(normalize(v) for v in (channel, sender, subject, body))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def detect_risk_flags(text: str) -> list[str]:
    lowered = normalize(text)
    return sorted(key for key, words in FLAG_RULES.items() if any(word in lowered for word in words))


def classify_intake(subject: str, body: str) -> dict:
    text = normalize(f"{subject} {body}")
    category = "기타"
    for candidate, words in CATEGORY_RULES:
        if any(word in text for word in words):
            category = candidate
            break
    if any(word in text for word in HIGH_URGENCY_WORDS):
        urgency = "high"
    elif category in {"불만·분쟁", "계약·법무"} or any(word in text for word in MEDIUM_URGENCY_WORDS):
        urgency = "medium"
    else:
        urgency = "low"
    flags = detect_risk_flags(text)
    if set(flags).intersection({"contract", "legal"}):
        mode = "human_only"
    elif urgency == "high" or set(flags).intersection({"refund", "payment", "personal_data", "public_response"}):
        mode = "prepare_only"
    else:
        mode = "standard"
    return {
        "category": category,
        "urgency": urgency,
        "assigned_team": TEAM_MAP.get(category, "운영"),
        "approval_required": 1,
        "risk_flags": flags,
        "handling_mode": mode,
    }


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: Path | str = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def log_action(conn: sqlite3.Connection, intake_id: int | None, action: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO audit_logs(intake_id,action,detail,created_at) VALUES(?,?,?,?)",
        (intake_id, action, detail, now_text()),
    )


def add_intake(data: dict, db_path: Path | str = DB_PATH) -> int:
    channel = str(data.get("channel", "manual")).strip() or "manual"
    sender = str(data.get("sender", "")).strip()
    subject = str(data.get("subject", "")).strip()
    body = str(data.get("body", "")).strip()
    if not subject:
        raise ValueError("제목을 입력하세요.")
    if not body:
        raise ValueError("내용을 입력하세요.")
    diagnosis = classify_intake(subject, body)
    dedupe = make_dedupe_hash(channel, sender, subject, body)
    timestamp = now_text()
    init_db(db_path)
    try:
        with connect(db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO intakes(
                    channel,sender,subject,body,dedupe_hash,category,urgency,
                    assigned_team,approval_required,risk_flags,handling_mode,
                    status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    channel, sender, subject, body, dedupe, diagnosis["category"],
                    diagnosis["urgency"], diagnosis["assigned_team"],
                    diagnosis["approval_required"], json.dumps(diagnosis["risk_flags"], ensure_ascii=False),
                    diagnosis["handling_mode"], "triaged", timestamp, timestamp,
                ),
            )
            intake_id = int(cursor.lastrowid)
            log_action(conn, intake_id, "intake_created", f"category={diagnosis['category']}; urgency={diagnosis['urgency']}")
            return intake_id
    except sqlite3.IntegrityError as exc:
        raise ValueError("같은 내용이 이미 접수되었습니다. 중복 항목을 확인하세요.") from exc


def import_csv_text(text: str, db_path: Path | str = DB_PATH) -> dict:
    reader = csv.DictReader(io.StringIO(text.strip()))
    required = {"subject", "body"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError("CSV 첫 줄에 subject,body 열이 필요합니다. channel과 sender는 선택입니다.")
    inserted = duplicates = errors = 0
    for row in reader:
        try:
            add_intake({
                "channel": row.get("channel") or "csv",
                "sender": row.get("sender") or "",
                "subject": row.get("subject") or "",
                "body": row.get("body") or "",
            }, db_path)
            inserted += 1
        except ValueError as exc:
            if "이미 접수" in str(exc):
                duplicates += 1
            else:
                errors += 1
    return {"inserted": inserted, "duplicates": duplicates, "errors": errors}


def list_intakes(db_path: Path | str = DB_PATH) -> list[sqlite3.Row]:
    init_db(db_path)
    order = "CASE urgency WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"
    with connect(db_path) as conn:
        return list(conn.execute(f"SELECT * FROM intakes ORDER BY {order}, id DESC").fetchall())


def get_intake(intake_id: int, db_path: Path | str = DB_PATH) -> sqlite3.Row | None:
    init_db(db_path)
    with connect(db_path) as conn:
        return conn.execute("SELECT * FROM intakes WHERE id=?", (intake_id,)).fetchone()


def change_status(intake_id: int, status: str, db_path: Path | str = DB_PATH) -> None:
    allowed = {"approved", "rejected", "done"}
    if status not in allowed:
        raise ValueError("허용되지 않은 상태입니다.")
    row = get_intake(intake_id, db_path)
    if row is None:
        raise ValueError("접수 항목을 찾을 수 없습니다.")
    if status == "done" and row["status"] != "approved":
        raise ValueError("분류 승인 후에만 완료 처리할 수 있습니다.")
    with connect(db_path) as conn:
        conn.execute("UPDATE intakes SET status=?,updated_at=? WHERE id=?", (status, now_text(), intake_id))
        log_action(conn, intake_id, f"status_{status}", f"previous={row['status']}")


def summary(db_path: Path | str = DB_PATH) -> dict:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """SELECT COUNT(*) total,
               SUM(CASE WHEN urgency='high' THEN 1 ELSE 0 END) high_count,
               SUM(CASE WHEN handling_mode='human_only' THEN 1 ELSE 0 END) human_count,
               SUM(CASE WHEN status='triaged' THEN 1 ELSE 0 END) pending_count
               FROM intakes"""
        ).fetchone()
    return {key: row[key] or 0 for key in row.keys()}


def flag_text(raw: str) -> str:
    try:
        flags = json.loads(raw or "[]")
    except json.JSONDecodeError:
        flags = []
    return ", ".join(FLAG_LABELS.get(flag, flag) for flag in flags) or "없음"


def export_csv_bytes(db_path: Path | str = DB_PATH) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "channel", "sender", "subject", "category", "urgency", "assigned_team", "handling_mode", "risk_flags", "status", "created_at"])
    for row in list_intakes(db_path):
        writer.writerow([
            row["id"], row["channel"], row["sender"], row["subject"], row["category"],
            row["urgency"], row["assigned_team"], row["handling_mode"],
            flag_text(row["risk_flags"]), row["status"], row["created_at"],
        ])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def insert_demo(db_path: Path | str = DB_PATH) -> int:
    samples = [
        {"channel": "email", "sender": "buyer@example.com", "subject": "배송이 아직 도착하지 않았습니다", "body": "운송장 조회가 안 됩니다. 확인 부탁드립니다."},
        {"channel": "webform", "sender": "customer@example.com", "subject": "긴급 환불 요청", "body": "결제 오류가 발생했습니다. 오늘 안에 환불 절차를 알려 주세요."},
        {"channel": "memo", "sender": "partner", "subject": "콘텐츠 제휴 제안", "body": "다음 달 공동 인터뷰와 원고 협업을 제안합니다."},
        {"channel": "email", "sender": "legal@example.com", "subject": "계약 조항과 내용증명 검토", "body": "법률 판단이 필요한 계약 분쟁 내용입니다."},
    ]
    inserted = 0
    for item in samples:
        try:
            add_intake(item, db_path)
            inserted += 1
        except ValueError:
            pass
    return inserted


def create_backup(db_path: Path | str = DB_PATH, backup_dir: Path | str = BACKUP_DIR) -> Path:
    init_db(db_path)
    source = Path(db_path)
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"intake_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
    with connect(db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(FULL)")
    shutil.copy2(source, target)
    with connect(db_path) as conn:
        log_action(conn, None, "backup_created", str(target))
    return target


def restore_backup(backup_path: Path | str, db_path: Path | str = DB_PATH) -> Path:
    backup = Path(backup_path)
    destination = Path(db_path)
    if not backup.exists():
        raise FileNotFoundError(f"백업 파일을 찾을 수 없습니다: {backup}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        safety = destination.with_name(f"{destination.stem}_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        shutil.copy2(destination, safety)
    shutil.copy2(backup, destination)
    init_db(destination)
    with connect(destination) as conn:
        log_action(conn, None, "backup_restored", str(backup))
    return destination


def reset_data(db_path: Path | str = DB_PATH) -> None:
    path = Path(db_path)
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()
    init_db(path)


def preflight(db_path: Path | str = DB_PATH, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    result: dict[str, object] = {
        "app": APP_TITLE,
        "version": APP_VERSION,
        "python": sys.version.split()[0],
        "python_ok": sys.version_info >= (3, 10),
        "database": str(Path(db_path)),
        "database_ok": False,
        "data_writable": False,
        "port": port,
        "port_available": False,
    }
    try:
        init_db(db_path)
        with connect(db_path) as conn:
            conn.execute("SELECT 1").fetchone()
        result["database_ok"] = True
        probe = Path(db_path).parent / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        result["data_writable"] = True
    except Exception as exc:
        result["database_error"] = str(exc)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        result["port_available"] = True
    except OSError as exc:
        result["port_error"] = str(exc)
    finally:
        sock.close()
    result["ready"] = bool(result["python_ok"] and result["database_ok"] and result["data_writable"] and result["port_available"])
    return result


def escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def layout(content: str) -> str:
    return f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{APP_TITLE}</title><style>{CSS}</style></head><body>
<header><div class='wrap brand'><div><h1>{APP_TITLE}</h1><div>여러 채널에서 들어온 업무를 한곳에서 분류하고 사람이 승인합니다.</div></div><span class='badge'>LOCAL · v{APP_VERSION}</span></div></header>
<main><div class='wrap'>{content}</div></main><footer><div class='wrap muted'>외부 메일·메신저로 전송하지 않습니다. 계약·법률 판단은 사람 직접 처리로 표시합니다.</div></footer></body></html>"""


def render_home(db_path: Path | str = DB_PATH, notice: str = "", error: bool = False) -> str:
    rows = list_intakes(db_path)
    stats = summary(db_path)
    notice_html = f"<div class='notice{' error' if error else ''}'>{escape(notice)}</div>" if notice else ""
    table_rows = []
    for row in rows:
        actions = ""
        if row["status"] == "triaged":
            actions = f"<form method='post' action='/approve/{row['id']}' style='display:inline'><button class='green'>분류 승인</button></form> <form method='post' action='/reject/{row['id']}' style='display:inline'><button class='red'>보류</button></form>"
        elif row["status"] == "approved":
            actions = f"<form method='post' action='/done/{row['id']}' style='display:inline'><button>완료</button></form>"
        table_rows.append(f"""
<tr><td><strong>{escape(row['subject'])}</strong><div class='muted'>{escape(row['channel'])} · {escape(row['sender'])}</div><div>{escape(row['body'][:120])}</div></td>
<td>{escape(row['category'])}<div class='muted'>{escape(row['assigned_team'])}</div></td>
<td class='urgency-{row['urgency']}'>{row['urgency']}</td>
<td class='mode-{row['handling_mode']}'>{MODE_LABELS[row['handling_mode']]}<div class='muted'>{escape(flag_text(row['risk_flags']))}</div></td>
<td>{escape(row['status'])}</td><td>{actions}</td></tr>""")
    body = "".join(table_rows) if table_rows else "<tr><td colspan='6' class='empty'>접수된 업무가 없습니다. 샘플을 넣거나 첫 업무를 등록하세요.</td></tr>"
    return layout(f"""
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
<div class='section card'><h2>분류 대기열</h2><div class='toolbar'><a class='button secondary' href='/demo'>샘플 넣기</a><a class='button secondary' href='/export.csv'>CSV 내보내기</a><a class='button secondary' href='/backup'>DB 백업</a><a class='button red' href='/reset' onclick="return confirm('모든 데이터를 초기화할까요?')">초기화</a></div>
<div class='table-wrap'><table><thead><tr><th>접수 내용</th><th>분류·담당</th><th>긴급도</th><th>처리 모드·위험</th><th>상태</th><th>결정</th></tr></thead><tbody>{body}</tbody></table></div></div>
""")


class AppHandler(BaseHTTPRequestHandler):
    server_version = "IntakeClassifier/1.0"

    @property
    def db_path(self) -> Path:
        return Path(getattr(self.server, "db_path", DB_PATH))

    @property
    def backup_dir(self) -> Path:
        return Path(getattr(self.server, "backup_dir", BACKUP_DIR))

    def log_message(self, fmt: str, *args: object) -> None:
        if os.environ.get("INTAKE_QUIET") != "1":
            super().log_message(fmt, *args)

    def send_bytes(self, body: bytes, content_type: str, status: int = 200, filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}")
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, path: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", path)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path == "/health":
            self.send_bytes(json.dumps({"ok": True, "app": APP_TITLE, "version": APP_VERSION}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if path == "/export.csv":
            self.send_bytes(export_csv_bytes(self.db_path), "text/csv; charset=utf-8", filename="intake_queue.csv")
            return
        if path == "/backup":
            backup = create_backup(self.db_path, self.backup_dir)
            self.send_bytes(backup.read_bytes(), "application/octet-stream", filename=backup.name)
            return
        if path == "/demo":
            count = insert_demo(self.db_path)
            self.redirect("/?notice=" + urllib.parse.quote(f"샘플 {count}건을 추가했습니다."))
            return
        if path == "/reset":
            reset_data(self.db_path)
            self.redirect("/?notice=" + urllib.parse.quote("데이터를 초기화했습니다."))
            return
        if path == "/":
            notice = query.get("notice", [""])[0]
            error = query.get("error", ["0"])[0] == "1"
            self.send_bytes(render_home(self.db_path, notice, error).encode("utf-8"), "text/html; charset=utf-8")
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(payload, keep_blank_values=True)
        try:
            if self.path == "/intakes":
                add_intake({key: values[0] for key, values in form.items()}, self.db_path)
                self.redirect("/?notice=" + urllib.parse.quote("업무를 접수하고 분류했습니다."))
                return
            if self.path == "/import":
                result = import_csv_text(form.get("csv_text", [""])[0], self.db_path)
                message = f"CSV 가져오기: 추가 {result['inserted']}건, 중복 {result['duplicates']}건, 오류 {result['errors']}건"
                self.redirect("/?notice=" + urllib.parse.quote(message))
                return
            for prefix, status in (("/approve/", "approved"), ("/reject/", "rejected"), ("/done/", "done")):
                if self.path.startswith(prefix):
                    intake_id = int(self.path.rsplit("/", 1)[-1])
                    change_status(intake_id, status, self.db_path)
                    self.redirect("/?notice=" + urllib.parse.quote(f"상태를 {status}로 변경했습니다."))
                    return
        except (ValueError, OSError) as exc:
            self.redirect("/?error=1&notice=" + urllib.parse.quote(str(exc)))
            return
        self.send_error(404)


def create_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, db_path: Path | str = DB_PATH, backup_dir: Path | str = BACKUP_DIR) -> ThreadingHTTPServer:
    init_db(db_path)
    server = ThreadingHTTPServer((host, port), AppHandler)
    server.db_path = str(db_path)  # type: ignore[attr-defined]
    server.backup_dir = str(backup_dir)  # type: ignore[attr-defined]
    return server


def open_browser_later(url: str) -> None:
    def _open() -> None:
        time.sleep(0.7)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--restore", metavar="DB_FILE")
    args = parser.parse_args(argv)

    if args.preflight:
        result = preflight(DB_PATH, args.host, args.port)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ready"] else 1
    if args.demo:
        print(f"샘플 {insert_demo(DB_PATH)}건 추가")
        return 0
    if args.backup:
        print(create_backup(DB_PATH, BACKUP_DIR))
        return 0
    if args.restore:
        print(restore_backup(args.restore, DB_PATH))
        return 0

    server = create_server(args.host, args.port, DB_PATH, BACKUP_DIR)
    url = f"http://{args.host}:{server.server_address[1]}"
    print(f"{APP_TITLE} v{APP_VERSION}")
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
