#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,html,io,json,os,re,shutil,socket,sqlite3,sys,threading,time,urllib.parse,webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DATA=Path(os.getenv('AI_DIAGNOSIS_DATA',ROOT/'data')); OUT=Path(os.getenv('AI_DIAGNOSIS_OUTPUT',ROOT/'output')); BACK=Path(os.getenv('AI_DIAGNOSIS_BACKUP',ROOT/'backups')); DB=DATA/'diagnosis.db'
HOST='127.0.0.1'; PORT=8794
FLAGS={'payment':'결제·송금','contract':'계약 확정','refund':'환불·보상','deletion':'삭제·덮어쓰기','legal':'법률 판단','medical':'의료 판단','personal_data':'개인정보','public_post':'외부 공개·발송','price_change':'가격 변경','account_permission':'계정 권한 변경'}
HUMAN={'payment','contract','refund','deletion','legal','medical'}; PREP={'personal_data','public_post','price_change','account_permission'}
SCHEMA='''CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,name TEXT UNIQUE,category TEXT,priority REAL,value INTEGER,mode TEXT,input TEXT,output TEXT,flags TEXT,status TEXT DEFAULT 'candidate',created TEXT);CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY,action TEXT,detail TEXT,created TEXT);'''
def now(): return datetime.now().astimezone().isoformat(timespec='seconds')
def conn(db=DB):
 db=Path(db);db.parent.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(db);c.row_factory=sqlite3.Row;c.executescript(SCHEMA);return c
def n(v,d=0):
 try:return int(str(v).replace(',',''))
 except:return d
def diagnose(d):
 f,t,r,q, risk,e=[max(1,min(5,n(d.get(k),1))) for k in ('frequency','time','regularity','review','risk','effort')]
 mins=max(0,n(d.get('minutes'))); hourly=max(0,n(d.get('hourly'))); err=max(0,n(d.get('error_cost'))); cost=max(0,n(d.get('tool_cost')))
 flags=set(d.get('flags') or []); mode='human_only' if risk>=5 or flags&HUMAN else 'prepare_only' if risk>=4 or flags&PREP else 'approval_required'
 value=max(0,round(mins/60*hourly+err-cost)); score=max(0,min(100,f*6+t*6+r*5+q*5+min(30,value/50000)-risk*8-e*4))
 if mode=='human_only':score=min(score,20)
 if mode=='prepare_only':score=min(score,55)
 return round(score,1),value,mode
MODE={'approval_required':'AI 초안 + 사람 승인','prepare_only':'AI 준비만 가능','human_only':'사람 직접 처리'}
def add(d,db=DB):
 name=d.get('name','').strip()
 if not name:raise ValueError('업무명을 입력하세요.')
 score,value,mode=diagnose(d)
 with conn(db) as c:
  try:c.execute('INSERT INTO tasks(name,category,priority,value,mode,input,output,flags,created) VALUES(?,?,?,?,?,?,?,?,?)',(name,d.get('category','기타'),score,value,mode,d.get('input',''),d.get('output',''),json.dumps(d.get('flags',[]),ensure_ascii=False),now()));c.execute('INSERT INTO logs(action,detail,created) VALUES(?,?,?)',('task_created',name,now()))
  except sqlite3.IntegrityError:raise ValueError('같은 이름의 업무가 이미 있습니다.')
def tasks(db=DB):
 with conn(db) as c:return c.execute('SELECT * FROM tasks ORDER BY priority DESC,value DESC').fetchall()
def brief(row):
 return f'''# TASK_BRIEF\n\n## 업무명\n{row['name']}\n\n## 목적\n반복 시간을 줄이되 대표가 최종 책임을 유지한다.\n\n## 입력\n{row['input'] or '확인 필요'}\n\n## 출력\n{row['output'] or '확인 필요'}\n\n## 진단\n- 우선순위: {row['priority']} / 100\n- 월간 가치 가정: {row['value']:,}원\n- 운영 모드: {MODE[row['mode']]}\n\n## 공통 규칙\n1. 원본을 덮어쓰지 않는다.\n2. 모르는 내용은 추측하지 않고 확인 필요로 표시한다.\n3. 외부 발송·게시·삭제·결제 전 사람 승인을 받는다.\n4. 처음 10건은 모두 사람이 검수한다.\n5. 성공·실패·수정 시간과 복구 위치를 기록한다.\n'''
