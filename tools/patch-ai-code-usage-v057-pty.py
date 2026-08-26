from pathlib import Path
import json, re

root = Path('/tmp/src/src/desktop')
main = root / 'main.js'
core = root / 'usage-core.js'
pkgp = root / 'package.json'

s = main.read_text()
s = s.replace("const VERSION='0.5.6';", "const VERSION='0.5.7';", 1)
s = s.replace(
    "const {normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache} = require('./usage-core');",
    "const {normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache, parseClaudeUsageText} = require('./usage-core');",
    1,
)

new_refresh = r'''let claudeTuiBusy=false;
let claudeTuiLastAttempt=0;

function claudeTrustedCwd(){
  try{
    const root=readJsonSafe(path.join(os.homedir(),'.claude.json'));
    const projects=root.projects||{};
    const candidates=Object.entries(projects)
      .filter(([p,v])=>v&&v.hasTrustDialogAccepted===true&&fs.existsSync(p))
      .sort((a,b)=>Number(b[1]?.lastSessionTimestamp||b[1]?.lastActivityAt||0)-Number(a[1]?.lastSessionTimestamp||a[1]?.lastActivityAt||0));
    if(candidates.length)return candidates[0][0];
  }catch{}
  return os.homedir();
}

function captureClaudeUsageTui(){
  return new Promise((resolve,reject)=>{
    if(process.platform!=='darwin')return reject(new Error('Claude TUI 캡처는 현재 macOS 전용입니다.'));
    const probe=shellClaudeProbe();
    const claude=probe.claudePath;
    if(!claude)return reject(new Error('Claude Code CLI를 찾지 못했습니다. 터미널에서 claude --version을 확인하세요.'));
    const cwd=claudeTrustedCwd();
    const env={...process.env,TERM:'xterm-256color',NO_COLOR:'1',FORCE_COLOR:'0'};
    let child;
    try{
      child=spawn('/usr/bin/script',['-q','/dev/null',claude,'--safe-mode'],{cwd,env,stdio:['pipe','pipe','pipe']});
    }catch(e){return reject(e)}
    let out='';let settled=false;
    const add=(buf)=>{out+=String(buf||'');if(out.length>1500000)out=out.slice(-1500000)};
    child.stdout.on('data',add);child.stderr.on('data',add);
    const finish=(err)=>{
      if(settled)return;settled=true;
      try{child.kill('SIGTERM')}catch{}
      if(err)reject(err);else resolve(out);
    };
    child.on('error',finish);
    child.on('close',()=>finish(null));
    // Feed the real interactive /usage command through a pseudo-terminal.
    setTimeout(()=>{try{child.stdin.write('/usage\n')}catch{}},1400);
    // Give the usage panel time to render, close it, then exit the hidden session.
    setTimeout(()=>{try{child.stdin.write('\x1b')}catch{}},4300);
    setTimeout(()=>{try{child.stdin.write('/exit\n')}catch{}},4600);
    setTimeout(()=>finish(null),7000);
  });
}

function fallbackClaudeSources(d){
  // First fallback: Claude's local cache when present.
  try{
    const cacheFile=path.join(os.homedir(),'.claude.json');
    const cacheRoot=readJsonSafe(cacheFile);
    let cacheTime=Date.now();try{cacheTime=fs.statSync(cacheFile).mtimeMs}catch{}
    const cached=parseClaudeCache(cacheRoot,cacheTime);
    if(cached&&(cached.fiveHour||cached.sevenDay))return {data:cached,error:null};
  }catch{}
  // Second fallback: statusLine capture for versions/accounts that still emit rate_limits.
  try{
    const raw=JSON.parse(fs.readFileSync(claudeUsageFile(),'utf8'));
    const data=normalizeClaude(raw);
    if(data&&(data.fiveHour||data.sevenDay))return {data,error:null};
  }catch{}
  return {data:null,error:d.blockers.length?'Claude 진단: '+d.blockers.join(' / '):'Claude 사용량을 찾지 못했습니다.'};
}

async function refreshClaude(){
  const d=claudeDiagnostics();
  const now=Date.now();
  // Run the real /usage TUI at startup and then at most once every 3 minutes.
  if(!claudeTuiBusy && (!state.claude || now-claudeTuiLastAttempt>=3*60*1000)){
    claudeTuiBusy=true;claudeTuiLastAttempt=now;
    try{
      const raw=await captureClaudeUsageTui();
      const parsed=parseClaudeUsageText(raw,Date.now());
      if(parsed&&(parsed.fiveHour||parsed.sevenDay)){
        state.claude=parsed;
        state.claudeError=d.blockers.length?'Claude 진단: '+d.blockers.join(' / '):null;
        updateUi();
        return;
      }
      const clean=String(raw||'');
      if(/login|sign in|authenticate/i.test(clean))state.claudeError='Claude Code 로그인이 필요합니다. 터미널에서 claude를 실행해 로그인하세요.';
      else if(/trust|workspace has not been trusted/i.test(clean))state.claudeError='Claude Code 작업 폴더 신뢰가 필요합니다. 평소 쓰는 프로젝트에서 Claude Code를 한 번 열고 Trust를 승인하세요.';
      else state.claudeError='Claude /usage 화면은 열렸지만 숫자 인식에 실패했습니다. Claude Code를 최신 버전으로 업데이트한 뒤 다시 시도하세요.';
    }catch(e){state.claudeError='Claude /usage 읽기 실패: '+e.message}
    finally{claudeTuiBusy=false}
  }
  if(!state.claude){
    const fb=fallbackClaudeSources(d);state.claude=fb.data;if(fb.error&&!state.claudeError)state.claudeError=fb.error;
  }
  updateUi();
}
'''

