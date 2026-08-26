#!/usr/bin/env python3
"""PART 06 - 회사 자료를 기억하는 AI 지식 창고.

외부 패키지 없이 실행되는 로컬 웹앱입니다. 지정한 텍스트 자료를 색인하고,
검색 결과마다 출처와 최신성 정보를 표시합니다. 자료에 없는 답을 만들어 내지
않으며, 외부 공유·원본 수정·삭제는 수행하지 않습니다.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shlex
import shutil
import socket
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable

APP_TITLE = "회사 자료를 기억하는 AI 지식 창고"
APP_VERSION = "1.0.0"
MODULE_ID = "part06_knowledge"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8796
SUPPORTED_SUFFIXES = {".txt", ".md", ".csv", ".json"}


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = app_root()
DATA_DIR = Path(os.environ.get("KNOWLEDGE_DATA_DIR", ROOT / "data"))
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_SOURCE_DIR", ROOT / "knowledge"))
OUTPUT_DIR = Path(os.environ.get("KNOWLEDGE_OUTPUT_DIR", ROOT / "output"))
BACKUP_DIR = Path(os.environ.get("KNOWLEDGE_BACKUP_DIR", ROOT / "backups"))
DB_PATH = Path(os.environ.get("KNOWLEDGE_DB", DATA_DIR / "knowledge.db"))
EVENT_LOG = Path(os.environ.get("AI_COMPANY_EVENT_LOG", DATA_DIR / "events.jsonl"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    review_due TEXT NOT NULL DEFAULT '',
    indexed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chunk_no INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_text TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id)
);
"""

CSS = """
:root{--navy:#173b58;--blue:#1669ad;--line:#d7e1e8;--green:#21765b;--red:#b23a45;--amber:#9b6500;--text:#24323d;--muted:#65737e}
*{box-sizing:border-box}body{margin:0;background:#f5f7f9;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",Arial,sans-serif;line-height:1.55}header{background:var(--navy);color:white;padding:22px 0}.wrap{width:min(1180px,94vw);margin:0 auto}.brand{display:flex;align-items:center;justify-content:space-between;gap:16px}.brand h1{margin:0;font-size:28px}.badge{background:#e9f3ff;color:#084a84;padding:6px 11px;border-radius:999px;font-weight:800;font-size:13px}main{padding:24px 0 60px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:13px}.card{background:white;border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 5px 18px rgba(25,55,78,.05)}.metric strong{display:block;font-size:28px;color:var(--navy)}.metric span{color:var(--muted)}h2{margin:0 0 14px;color:var(--navy);font-size:22px}.section{margin-top:20px}.form-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.wide{grid-column:span 2}.full{grid-column:1/-1}label{font-size:13px;font-weight:750;color:#405462;display:block;margin-bottom:5px}input,textarea{width:100%;border:1px solid #ccd8e0;border-radius:8px;padding:10px 11px;background:#fff;font:inherit}textarea{min-height:130px;resize:vertical}button,.button{display:inline-block;border:0;border-radius:8px;padding:9px 13px;background:var(--blue);color:#fff;font-weight:750;text-decoration:none;cursor:pointer}.button.secondary{background:#657987}.button.green,button.green{background:var(--green)}.button.red{background:var(--red)}.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.notice{padding:12px 14px;border-left:5px solid var(--blue);background:#edf5ff;margin-bottom:15px}.notice.error{border-color:var(--red);background:#fff0f1}.result{border-top:1px solid var(--line);padding:15px 0}.result:first-child{border-top:0}.score{font-weight:800;color:var(--blue)}.source{font-size:13px;color:var(--muted)}.stale{color:var(--red);font-weight:800}.fresh{color:var(--green);font-weight:800}.muted{color:var(--muted);font-size:13px}code{background:#edf2f5;padding:2px 5px;border-radius:4px}@media(max-width:850px){.grid{grid-template-columns:repeat(2,1fr)}.form-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
"""


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def tokens(value: str) -> list[str]:
    return [x.lower() for x in re.findall(r"[0-9A-Za-z가-힣]{2,}", value)]


def source_key(source: str) -> str:
    return hashlib.sha256(normalize(source).lower().encode("utf-8")).hexdigest()


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def split_chunks(content: str, max_chars: int = 700) -> list[str]:
    paragraphs = [normalize(p) for p in re.split(r"\n\s*\n", content) if normalize(p)]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [normalize(content)]:
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks


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