def approve(i,db=DB,out=OUT):
 with conn(db) as c:
  row=c.execute('SELECT * FROM tasks WHERE id=?',(i,)).fetchone()
  if not row:raise ValueError('업무를 찾을 수 없습니다.')
  if row['mode']=='human_only':raise ValueError('사람 직접 처리 업무는 승인할 수 없습니다.')
  out=Path(out);out.mkdir(parents=True,exist_ok=True);p=out/(re.sub(r'[^0-9A-Za-z가-힣_-]+','_',row['name'])+'_TASK_BRIEF.md');p.write_text(brief(row),encoding='utf-8');c.execute("UPDATE tasks SET status='candidate'");c.execute("UPDATE tasks SET status='approved' WHERE id=?",(i,));c.execute('INSERT INTO logs(action,detail,created) VALUES(?,?,?)',('approved',str(p),now()));return p
def backup(db=DB,back=BACK):
 with conn(db) as c:c.execute('PRAGMA wal_checkpoint(FULL)')
 back=Path(back);back.mkdir(parents=True,exist_ok=True);p=back/f"diagnosis_{datetime.now():%Y%m%d_%H%M%S_%f}.db";shutil.copy2(db,p);return p
def restore(src,db=DB):Path(db).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,db);conn(db).close();return Path(db)
def reset(db=DB):
 for s in ('','-wal','-shm'):
  p=Path(str(db)+s)
  if p.exists():p.unlink()
 conn(db).close()
def preflight(db=DB,port=PORT):
 ok=True;err=''
 try:conn(db).close();s=socket.socket();s.bind((HOST,port));s.close()
 except Exception as e:ok=False;err=str(e)
 return {'python':sys.version.split()[0],'database':str(db),'port':port,'ready':ok,'error':err}
CSS='body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Noto Sans KR,sans-serif;background:#f4f7f9;color:#20313e;margin:0}header{background:#143d5a;color:#fff;padding:24px}.wrap{max-width:1180px;margin:auto;padding:20px}.card{background:#fff;border:1px solid #d8e1e8;border-radius:12px;padding:18px;margin:16px 0}h1,h2{margin-top:0}form.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}label{font-weight:700;font-size:13px}input,select,textarea{width:100%;padding:9px;border:1px solid #ccd7df;border-radius:7px;box-sizing:border-box}.full{grid-column:1/-1}.checks{display:flex;flex-wrap:wrap;gap:8px}.checks label{font-weight:400;border:1px solid #ccd7df;border-radius:999px;padding:6px 9px}button,a.btn{background:#0b67c1;color:#fff;border:0;border-radius:7px;padding:9px 13px;text-decoration:none;font-weight:700}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #d8e1e8;text-align:left}th{background:#143d5a;color:white}.notice{background:#edf5ff;border-left:5px solid #0b67c1;padding:12px}@media(max-width:800px){form.grid{grid-template-columns:1fr}.full{grid-column:auto}}'
def esc(v):return html.escape(str(v or ''),quote=True)
def home(db=DB,msg=''):
 rows=''.join(f"<tr><td><b>{esc(x['name'])}</b><br><small>{esc(x['category'])}</small></td><td>{x['priority']}/100</td><td>{x['value']:,}원</td><td>{MODE[x['mode']]}</td><td>{esc(x['input'])}<br>→ {esc(x['output'])}</td><td>{'승인됨' if x['status']=='approved' else ('' if x['mode']=='human_only' else f'<form method=post action=/approve/{x["id"]}><button>첫 프로젝트 승인</button></form>')}</td></tr>" for x in tasks(db)) or '<tr><td colspan=6>업무를 입력하세요.</td></tr>'
 opts=''.join(f'<option value={i}>{i}</option>' for i in range(1,6)); checks=''.join(f'<label><input type=checkbox name=flags value={k}>{v}</label>' for k,v in FLAGS.items())
 return f'''<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><style>{CSS}</style><header><div class=wrap><h1>AI 자동화 진단실</h1>반복 업무를 비교해 첫 자동화 프로젝트를 고릅니다.</div></header><main class=wrap>{f'<div class=notice>{esc(msg)}</div>' if msg else ''}<div class=card><h2>반복 업무 입력</h2><form class=grid method=post action=/tasks><label>업무명<input name=name required></label><label>분류<select name=category><option>고객응대</option><option>콘텐츠</option><option>데이터</option><option>예약·일정</option><option>견적·영업</option><option>보고</option><option>기타</option></select></label><label>월 반복 시간(분)<input type=number name=minutes value=300></label><label>빈도<select name=frequency>{opts}</select></label><label>걸리는 시간<select name=time>{opts}</select></label><label>규칙성<select name=regularity>{opts}</select></label><label>검수 용이성<select name=review>{opts}</select></label><label>실패 위험<select name=risk>{opts}</select></label><label>구현 난이도<select name=effort>{opts}</select></label><label>시간 가치(원/시간)<input type=number name=hourly value=30000></label><label>오류 비용(원/월)<input type=number name=error_cost value=0></label><label>도구 비용(원/월)<input type=number name=tool_cost value=0></label><label>입력<textarea name=input></textarea></label><label>출력<textarea name=output></textarea></label><div class=full><b>위험 행동</b><div class=checks>{checks}</div></div><div class=full><button>진단하고 저장</button></div></form></div><div class=card><h2>진단 결과</h2><p><a class=btn href=/demo>샘플 업무</a> <a class=btn href=/export.csv>CSV</a> <a class=btn href=/backup>백업</a> <a class=btn href=/reset>초기화</a></p><div style="overflow:auto"><table><tr><th>업무</th><th>점수</th><th>월간 가치</th><th>운영 모드</th><th>입력→출력</th><th>결정</th></tr>{rows}</table></div></div></main>'''
