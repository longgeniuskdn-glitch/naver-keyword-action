import tempfile,threading,unittest,urllib.request
from pathlib import Path
import app

class Part04Tests(unittest.TestCase):
    def paths(self):
        root=Path(tempfile.mkdtemp());return root,root/'test.db',root/'out',root/'back'
    def test_01_score_and_modes(self):
        score,value,mode=app.diagnose({'frequency':5,'time':5,'regularity':5,'review':5,'risk':1,'effort':1,'minutes':600,'hourly':30000,'flags':[]})
        self.assertGreaterEqual(score,70);self.assertEqual(value,300000);self.assertEqual(mode,'approval_required')
        self.assertEqual(app.diagnose({'frequency':5,'time':5,'regularity':5,'review':5,'risk':5,'effort':1,'flags':['contract']})[2],'human_only')
    def test_02_duplicate_block(self):
        _,db,_,_=self.paths();d={'name':'문의 분류','frequency':3,'time':3,'regularity':3,'review':3,'risk':2,'effort':2,'flags':[]};app.add(d,db)
        with self.assertRaises(ValueError):app.add(d,db)
    def test_03_approve_and_brief(self):
        _,db,out,_=self.paths();app.add({'name':'콘텐츠 재가공','category':'콘텐츠','frequency':5,'time':4,'regularity':5,'review':5,'risk':2,'effort':2,'input':'원고','output':'SNS 초안','flags':[]},db)
        p=app.approve(app.tasks(db)[0]['id'],db,out);self.assertTrue(p.exists());self.assertIn('첫 10건',p.read_text(encoding='utf-8'))
    def test_04_human_only_rejected(self):
        _,db,out,_=self.paths();app.add({'name':'계약 확정','frequency':3,'time':3,'regularity':3,'review':1,'risk':5,'effort':3,'flags':['contract']},db)
        with self.assertRaises(ValueError):app.approve(app.tasks(db)[0]['id'],db,out)
    def test_05_backup_restore(self):
        _,db,_,back=self.paths();app.add({'name':'CSV 검사','frequency':4,'time':3,'regularity':5,'review':5,'risk':2,'effort':2,'flags':[]},db)
        b=app.backup(db,back);app.reset(db);self.assertEqual(len(app.tasks(db)),0);app.restore(b,db);self.assertEqual(len(app.tasks(db)),1)
    def test_06_preflight(self):
        _,db,_,_=self.paths();self.assertTrue(app.preflight(db,0)['ready'])
    def test_07_http_health(self):
        root,db,out,back=self.paths();old=(app.DB,app.OUT,app.BACK);app.DB,app.OUT,app.BACK=db,out,back
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.H);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:self.assertIn(b'"ok": true',urllib.request.urlopen(f'http://127.0.0.1:{server.server_address[1]}/health',timeout=3).read())
        finally:server.shutdown();server.server_close();app.DB,app.OUT,app.BACK=old

if __name__=='__main__':unittest.main(verbosity=2)