def write_event(action: str, status: str, message: str, task_id: str = "") -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event_id": f"EVT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "module_id": MODULE_ID,
        "task_id": task_id,
        "action": action,
        "status": status,
        "message": message,
        "created_at": now_text(),
    }
    with EVENT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def log_action(conn: sqlite3.Connection, document_id: int | None, action: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO audit_logs(document_id,action,detail,created_at) VALUES(?,?,?,?)",
        (document_id, action, detail, now_text()),
    )


def ingest_text(title: str, source: str, content: str, review_due: str = "", db_path: Path | str = DB_PATH) -> dict:
    title = normalize(title)
    source = normalize(source)
    content = content.strip()
    if not title:
        raise ValueError("자료 제목을 입력하세요.")
    if not source:
        raise ValueError("출처 또는 파일 경로를 입력하세요.")
    if not content:
        raise ValueError("자료 내용을 입력하세요.")
    if review_due:
        date.fromisoformat(review_due)
    init_db(db_path)
    skey = source_key(source)
    chash = content_hash(content)
    timestamp = now_text()
    with connect(db_path) as conn:
        existing = conn.execute("SELECT * FROM documents WHERE source_key=?", (skey,)).fetchone()
        if existing and existing["content_hash"] == chash and existing["title"] == title and existing["review_due"] == review_due:
            log_action(conn, existing["id"], "document_unchanged", source)
            return {"id": existing["id"], "version": existing["version"], "changed": False}
        if existing:
            document_id = int(existing["id"])
            version = int(existing["version"]) + 1
            conn.execute(
                "UPDATE documents SET title=?,source=?,content=?,content_hash=?,version=?,review_due=?,indexed_at=?,updated_at=? WHERE id=?",
                (title, source, content, chash, version, review_due, timestamp, timestamp, document_id),
            )
            conn.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
            action = "document_updated"
        else:
            cursor = conn.execute(
                "INSERT INTO documents(source_key,title,source,content,content_hash,version,review_due,indexed_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (skey, title, source, content, chash, 1, review_due, timestamp, timestamp),
            )
            document_id = int(cursor.lastrowid)
            version = 1
            action = "document_created"
        for index, chunk in enumerate(split_chunks(content), 1):
            conn.execute(
                "INSERT INTO chunks(document_id,chunk_no,content,token_text) VALUES(?,?,?,?)",
                (document_id, index, chunk, " ".join(tokens(chunk))),
            )
        log_action(conn, document_id, action, f"source={source}; version={version}")
    write_event("knowledge.index", "completed", f"{title} v{version} 색인 완료")
    return {"id": document_id, "version": version, "changed": True}


def list_documents(db_path: Path | str = DB_PATH) -> list[sqlite3.Row]:
    init_db(db_path)
    with connect(db_path) as conn:
        return list(conn.execute("SELECT * FROM documents ORDER BY updated_at DESC, id DESC").fetchall())


def is_stale(review_due: str) -> bool:
    if not review_due:
        return False
    try:
        return date.fromisoformat(review_due) < date.today()
    except ValueError:
        return True