DEMO=[{'name':'고객 문의 분류','category':'고객응대','frequency':5,'time':4,'regularity':5,'review':5,'risk':2,'effort':2,'minutes':900,'hourly':30000,'error_cost':50000,'tool_cost':0,'input':'문의 CSV와 정책','output':'분류표와 답변 초안','flags':['public_post']},{'name':'블로그 원본 SNS 재가공','category':'콘텐츠','frequency':4,'time':4,'regularity':4,'review':5,'risk':2,'effort':2,'minutes':600,'hourly':35000,'input':'검수된 원고','output':'Threads와 캐러셀','flags':[]},{'name':'계약서 최종 확정','category':'계약','frequency':2,'time':3,'regularity':2,'review':1,'risk':5,'effort':4,'minutes':180,'hourly':50000,'error_cost':1000000,'input':'계약서','output':'계약 확정','flags':['contract','legal']}]
class H(BaseHTTPRequestHandler):
 def sendb(self,b,typ='text/html; charset=utf-8',name=None):
  self.send_response(200);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(b)));
  if name:self.send_header('Content-Disposition',f"attachment; filename*=UTF-8''{urllib.parse.quote(name)}")
  self.end_headers();self.wfile.write(b)
 def redir(self,msg):self.send_response(303);self.send_header('Location','/?msg='+urllib.parse.quote(msg));self.end_headers()
 def do_GET(self):
  u=urllib.parse.urlparse(self.path);q=urllib.parse.parse_qs(u.query)
  if u.path=='/health':return self.sendb(json.dumps({'ok':True}).encode(),'application/json')
  if u.path=='/demo':
   c=0
   for d in DEMO:
    try:add(d);c+=1
    except:pass
   return self.redir(f'샘플 {c}건 추가')
  if u.path=='/backup':
   p=backup();return self.sendb(p.read_bytes(),'application/octet-stream',p.name)
  if u.path=='/reset':reset();return self.redir('초기화 완료')
  if u.path=='/export.csv':
   s=io.StringIO();w=csv.writer(s);w.writerow(['업무','분류','점수','월간 가치','운영 모드','상태']);[w.writerow([x['name'],x['category'],x['priority'],x['value'],MODE[x['mode']],x['status']]) for x in tasks()];return self.sendb(('\ufeff'+s.getvalue()).encode(),'text/csv; charset=utf-8','diagnosis.csv')
  return self.sendb(home(DB,q.get('msg',[''])[0]).encode()) if u.path=='/' else self.send_error(404)
 def do_POST(self):
  f=urllib.parse.parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode(),keep_blank_values=True)
  if self.path=='/tasks':
   d={k:v[0] for k,v in f.items() if k!='flags'};d['flags']=f.get('flags',[])
   try:add(d);self.redir('진단 저장 완료')
   except ValueError as e:self.redir(str(e))
  elif self.path.startswith('/approve/'):
   try:p=approve(int(self.path.rsplit('/',1)[1]));self.redir(f'{p.name} 생성 완료')
   except ValueError as e:self.redir(str(e))
  else:self.send_error(404)
def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=PORT);p.add_argument('--no-browser',action='store_true');p.add_argument('--preflight',action='store_true');p.add_argument('--backup',action='store_true');p.add_argument('--restore');a=p.parse_args()
 if a.preflight:print(json.dumps(preflight(DB,a.port),ensure_ascii=False,indent=2));return 0 if preflight(DB,a.port)['ready'] else 1
 if a.backup:print(backup());return 0
 if a.restore:print(restore(a.restore));return 0
 s=ThreadingHTTPServer((HOST,a.port),H);url=f'http://{HOST}:{a.port}';print('AI 자동화 진단실',url)
 if not a.no_browser:threading.Thread(target=lambda:(time.sleep(.7),webbrowser.open(url)),daemon=True).start()
 try:s.serve_forever()
 except KeyboardInterrupt:pass
 finally:s.server_close()
if __name__=='__main__':raise SystemExit(main())
