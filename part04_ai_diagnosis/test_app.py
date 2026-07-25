from pathlib import Path
import tempfile,threading,urllib.request
import app

def temp_paths():
 d=Path(tempfile.mkdtemp());return d,d/'test.db',d/'out',d/'back'

def test_score_and_modes():
 score,value,mode=app.diagnose({'frequency':5,'time':5,'regularity':5,'review':5,'risk':1,'effort':1,'minutes':600,'hourly':30000,'flags':[]})
 assert score>=70 and value==300000 and mode=='approval_required'
 assert app.diagnose({'frequency':5,'time':5,'regularity':5,'review':5,'risk':5,'effort':1,'flags':['contract']})[2]=='human_only'

def test_duplicate_block():
 _,db,_,_=temp_paths();d={'name':'문의 분류','frequency':3,'time':3,'regularity':3,'review':3,'risk':2,'effort':2,'flags':[]}
 app.add(d,db)
 try:app.add(d,db);assert False
 except ValueError:pass

def test_approve_and_brief():
 _,db,out,_=temp_paths();app.add({'name':'콘텐츠 재가공','category':'콘텐츠','frequency':5,'time':4,'regularity':5,'review':5,'risk':2,'effort':2,'input':'원고','output':'SNS 초안','flags':[]},db)
 row=app.tasks(db)[0];p=app.approve(row['id'],db,out)
 assert p.exists() and '첫 10건' in p.read_text(encoding='utf-8')

def test_human_only_rejected():
 _,db,out,_=temp_paths();app.add({'name':'계약 확정','frequency':3,'time':3,'regularity':3,'review':1,'risk':5,'effort':3,'flags':['contract']},db)
 try:app.approve(app.tasks(db)[0]['id'],db,out);assert False
 except ValueError:pass

def test_backup_restore():
 root,db,_,back=temp_paths();app.add({'name':'CSV 검사','frequency':4,'time':3,'regularity':5,'review':5,'risk':2,'effort':2,'flags':[]},db)
 b=app.backup(db,back);app.reset(db);assert len(app.tasks(db))==0
 app.restore(b,db);assert len(app.tasks(db))==1

def test_preflight():
 _,db,_,_=temp_paths();r=app.preflight(db,0);assert r['ready'] is True

def test_http_health():
 root,db,out,back=temp_paths();server=app.ThreadingHTTPServer(('127.0.0.1',0),app.H)
 old=(app.DB,app.OUT,app.BACK);app.DB,app.OUT,app.BACK=db,out,back
 t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
 try:
  data=urllib.request.urlopen(f'http://127.0.0.1:{server.server_address[1]}/health',timeout=3).read()
  assert b'"ok": true' in data
 finally:
  server.shutdown();server.server_close();app.DB,app.OUT,app.BACK=old