def search_documents(query: str, db_path: Path | str = DB_PATH, limit: int = 8) -> list[dict]:
    query_tokens = sorted(set(tokens(query)))
    if not query_tokens:
        return []
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT c.id AS chunk_id,c.chunk_no,c.content,c.token_text,
                      d.id AS document_id,d.title,d.source,d.version,d.review_due,d.updated_at
               FROM chunks c JOIN documents d ON d.id=c.document_id"""
        ).fetchall()
    results: list[dict] = []
    for row in rows:
        haystack = f"{row['title']} {row['token_text']}".lower()
        matched = [token for token in query_tokens if token in haystack]
        if not matched:
            continue
        occurrence = sum(haystack.count(token) for token in matched)
        score = len(matched) * 10 + occurrence
        results.append({
            "score": score,
            "matched_tokens": matched,
            "document_id": row["document_id"],
            "chunk_id": row["chunk_id"],
            "chunk_no": row["chunk_no"],
            "title": row["title"],
            "source": row["source"],
            "version": row["version"],
            "review_due": row["review_due"],
            "stale": is_stale(row["review_due"]),
            "updated_at": row["updated_at"],
            "content": row["content"],
        })
    results.sort(key=lambda item: (-item["score"], item["stale"], item["title"], item["chunk_no"]))
    return results[:limit]


def build_evidence_markdown(query: str, results: Iterable[dict]) -> str:
    items = list(results)
    lines = [f"# 근거 묶음: {query}", "", "> 자료에 없는 내용은 추측하지 말고 ‘확인 필요’로 표시합니다.", ""]
    if not items:
        lines.extend(["검색 결과가 없습니다.", "", "## 다음 행동", "- 검색어를 바꿉니다.", "- 최신 회사 자료를 knowledge 폴더에 추가합니다."])
        return "\n".join(lines) + "\n"
    for index, item in enumerate(items, 1):
        freshness = "검토 기한 지남" if item["stale"] else "현재 색인 기준"
        lines.extend([
            f"## 근거 {index}. {item['title']}",
            f"- 출처: {item['source']}",
            f"- 버전: {item['version']}",
            f"- 최신성: {freshness}",
            f"- 청크: {item['chunk_no']}",
            "",
            item["content"],
            "",
        ])
    return "\n".join(lines)


def export_evidence(query: str, db_path: Path | str = DB_PATH, output_dir: Path | str = OUTPUT_DIR) -> Path:
    results = search_documents(query, db_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", query).strip("_") or "search"
    path = output / f"{safe}_EVIDENCE.md"
    path.write_text(build_evidence_markdown(query, results), encoding="utf-8")
    write_event("knowledge.export", "completed", f"{path.name} 생성")
    return path


def scan_knowledge_folder(folder: Path | str = KNOWLEDGE_DIR, db_path: Path | str = DB_PATH) -> dict:
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    added = updated = unchanged = errors = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8-sig")
            before = next((row for row in list_documents(db_path) if row["source"] == str(path)), None)
            result = ingest_text(path.stem, str(path), content, "", db_path)
            if not result["changed"]:
                unchanged += 1
            elif before:
                updated += 1
            else:
                added += 1
        except Exception:
            errors += 1
    return {"added": added, "updated": updated, "unchanged": unchanged, "errors": errors}


def insert_demo(db_path: Path | str = DB_PATH, folder: Path | str = KNOWLEDGE_DIR) -> int:
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    samples = {
        "환불정책.md": "# 환불 정책\n\n단순 변심 환불은 상품 수령 후 7일 이내에 접수한다. 사용 흔적이 있거나 디지털 파일을 내려받은 경우에는 담당자가 별도 검토한다. 환불 확정과 금액 결정은 사람이 승인한다.",
        "배송정책.md": "# 배송 정책\n\n평일 오후 2시 이전 결제 완료 주문은 당일 출고를 목표로 한다. 도서산간 지역은 추가 배송 기간이 발생할 수 있다. 운송장 번호는 출고 후 고객에게 안내한다.",
        "회사문체.md": "# 회사 문체\n\n고객에게는 존댓말을 사용한다. 확인되지 않은 내용은 단정하지 않는다. 불편을 먼저 인정하고 확인 방법과 예상 회신 시점을 안내한다.",
    }
    for name, content in samples.items():
        (root / name).write_text(content, encoding="utf-8")
    result = scan_knowledge_folder(root, db_path)
    return result["added"] + result["updated"]


def create_backup(db_path: Path | str = DB_PATH, backup_dir: Path | str = BACKUP_DIR) -> Path:
    init_db(db_path)
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"knowledge_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
    source_conn = connect(db_path)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    write_event("backup.create", "completed", str(target))
    return target


def restore_backup(backup_path: Path | str, db_path: Path | str = DB_PATH) -> Path:
    backup = Path(backup_path)
    destination = Path(db_path)
    if not backup.exists():
        raise FileNotFoundError(f"백업 파일을 찾을 수 없습니다: {backup}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    safety = destination.with_name(f"{destination.stem}_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    if destination.exists():
        shutil.copy2(destination, safety)
    src = sqlite3.connect(backup)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    init_db(destination)
    write_event("backup.restore", "completed", str(backup))
    return destination


def reset_data(db_path: Path | str = DB_PATH) -> None:
    path = Path(db_path)
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()
    init_db(path)


def module_info() -> dict:
    return {
        "module_id": MODULE_ID,
        "name": APP_TITLE,
        "version": APP_VERSION,
        "category": "knowledge",
        "standalone": True,
        "default_port": DEFAULT_PORT,
        "capabilities": ["knowledge.index", "knowledge.search", "knowledge.export", "backup.create", "backup.restore"],
    }


def preflight(db_path: Path | str = DB_PATH, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    result: dict[str, object] = {
        "app": APP_TITLE,
        "version": APP_VERSION,
        "python": sys.version.split()[0],
        "python_ok": sys.version_info >= (3, 10),
        "database_ok": False,
        "data_writable": False,
        "knowledge_dir": str(KNOWLEDGE_DIR),
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


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def layout(content: str) -> str:
    return f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{APP_TITLE}</title><style>{CSS}</style></head><body><header><div class='wrap brand'><div><h1>{APP_TITLE}</h1><div>회사 자료를 출처와 함께 찾고, 없는 답은 만들지 않습니다.</div></div><span class='badge'>MODULE · v{APP_VERSION}</span></div></header><main><div class='wrap'>{content}</div></main></body></html>"""