pattern=r"function refreshClaude\(\)\{.*?\n\}\nasync function refreshAll\(\)"
s,n=re.subn(pattern,new_refresh+"\nasync function refreshAll()",s,count=1,flags=re.S)
if n!=1:
    raise SystemExit(f'refreshClaude replacement failed: {n}')
main.write_text(s)

c=core.read_text()
insert=r'''
function stripClaudeTerminalText(text) {
  let s=String(text||'');
  s=s.replace(/\u001b\[[0-9;?]*[ -/]*[@-~]/g,' ');
  s=s.replace(/\u001b\][^\u0007]*\u0007/g,' ');
  s=s.replace(/\r/g,'\n');
  for(let i=0;i<8&&s.includes('\b');i++)s=s.replace(/[^\b]\b/g,'');
  s=s.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g,' ');
  return s.replace(/[ \t]+/g,' ').replace(/\n{3,}/g,'\n\n');
}

function parseClaudeUsageText(text, capturedAt = Date.now()) {
  const s=stripClaudeTerminalText(text);
  const clamp=(n)=>Math.max(0,Math.min(100,Number(n)));
  const find=(re)=>{const m=s.match(re);return m?clamp(m[1]):null};
  let five=find(/Current\s+session[\s\S]{0,700}?(\d{1,3})\s*%\s*used/i);
  let seven=find(/Current\s+week\s*\(all\s+models\)[\s\S]{0,700}?(\d{1,3})\s*%\s*used/i);
  if(five==null)five=find(/현재\s*세션[\s\S]{0,700}?(\d{1,3})\s*%/i);
  if(seven==null)seven=find(/현재\s*주[^\n]{0,80}[\s\S]{0,700}?(\d{1,3})\s*%/i);
  if(five==null||seven==null){
    const vals=[...s.matchAll(/(\d{1,3})\s*%\s*(?:used|사용)/gi)].map(m=>clamp(m[1]));
    if(five==null&&vals.length>0)five=vals[0];
    if(seven==null&&vals.length>1)seven=vals[1];
  }
  if(five==null&&seven==null)return null;
  return {
    service:'claude',
    fiveHour:five==null?null:{usedPercent:five,resetsAt:null},
    sevenDay:seven==null?null:{usedPercent:seven,resetsAt:null},
    updatedAt:Number(capturedAt)||Date.now(),
    source:'claude-interactive-usage'
  };
}
'''
if 'function parseClaudeUsageText(' not in c:
    c=c.replace('\nmodule.exports = { normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache };',insert+'\nmodule.exports = { normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache, parseClaudeUsageText };')
else:
    raise SystemExit('parseClaudeUsageText already exists')
core.write_text(c)

pkg=json.loads(pkgp.read_text());pkg['version']='0.5.7';pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkgp.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n')

tdir=root/'test';tdir.mkdir(exist_ok=True)
(tdir/'claude-usage-tui.test.js').write_text(r'''const test=require('node:test');
const assert=require('node:assert/strict');
const {parseClaudeUsageText}=require('../usage-core');

test('parses Claude interactive /usage text',()=>{
  const sample=`\u001b[2JCurrent session\n████████ 34% used\nResets 11pm (America/Chicago)\n\nCurrent week (all models)\n████ 18% used\nResets Mar 20, 12pm (America/Chicago)`;
  const d=parseClaudeUsageText(sample,1234);
  assert.equal(d.fiveHour.usedPercent,34);assert.equal(d.sevenDay.usedPercent,18);assert.equal(d.source,'claude-interactive-usage');assert.equal(d.updatedAt,1234);
});

test('parses compact usage text',()=>{
  const d=parseClaudeUsageText('/usage Current session: 56% used Current week (all models): 7% used');
  assert.equal(d.fiveHour.usedPercent,56);assert.equal(d.sevenDay.usedPercent,7);
});

test('returns null for unrelated terminal output',()=>{assert.equal(parseClaudeUsageText('Claude Code ready'),null)});
''')
print('v0.5.7 Claude PTY /usage patch applied')
