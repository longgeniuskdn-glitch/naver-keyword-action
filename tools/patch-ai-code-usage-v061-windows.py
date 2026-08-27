from pathlib import Path
import json, re

root = Path('/tmp/src/src/desktop')
main = root / 'main.js'
html = root / 'index.html'
pkgp = root / 'package.json'

s = main.read_text(encoding='utf-8')
s = s.replace("const VERSION='0.6.0';", "const VERSION='0.6.1';", 1)

probe = r'''function shellClaudeProbe(){
  const fallback={claudePath:null};
  try{
    if(process.platform==='darwin'){
      let claudePath=null;
      try{claudePath=String(execFileSync('/bin/zsh',['-lic','command -v claude || true'],{encoding:'utf8',timeout:3000,stdio:['ignore','pipe','pipe']})).trim()||null}catch{}
      return {claudePath};
    }
    if(process.platform==='win32'){
      const candidates=[];
      try{
        const raw=String(execFileSync('where.exe',['claude.exe'],{encoding:'utf8',timeout:3000,stdio:['ignore','pipe','pipe']}));
        candidates.push(...raw.split(/\r?\n/).map(x=>x.trim()).filter(Boolean));
      }catch{}
      try{
        const raw=String(execFileSync('where.exe',['claude.cmd'],{encoding:'utf8',timeout:3000,stdio:['ignore','pipe','pipe']}));
        candidates.push(...raw.split(/\r?\n/).map(x=>x.trim()).filter(Boolean));
      }catch{}
      if(process.env.APPDATA)candidates.push(path.join(process.env.APPDATA,'npm','claude.cmd'));
      candidates.push(path.join(os.homedir(),'.local','bin','claude.exe'));
      candidates.push(path.join(os.homedir(),'.claude','local','claude.exe'));
      return {claudePath:candidates.find(p=>{try{return fs.existsSync(p)}catch{return false}})||null};
    }
  }catch{}
  return fallback;
}'''
s,n = re.subn(r"function shellClaudeProbe\(\)\{.*?\n\}", lambda _m: probe, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit(f'shellClaudeProbe replacement failed: {n}')

cred = r'''function readClaudeCredentialBlob(){
  const errors=[];
  if(process.platform==='darwin'){
    try{
      const out=String(execFileSync('/usr/bin/security',['find-generic-password','-s','Claude Code-credentials','-w'],{encoding:'utf8',timeout:20000,stdio:['ignore','pipe','pipe']}));
      if(out.trim())return {raw:out,source:'macOS Keychain'};
    }catch(e){errors.push('Keychain: '+String(e.stderr||e.message||e).trim().slice(0,180))}
  }
  const candidates=[];
  if(process.env.CLAUDE_SECURESTORAGE_CONFIG_DIR)candidates.push(path.join(process.env.CLAUDE_SECURESTORAGE_CONFIG_DIR,'.credentials.json'));
  if(process.env.CLAUDE_CONFIG_DIR)candidates.push(path.join(process.env.CLAUDE_CONFIG_DIR,'.credentials.json'));
  candidates.push(path.join(os.homedir(),'.claude','.credentials.json'));
  for(const file of candidates){
    try{
      const raw=fs.readFileSync(file,'utf8');
      if(raw.trim())return {raw,source:file};
    }catch{}
  }
  const where=process.platform==='win32'?'%USERPROFILE%\\.claude\\.credentials.json':'Claude Code credential store';
  throw new Error(errors[0]||`Claude Code 로그인 정보를 찾지 못했습니다. ${where}을 확인하거나 터미널에서 claude를 실행해 로그인하세요.`);
}'''
s,n = re.subn(r"function readClaudeCredentialBlob\(\)\{.*?\n\}", lambda _m: cred, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit(f'readClaudeCredentialBlob replacement failed: {n}')

# Windows does not need a Claude CLI path to query usage; auth status is optional metadata.
# Keep direct OAuth usage collection identical to the Mac v0.6.0 engine.
main.write_text(s, encoding='utf-8')

h = html.read_text(encoding='utf-8')
h = h.replace('Claude Code의 기존 로그인 OAuth를 macOS Keychain에서 읽어 사용량 서버를 직접 조회합니다. 별도 Claude 로그인이나 토큰 입력은 필요 없습니다.',
              'Claude Code의 기존 로그인 OAuth를 로컬 자격증명에서 읽어 사용량 서버를 직접 조회합니다. Windows에서는 %USERPROFILE%\\.claude\\.credentials.json을 자동으로 사용합니다.')
h = h.replace('AI Code Usage v0.6.0','AI Code Usage v0.6.1')
html.write_text(h, encoding='utf-8')

pkg = json.loads(pkgp.read_text(encoding='utf-8'))
pkg['version'] = '0.6.1'
pkg.setdefault('scripts', {})['dist:win'] = 'electron-builder --win nsis portable --x64'
build = pkg.setdefault('build', {})
build['productName'] = build.get('productName') or 'AI Code Usage'
build['appId'] = build.get('appId') or 'com.myvision.aicodeusage'
build['win'] = {
    'target': [
        {'target': 'nsis', 'arch': ['x64']},
        {'target': 'portable', 'arch': ['x64']}
    ]
}
build.setdefault('nsis', {})
build['nsis'].update({
    'oneClick': False,
    'allowToChangeInstallationDirectory': True,
    'createDesktopShortcut': True,
    'createStartMenuShortcut': True,
    'shortcutName': 'AI Code Usage'
})
pkgp.write_text(json.dumps(pkg, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

# Add a small Windows-specific regression test ensuring the credential parser remains compatible.
tdir = root / 'test'; tdir.mkdir(exist_ok=True)
(tdir / 'windows-credential.test.js').write_text(r'''const test=require('node:test');
const assert=require('node:assert/strict');
const {parseClaudeAccessToken}=require('../usage-core');

test('parses Windows Claude Code .credentials.json OAuth blob',()=>{
 const raw=JSON.stringify({claudeAiOauth:{accessToken:'windows-oauth-token',subscriptionType:'pro',rateLimitTier:'default_claude_pro',expiresAt:9999999999999}});
 const x=parseClaudeAccessToken(raw);
 assert.equal(x.accessToken,'windows-oauth-token');
 assert.equal(x.subscriptionType,'pro');
 assert.equal(x.rateLimitTier,'default_claude_pro');
});
''', encoding='utf-8')

print('v0.6.1 Windows patch applied')