def render_home(query: str = "", notice: str = "", error: bool = False, db_path: Path | str = DB_PATH) -> str:
    docs = list_documents(db_path)
    results = search_documents(query, db_path) if query else []
    stale_count = sum(1 for row in docs if is_stale(row["review_due"]))
    notice_html = f"<div class='notice{' error' if error else ''}'>{esc(notice)}</div>" if notice else ""
    result_html = ""
    if query:
        if not results:
            result_html = "<div class='notice error'>근거를 찾지 못했습니다. 검색어를 바꾸거나 자료를 추가하세요.</div>"
        else:
            parts = []
            for item in results:
                fresh_class = "stale" if item["stale"] else "fresh"
                fresh_text = "검토 기한 지남" if item["stale"] else "현재 색인 기준"
                parts.append(f"<div class='result'><div><span class='score'>{item['score']}점</span> · <strong>{esc(item['title'])}</strong> · <span class='{fresh_class}'>{fresh_text}</span></div><div class='source'>{esc(item['source'])} · v{item['version']} · 청크 {item['chunk_no']}</div><p>{esc(item['content'])}</p></div>")
            result_html = "".join(parts)
    doc_items = "".join(
        f"<div class='result'><strong>{esc(row['title'])}</strong> <span class='muted'>v{row['version']}</span><div class='source'>{esc(row['source'])}</div><div class='{'stale' if is_stale(row['review_due']) else 'fresh'}'>{'검토 기한 지남' if is_stale(row['review_due']) else '현재 색인 기준'}</div></div>"
        for row in docs[:10]
    ) or "<div class='muted'>아직 색인된 자료가 없습니다.</div>"
    return layout(f"""
{notice_html}
<div class='grid'><div class='card metric'><strong>{len(docs)}</strong><span>색인 자료</span></div><div class='card metric'><strong>{sum(len(split_chunks(row['content'])) for row in docs)}</strong><span>검색 청크</span></div><div class='card metric'><strong>{stale_count}</strong><span>검토 기한 경과</span></div><div class='card metric'><strong>{len(results)}</strong><span>현재 검색 결과</span></div></div>
<div class='section card'><h2>회사 자료 검색</h2><form method='get' action='/'><div class='form-grid'><div class='wide'><label>질문 또는 검색어</label><input name='q' value='{esc(query)}' placeholder='예: 단순 변심 환불 기간'></div><div><label>&nbsp;</label><button type='submit'>근거 찾기</button></div></div></form><div class='toolbar'><a class='button secondary' href='/scan'>knowledge 폴더 다시 색인</a><a class='button secondary' href='/demo'>샘플 자료 넣기</a>{f"<a class='button green' href='/export?q={urllib.parse.quote(query)}'>근거 MD 내보내기</a>" if query else ''}<a class='button secondary' href='/backup'>DB 백업</a></div>{result_html}</div>
<div class='section card'><h2>자료 직접 추가</h2><form method='post' action='/documents'><div class='form-grid'><div><label>제목</label><input name='title' required></div><div><label>출처·파일 경로</label><input name='source' required></div><div><label>검토 기한</label><input type='date' name='review_due'></div><div class='full'><label>내용</label><textarea name='content' required></textarea></div><div class='full'><button type='submit'>색인하고 저장</button></div></div></form></div>
<div class='section card'><h2>최근 자료</h2>{doc_items}</div>
""")


