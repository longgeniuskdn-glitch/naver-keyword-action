from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from launcher_core import LauncherManager  # 통합 ZIP 안에서 사용
except ImportError:
    from ai_launcher_v02.launcher import LauncherManager  # 저장소 개발·테스트에서 사용

from common_feedback import FeedbackEngine, FeedbackEngineError, RuleConflictError

DEFAULT_MODULES_DIR = ROOT / "modules"
DEFAULT_RUNTIME_DIR = ROOT / "runtime"
DEFAULT_LOGS_DIR = ROOT / "logs"
DEFAULT_MEMORY_DIR = ROOT / "memory"


DASHBOARD_HTML = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>우리 회사 AI 운영실 v0.3</title>
<style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif;color:#172033;background:#f3f6fa}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1240px;margin:auto;padding:28px 18px 60px}h1,h2,h3{margin-top:0}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:20px}.sub{color:#667085;line-height:1.6}.actions,.row{display:flex;gap:8px;flex-wrap:wrap}
button,a.btn{border:0;border-radius:10px;padding:10px 14px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}.primary{background:#155eef;color:white}.dark{background:#25324b;color:white}.light{background:white;color:#344054;border:1px solid #d0d5dd}.danger{background:#b42318;color:white}
.tabs{display:flex;gap:8px;margin:18px 0}.tab{background:white;border:1px solid #d0d5dd}.tab.active{background:#172033;color:white}.panel{display:none}.panel.active{display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}.card{background:white;border:1px solid #e4e7ec;border-radius:16px;padding:18px;box-shadow:0 4px 16px rgba(16,24,40,.05)}
.top{display:flex;justify-content:space-between;gap:12px}.name{font-size:19px;font-weight:800}.version,.meta,.muted{color:#667085;font-size:13px}.desc{color:#475467;min-height:44px;line-height:1.55}.status{font-weight:800}.healthy{color:#067647}.stopped{color:#667085}
.formgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.full{grid-column:1/-1}label{display:block;font-size:13px;font-weight:800;margin-bottom:6px}input,select,textarea{width:100%;border:1px solid #d0d5dd;border-radius:10px;padding:10px;font:inherit}textarea{min-height:88px;resize:vertical}
.notice{padding:12px 14px;border-radius:12px;background:#fff6ed;color:#9a3412;margin-bottom:14px;line-height:1.55}.msg{margin:14px 0;padding:12px;border-radius:10px;background:#eef4ff;display:none;white-space:pre-wrap}
table{width:100%;border-collapse:collapse;background:white;border-radius:14px;overflow:hidden}th,td{text-align:left;padding:11px;border-bottom:1px solid #eaecf0;vertical-align:top;font-size:14px}th{background:#f9fafb}.badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#eef4ff;font-size:12px;font-weight:800}.pending{background:#fff6ed}.approved{background:#ecfdf3}.conflict{background:#fef3f2}.collecting{background:#f2f4f7}
@media(max-width:720px){header{align-items:flex-start;flex-direction:column}.formgrid{grid-template-columns:1fr}.full{grid-column:auto}table{display:block;overflow:auto}}
</style></head><body><div class="wrap">
<header><div><h1>우리 회사 AI 운영실 <span class="badge">v0.3</span></h1><div class="sub">PART 실행과 함께 수정 이유를 모으고, 반복 규칙을 사람 승인 후 MD에 반영합니다.</div></div><div class="actions"><button class="primary" onclick="post('/api/start-all')">전체 실행</button><button class="dark" onclick="post('/api/stop-all')">전체 종료</button><button class="light" onclick="refreshAll()">새로고침</button></div></header>
<div class="tabs"><button class="tab active" data-panel="modules">모듈 실행</button><button class="tab" data-panel="training">AI 교육·규칙 승인</button><button class="tab" data-panel="registry">MD 기억 레지스트리</button></div>
<div id="msg" class="msg"></div>
<section id="modules" class="panel active"><div id="moduleGrid" class="grid"></div></section>
<section id="training" class="panel">
<div class="notice">규칙 후보는 자동으로 적용되지 않습니다. 계약·법률·결제·환불·개인정보·대외 답변은 사례가 쌓여도 사람 승인을 유지합니다.</div>
<div class="card"><h2>수정 피드백 기록</h2><form id="feedbackForm" class="formgrid">
<div><label>모듈</label><select name="module_id" id="moduleSelect"></select></div><div><label>업무·게시물 ID</label><input name="item_ref" required placeholder="예: inquiry-102"></div>
<div class="full"><label>AI 원본</label><textarea name="original_text" placeholder="수정 전 결과"></textarea></div><div class="full"><label>사람 수정본</label><textarea name="revised_text" required placeholder="승인할 수정 결과"></textarea></div>
<div><label>수정 이유 코드</label><select name="reason_code"><option value="tone">말투</option><option value="accuracy">정확성</option><option value="structure">구조</option><option value="routing">분류·배정</option><option value="legal">법률</option><option value="payment">결제</option><option value="privacy">개인정보</option><option value="general">기타</option></select></div>
<div><label>규칙 키</label><input name="rule_key" required placeholder="예: polite-opening"></div><div class="full"><label>수정 이유·승격할 규칙 문장</label><textarea name="reason_detail" required placeholder="예: 고객 답변은 첫 문장을 사과보다 사실 확인으로 시작한다"></textarea></div>
<div><label>검토자</label><input name="reviewer" required value="Kris"></div><div><label>검토 시간(초)</label><input name="review_seconds" type="number" min="0" value="0"></div>
<div class="full"><button class="primary" type="submit">피드백 저장</button></div></form></div>
<div class="card" style="margin-top:14px"><h2>규칙 후보</h2><div class="muted">같은 수정 이유가 반복되면 collecting → pending으로 바뀝니다. 승인 전에는 실제 MD 규칙에 반영되지 않습니다.</div><div style="overflow:auto;margin-top:12px"><table><thead><tr><th>ID</th><th>모듈</th><th>규칙</th><th>반복</th><th>상태</th><th>결정</th></tr></thead><tbody id="candidateBody"></tbody></table></div></div>
</section>
<section id="registry" class="panel"><div class="card"><h2>MD 기억 레지스트리</h2><div class="muted">회사 공통 규칙과 모듈별 규칙의 버전·승인자·변경 시각을 확인합니다.</div><div style="overflow:auto;margin-top:12px"><table><thead><tr><th>경로</th><th>범위</th><th>모듈</th><th>버전</th><th>승인자</th><th>갱신</th></tr></thead><tbody id="registryBody"></tbody></table></div></div></section>
</div><script>
const msg=document.getElementById('msg');const esc=v=>String(v??'').replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
function show(v){msg.style.display='block';msg.textContent=typeof v==='string'?v:JSON.stringify(v,null,2)}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab,.panel').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.panel).classList.add('active')});
async function get(path){const r=await fetch(path);const d=await r.json();if(!r.ok)throw new Error(d.error||r.statusText);return d}
async function post(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw new Error(d.error||r.statusText);show(d);await refreshAll();return d}
async function refreshModules(){const d=await get('/api/modules');const grid=document.getElementById('moduleGrid');const select=document.getElementById('moduleSelect');const defaults=['part02-threads','part03-blog','part04-ai-diagnosis','part05-work-intake','part06-knowledge-vault'];const options=[...new Set([...defaults,...d.modules.map(m=>m.id)])];select.innerHTML=options.map(id=>`<option value="${esc(id)}">${esc(id)}</option>`).join('');grid.innerHTML=d.modules.length?d.modules.map(m=>`<article class="card"><div class="top"><div><div class="name">${esc(m.name)}</div><div class="version">${esc(m.version)} · 포트 ${m.port}</div></div><div class="status ${m.healthy?'healthy':'stopped'}">${m.healthy?'정상':m.running?'시작 중':'중지'}</div></div><p class="desc">${esc(m.description)}</p><div class="meta">ID: ${esc(m.id)} · PID: ${esc(m.pid||'-')}<br>로그: ${esc(m.log)}</div><div class="row"><button class="primary" onclick="post('/api/start/${encodeURIComponent(m.id)}')">실행</button><button class="dark" onclick="post('/api/stop/${encodeURIComponent(m.id)}')">종료</button><a class="btn light" href="${esc(m.url)}" target="_blank">화면 열기</a></div></article>`).join(''):'<div class="card">등록된 모듈이 없습니다. 피드백 엔진은 단독으로 사용할 수 있습니다.</div>'}
async function refreshCandidates(){const d=await get('/api/rules/candidates');document.getElementById('candidateBody').innerHTML=d.candidates.length?d.candidates.map(c=>`<tr><td>${c.id}</td><td>${esc(c.module_id)}</td><td><b>${esc(c.rule_key)}</b><br>${esc(c.rule_text)}</td><td>${c.occurrences}</td><td><span class="badge ${esc(c.status)}">${esc(c.status)}</span><br><span class="muted">${esc(c.risk_level)}</span></td><td><div class="row">${['pending','collecting','conflict'].includes(c.status)?`<button class="primary" onclick="decide(${c.id},'approve')">승인</button><button class="light" onclick="decide(${c.id},'reject')">거절</button>`:''}${c.status==='conflict'?`<button class="danger" onclick="decide(${c.id},'approve',true)">충돌 덮어쓰기</button>`:''}${c.status==='approved'?`<button class="danger" onclick="decide(${c.id},'rollback')">롤백</button>`:''}</div></td></tr>`).join(''):'<tr><td colspan="6">후보가 없습니다.</td></tr>'}
async function refreshRegistry(){const d=await get('/api/memory/registry');document.getElementById('registryBody').innerHTML=d.files.map(f=>`<tr><td>${esc(f.path)}</td><td>${esc(f.scope)}</td><td>${esc(f.module_id||'-')}</td><td>${f.version}</td><td>${esc(f.approved_by||'-')}</td><td>${esc(f.updated_at)}</td></tr>`).join('')}
async function decide(id,action,override=false){const actor=prompt('승인·결정자 이름','Kris');if(!actor)return;const note=prompt('결정 메모','')||'';try{await post(`/api/rules/${id}/${action}`,{actor,note,override_conflict:override})}catch(e){show(e.message)}}
document.getElementById('feedbackForm').onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target).entries());data.review_seconds=Number(data.review_seconds||0);try{await post('/api/feedback',data);e.target.item_ref.value='';e.target.original_text.value='';e.target.revised_text.value='';e.target.reason_detail.value=''}catch(err){show(err.message)}};
async function refreshAll(){try{await Promise.all([refreshModules(),refreshCandidates(),refreshRegistry()])}catch(e){show(e.message)}}refreshAll();setInterval(refreshModules,3000);
</script></body></html>'''


def find_free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("사용 가능한 런처 포트를 찾지 못했습니다.")


def make_handler(manager: LauncherManager, engine: FeedbackEngine) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "AIOperationsLauncher/0.3"

        def _json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            if length > 2_000_000:
                raise ValueError("요청 본문이 너무 큽니다.")
            raw = self.rfile.read(length).decode("utf-8")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("JSON 객체만 허용합니다.")
            return value

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/":
                body = DASHBOARD_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/health":
                self._json({"status": "ok", "version": "0.3", "modules": len(manager.specs), "feedback_engine": "ok"})
                return
            if parsed.path == "/api/modules":
                self._json({"modules": manager.list_status()})
                return
            if parsed.path == "/api/feedback":
                self._json({"feedback": engine.list_feedback(query.get("module_id", [None])[0])})
                return
            if parsed.path == "/api/rules/candidates":
                status = query.get("status", [])
                self._json({"candidates": engine.list_candidates(query.get("module_id", [None])[0], status)})
                return
            if parsed.path == "/api/memory/registry":
                self._json({"files": engine.list_registry()})
                return
            if parsed.path == "/api/audit":
                self._json({"events": engine.list_audit()})
                return
            self._json({"error": "not_found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/start-all":
                    self._json({"results": manager.start_all()})
                    return
                if parsed.path == "/api/stop-all":
                    self._json({"results": manager.stop_all()})
                    return
                if parsed.path.startswith("/api/start/"):
                    self._json(manager.start(parsed.path.removeprefix("/api/start/")))
                    return
                if parsed.path.startswith("/api/stop/"):
                    self._json(manager.stop(parsed.path.removeprefix("/api/stop/")))
                    return
                if parsed.path == "/api/feedback":
                    self._json(engine.submit_feedback(self._body()), 201)
                    return
                if parsed.path == "/api/rules/manual":
                    body = self._body()
                    self._json(engine.create_manual_candidate(**body), 201)
                    return
                parts = parsed.path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["api", "rules"]:
                    candidate_id = int(parts[2])
                    action = parts[3]
                    body = self._body()
                    actor = str(body.get("actor", ""))
                    note = str(body.get("note", ""))
                    if action == "approve":
                        self._json(engine.approve_candidate(candidate_id, approved_by=actor, note=note, override_conflict=bool(body.get("override_conflict"))))
                        return
                    if action == "reject":
                        self._json(engine.reject_candidate(candidate_id, rejected_by=actor, note=note))
                        return
                    if action == "rollback":
                        self._json(engine.rollback_candidate(candidate_id, rolled_back_by=actor, note=note))
                        return
                self._json({"error": "not_found"}, 404)
            except RuleConflictError as exc:
                self._json({"error": str(exc), "code": "rule_conflict"}, 409)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, 400)
            except KeyError as exc:
                self._json({"error": str(exc)}, 404)
            except FeedbackEngineError as exc:
                self._json({"error": str(exc)}, 409)
            except Exception as exc:
                self._json({"error": str(exc)}, 500)

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler


def build_services(root: Path = ROOT) -> tuple[LauncherManager, FeedbackEngine]:
    manager = LauncherManager(
        modules_dir=root / "modules",
        runtime_dir=root / "runtime",
        logs_dir=root / "logs",
    )
    engine = FeedbackEngine(
        db_path=root / "runtime" / "feedback.db",
        memory_root=root / "memory",
        candidate_threshold=2,
    )
    engine.ensure_memory_layout(manager.specs.keys())
    return manager, engine


def run_server(port: int, open_browser: bool = True) -> None:
    manager, engine = build_services()
    actual_port = find_free_port(port)
    server = ThreadingHTTPServer(("127.0.0.1", actual_port), make_handler(manager, engine))
    url = f"http://127.0.0.1:{actual_port}"
    print(f"우리 회사 AI 운영실 v0.3: {url}")
    print("공통 피드백·MD 승인 엔진: 사용 가능")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n런처를 종료합니다.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="우리 회사 AI 운영실 v0.3")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        manager, engine = build_services()
        print(json.dumps({"modules": manager.list_status(), "memory": engine.list_registry()}, ensure_ascii=False, indent=2))
        return
    run_server(args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