class AppHandler(BaseHTTPRequestHandler):
    server_version = "KnowledgeWarehouse/1.0"

    @property
    def db_path(self) -> Path:
        return Path(getattr(self.server, "db_path", DB_PATH))

    def log_message(self, fmt: str, *args: object) -> None:
        if os.environ.get("KNOWLEDGE_QUIET") != "1":
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
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/health":
            self.send_bytes(json.dumps({"ok": True, **module_info()}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/module-info":
            self.send_bytes(json.dumps(module_info(), ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/api/search":
            q = query.get("q", [""])[0]
            self.send_bytes(json.dumps(search_documents(q, self.db_path), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/events":
            body = EVENT_LOG.read_bytes() if EVENT_LOG.exists() else b""
            self.send_bytes(body, "application/x-ndjson; charset=utf-8")
            return
        if parsed.path == "/scan":
            result = scan_knowledge_folder(KNOWLEDGE_DIR, self.db_path)
            self.redirect("/?notice=" + urllib.parse.quote(f"폴더 색인: 추가 {result['added']}, 갱신 {result['updated']}, 동일 {result['unchanged']}, 오류 {result['errors']}"))
            return
        if parsed.path == "/demo":
            count = insert_demo(self.db_path, KNOWLEDGE_DIR)
            self.redirect("/?notice=" + urllib.parse.quote(f"샘플 자료 {count}건을 반영했습니다."))
            return
        if parsed.path == "/backup":
            path = create_backup(self.db_path, BACKUP_DIR)
            self.send_bytes(path.read_bytes(), "application/octet-stream", filename=path.name)
            return
        if parsed.path == "/export":
            q = query.get("q", [""])[0]
            if not q:
                self.redirect("/?error=1&notice=" + urllib.parse.quote("검색어가 필요합니다."))
                return
            path = export_evidence(q, self.db_path, OUTPUT_DIR)
            self.send_bytes(path.read_bytes(), "text/markdown; charset=utf-8", filename=path.name)
            return
        if parsed.path == "/":
            q = query.get("q", [""])[0]
            notice = query.get("notice", [""])[0]
            error = query.get("error", ["0"])[0] == "1"
            self.send_bytes(render_home(q, notice, error, self.db_path).encode("utf-8"), "text/html; charset=utf-8")
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(body, keep_blank_values=True)
        if self.path == "/documents":
            data = {key: values[0] for key, values in form.items()}
            try:
                result = ingest_text(data.get("title", ""), data.get("source", ""), data.get("content", ""), data.get("review_due", ""), self.db_path)
                message = f"자료를 색인했습니다. 버전 {result['version']}" if result["changed"] else "같은 내용이라 새 버전을 만들지 않았습니다."
                self.redirect("/?notice=" + urllib.parse.quote(message))
            except (ValueError, OSError) as exc:
                self.redirect("/?error=1&notice=" + urllib.parse.quote(str(exc)))
            return
        self.send_error(404)


def create_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, db_path: Path | str = DB_PATH) -> ThreadingHTTPServer:
    init_db(db_path)
    server = ThreadingHTTPServer((host, port), AppHandler)
    server.db_path = str(db_path)  # type: ignore[attr-defined]
    return server


def open_browser_later(url: str) -> None:
    def _open() -> None:
        time.sleep(0.8)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--restore", metavar="DB_FILE")
    args = parser.parse_args(argv)
    if args.preflight:
        result = preflight(DB_PATH, args.host, args.port)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ready"] else 1
    if args.demo:
        print(f"샘플 자료 {insert_demo(DB_PATH, KNOWLEDGE_DIR)}건 반영")
        return 0
    if args.scan:
        print(json.dumps(scan_knowledge_folder(KNOWLEDGE_DIR, DB_PATH), ensure_ascii=False))
        return 0
    if args.backup:
        print(create_backup(DB_PATH, BACKUP_DIR))
        return 0
    if args.restore:
        print(restore_backup(args.restore, DB_PATH))
        return 0
    server = create_server(args.host, args.port, DB_PATH)
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
