from pathlib import Path
import json,re

root=Path('/tmp/src/src/desktop')
main=root/'main.js'; core=root/'usage-core.js'; html=root/'index.html'; pkgp=root/'package.json'
s=main.read_text(encoding='utf-8')
c=core.read_text(encoding='utf-8')
h=html.read_text(encoding='utf-8')

s=s.replace("const VERSION='0.6.6';","const VERSION='0.6.7';",1)

s=s.replace(
"const {normalizeCodex, shortValue, describeWindow, normalizeClaudeOauthUsage, parseClaudeAccessToken} = require('./usage-core');",
"const {normalizeCodex, shortValue, describeWindow, normalizeClaudeOauthUsage, parseClaudeAccessToken, parseClaudeUsageText} = require('./usage-core');",
1)

old_menu=r'''function remainingPercent(w){
  const n=Number(w?.usedPercent);
  return Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(100-n))):null;
}
function cxMenu(data){
  if(!data)return 'CX : --';
  const five=remainingPercent(data.fiveHour), seven=remainingPercent(data.sevenDay);
  const n=seven!=null?seven:five;
  return 'CX : '+(n==null?'--':n+'%');
}
function claudeMenu(data){
  if(!data)return 'CL 5H -- / W --';
  const five=remainingPercent(data.fiveHour), week=remainingPercent(data.sevenDay), fable=remainingPercent(data.fableWeek);
  let out='CL 5H '+(five==null?'--':five+'%')+' / W '+(week==null?'--':week+'%');
  if(fable!=null)out+=', F '+fable+'%';
  return out;
}
function label(){
  const parts=[];
  if(modeShows('codex')) parts.push(cxMenu(state.codex));
  if(modeShows('claude')) parts.push(claudeMenu(state.claude));
  return parts.join(' · ');
}
'''
new_menu=r'''function resetAtMs(w){
  const n=Number(w?.resetsAt);if(!Number.isFinite(n)||n<=0)return 0;
  return n>1e12?n:n*1000;
}
function windowExpired(w,now=Date.now()){
  const at=resetAtMs(w);return !!at&&at<=now;
}
function remainingPercent(w){
  if(windowExpired(w))return null;
  const n=Number(w?.usedPercent);
  return Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(100-n))):null;
}
function resetCountdown(w,now=Date.now()){
  const at=resetAtMs(w);if(!at)return '';
  const ms=at-now;if(ms<=0)return '재조회';
  const mins=Math.max(1,Math.ceil(ms/60000));
  if(mins<60)return mins+'m';
  const hours=Math.floor(mins/60), rem=mins%60;
  if(hours<24)return hours+'h'+(rem?rem+'m':'');
  const days=Math.floor(hours/24), rh=hours%24;
  return days+'d'+(rh?rh+'h':'');
}
function cxMenu(data){
  if(!data)return 'CX --';
  const five=remainingPercent(data.fiveHour), seven=remainingPercent(data.sevenDay);
  const win=five!=null?data.fiveHour:(seven!=null?data.sevenDay:null);
  const n=five!=null?five:seven, cd=resetCountdown(win);
  return 'CX '+(n==null?'--':n+'%')+(cd?'·'+cd:'');
}
function claudeMenu(data){
  if(!data)return 'CL 5H -- / W --';
  const five=remainingPercent(data.fiveHour), week=remainingPercent(data.sevenDay), fable=remainingPercent(data.fableWeek);
  const cd=resetCountdown(data.fiveHour);
  let out='CL 5H '+(five==null?'--':five+'%')+(cd?'·'+cd:'')+' / W '+(week==null?'--':week+'%');
  if(fable!=null)out+=', F '+fable+'%';
  return out;
}
function label(){
  const parts=[];
  if(modeShows('codex')) parts.push(cxMenu(state.codex));
  if(modeShows('claude')) parts.push(claudeMenu(state.claude));
  return parts.join(' · ');
}
'''
if old_menu not in s: raise SystemExit('v0.6.3 menu block not found')
s=s.replace(old_menu,new_menu,1)

local_block=r'''let claudeLocalUsageBusy=false;
let claudeLocalUsageLastAttempt=0;
const CLAUDE_LOCAL_USAGE_MIN_MS=10*60*1000;

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
    if(process.platform!=='darwin')return reject(new Error('macOS 전용'));
    const claude=findClaudeExecutable();
    if(!claude)return reject(new Error('Claude Code CLI 없음'));
    if(!fs.existsSync('/usr/bin/expect'))return reject(new Error('expect 없음'));
    const expectScript=`
set timeout 12
log_user 1
spawn -noecho $env(AICODE_CLAUDE)
after 2500
send -- "/usage\\r"
after 5000
send -- "\\033"
after 250
send -- "\\003"
after 250
catch {close}
catch {wait}
`;
    const env={...process.env,TERM:'xterm-256color',NO_COLOR:'1',FORCE_COLOR:'0',AICODE_CLAUDE:claude};
    let child;
    try{child=spawn('/usr/bin/expect',['-c',expectScript],{cwd:claudeTrustedCwd(),env,stdio:['ignore','pipe','pipe']})}
    catch(e){return reject(e)}
    let out='',settled=false;
    const add=b=>{out+=String(b||'');if(out.length>2000000)out=out.slice(-2000000)};
    child.stdout.on('data',add);child.stderr.on('data',add);
    const finish=err=>{if(settled)return;settled=true;try{child.kill('SIGTERM')}catch{};err?reject(err):resolve(out)};
    child.on('error',finish);child.on('close',()=>finish(null));
    setTimeout(()=>finish(null),11000);
  });
}
function mergeClaudeLocalUsage(parsed){
  if(!parsed)return false;
  const prev=state.claude||{};const now=Date.now();
  const keepReset=(oldW,newW)=>{
    if(newW?.resetsAt)return newW;
    const oldAt=resetAtMs(oldW);
    if(oldAt>now)return {...newW,resetsAt:oldW.resetsAt};
    return newW;
  };
  state.claude={...prev,
    fiveHour:parsed.fiveHour?keepReset(prev.fiveHour,parsed.fiveHour):prev.fiveHour,
    sevenDay:parsed.sevenDay?keepReset(prev.sevenDay,parsed.sevenDay):prev.sevenDay,
    updatedAt:now,source:'claude-interactive-usage-fallback'};
  saveClaudeOauthCache(state.claude);return true;
}
async function refreshClaudeLocalUsageFallback(force=false){
  const now=Date.now();
  if(claudeLocalUsageBusy)return false;
  if(!force&&claudeLocalUsageLastAttempt&&now-claudeLocalUsageLastAttempt<CLAUDE_LOCAL_USAGE_MIN_MS)return false;
  claudeLocalUsageBusy=true;claudeLocalUsageLastAttempt=now;
  try{
    const raw=await captureClaudeUsageTui();
    const parsed=parseClaudeUsageText(raw,Date.now());
    return mergeClaudeLocalUsage(parsed);
  }catch{return false}
  finally{claudeLocalUsageBusy=false}
}
'''
needle='function claudeRetryAfterAt(headers,now=Date.now()){'
if needle not in s: raise SystemExit('v0.6.6 retry helper not found')
s=s.replace(needle,local_block+'\n'+needle,1)

old_cool=r'''  if(now<claudeNextAllowedAt){
    state.claudeError='Claude 사용량 서버 요청 제한 대기 중입니다. 기존 값은 정상적으로 유지됩니다. '+claudeCooldownText(now)+' 자동 재조회합니다.';
    scheduleClaudeCooldownRefresh();
    return updateUi();
  }'''
new_cool=r'''  if(now<claudeNextAllowedAt){
    const localOk=await refreshClaudeLocalUsageFallback(false);
    state.claudeError=(localOk?'Claude API 요청 제한 대기 중 · 로컬 /usage로 최신값을 보완했습니다. ':'Claude API 요청 제한 대기 중 · 마지막 정상값을 유지합니다. ')+claudeCooldownText(now)+' 자동 재조회합니다.';
    scheduleClaudeCooldownRefresh();
    return updateUi();
  }'''
if old_cool not in s: raise SystemExit('cooldown early return not found')
s=s.replace(old_cool,new_cool,1)

old429="      state.claudeError='Claude 사용량 서버가 요청을 제한 중입니다. 연결은 정상이며 기존 값을 유지합니다. '+claudeCooldownText(now429)+' 자동 재조회합니다.';\n      scheduleClaudeCooldownRefresh();"
new429="      const localOk=await refreshClaudeLocalUsageFallback(true);\n      state.claudeError=(localOk?'Claude API 요청 제한 대기 중 · 로컬 /usage로 최신값을 보완했습니다. ':'Claude API 요청 제한 대기 중 · 마지막 정상값을 유지합니다. ')+claudeCooldownText(now429)+' 자동 재조회합니다.';\n      scheduleClaudeCooldownRefresh();"
if old429 not in s: raise SystemExit('v0.6.6 429 message block not found')
s=s.replace(old429,new429,1)

new_parser=r'''function stripClaudeTerminalText(text) {
  let s=String(text||'');
  s=s.replace(/\u001b\][\s\S]*?(?:\u0007|\u001b\\)/g,' ');
  s=s.replace(/\u001b\[[0-9;?]*[ -/]*[@-~]/g,' ');
  s=s.replace(/\u001b[()][A-Za-z0-9]/g,' ');
  s=s.replace(/\r/g,'\n');
  for(let i=0;i<12&&s.includes('\b');i++)s=s.replace(/[^\b]\b/g,'');
  s=s.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g,' ');
  return s.replace(/[ \t]+/g,' ').replace(/\n{3,}/g,'\n\n');
}
function claudeRelativeReset(section,capturedAt){
  const t=String(section||'');let m;
  m=t.match(/(?:(\d+)\s*시간)?\s*(?:(\d+)\s*분)?\s*후\s*재설정/i);
  if(m&&(m[1]||m[2]))return Math.round((Number(capturedAt)+((Number(m[1]||0)*60+Number(m[2]||0))*60000))/1000);
  m=t.match(/(?:resets?|reset)\s+(?:in\s+)?(?:(\d+)\s*h(?:ours?)?)?\s*(?:(\d+)\s*m(?:in(?:utes?)?)?)?/i);
  if(m&&(m[1]||m[2]))return Math.round((Number(capturedAt)+((Number(m[1]||0)*60+Number(m[2]||0))*60000))/1000);
  return null;
}
function parseClaudeUsageText(text, capturedAt = Date.now()) {
  const s=stripClaudeTerminalText(text);
  const clamp=n=>Math.max(0,Math.min(100,Number(n)));
  const pct=section=>{const m=String(section||'').match(/(\d{1,3})\s*%\s*(?:used|사용)?/i);return m?clamp(m[1]):null};
  const sessionMatch=s.match(/(?:Current\s+session|현재\s*세션)([\s\S]*?)(?=Current\s+week|현재\s*주|$)/i);
  const weekMatch=s.match(/(?:Current\s+week\s*\(all\s+models\)|현재\s*주[^\n]*)([\s\S]*?)(?=Current\s+week\s*\(|주간\s*[·\-]|$)/i);
  const session=sessionMatch?sessionMatch[1]:s, week=weekMatch?weekMatch[1]:'';
  let five=pct(session), seven=pct(week);
  if(five==null||seven==null){
    const vals=[...s.matchAll(/(\d{1,3})\s*%\s*(?:used|사용)/gi)].map(m=>clamp(m[1]));
    if(five==null&&vals.length>0)five=vals[0];
    if(seven==null&&vals.length>1)seven=vals[1];
  }
  if(five==null&&seven==null)return null;
  return {service:'claude',
    fiveHour:five==null?null:{usedPercent:five,resetsAt:claudeRelativeReset(session,capturedAt)},
    sevenDay:seven==null?null:{usedPercent:seven,resetsAt:claudeRelativeReset(week,capturedAt)},
    updatedAt:Number(capturedAt)||Date.now(),source:'claude-interactive-usage'};
}
'''
pat=r"function stripClaudeTerminalText\(text\) \{.*?\n\}\n\nfunction parseClaudeUsageText\(text, capturedAt = Date\.now\(\)\) \{.*?\n\}\n"
c,n=re.subn(pat,lambda _m:new_parser+'\n',c,count=1,flags=re.S)
if n!=1: raise SystemExit('TUI parser replacement failed')

old_claude="function claudeSvc(data,err,buttons=''){const f=data?.fableWeek?wline(data.fableWeek,'주간 · Fable'):'';const src=data?.credentialSource?`<div class=muted style=\"margin-top:8px\">연결: ${data.credentialSource}</div>`:'';document.getElementById('claude').innerHTML=`<div class=svc>Claude Code</div>${wline(data?.fiveHour,'5시간')}${wline(data?.sevenDay,'주간 · 전체')}${f}${src}${err?`<div class=err>${err}</div>`:''}<div class=row style=\"margin-top:10px\">${buttons}</div>`}"
new_claude="function claudeSvc(data,err,buttons=''){const stale=w=>{const n=Number(w?.resetsAt);const at=Number.isFinite(n)&&n>0?(n>1e12?n:n*1000):0;return !!at&&at<=Date.now()};const line=(w,name)=>stale(w)?`<div style=\"margin:8px 0\"><b>${name}:</b> 새 주기 · 업데이트 대기</div>`:wline(w,name);const f=data?.fableWeek?line(data.fableWeek,'주간 · Fable'):'';const src=data?.credentialSource?`<div class=muted style=\"margin-top:8px\">연결: ${data.credentialSource}</div>`:'';const wait=err&&err.startsWith('Claude API 요청 제한 대기 중');const msg=err?`<div class=${wait?'muted':'err'} style=\"margin-top:8px\">${err}</div>`:'';document.getElementById('claude').innerHTML=`<div class=svc>Claude Code</div>${line(data?.fiveHour,'5시간')}${line(data?.sevenDay,'주간 · 전체')}${f}${src}${msg}<div class=row style=\"margin-top:10px\">${buttons}</div>`}"
if old_claude not in h: raise SystemExit('claudeSvc not found')
h=h.replace(old_claude,new_claude,1)

h=h.replace('Claude Code의 기존 로그인 OAuth를 읽어 사용량 서버를 직접 조회합니다. 서버 요청 제한(429)이 발생하면 로그인은 유지한 채 마지막 정상값을 보여주고, 서버가 허용할 때까지 추가 호출을 막은 뒤 자동 재조회합니다.',
'Claude Code의 기존 로그인 OAuth를 읽어 사용량 서버를 조회합니다. 429가 발생하면 직접 API 호출을 멈추고, 백그라운드 공식 /usage에서 값을 보완하며 리셋 카운트다운은 로컬에서 계속 갱신합니다. 지난 주기의 값은 현재값처럼 표시하지 않습니다.')

main.write_text(s,encoding='utf-8');core.write_text(c,encoding='utf-8');html.write_text(h,encoding='utf-8')
pkg=json.loads(pkgp.read_text(encoding='utf-8'));pkg['version']='0.6.7';pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkgp.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

assert "const VERSION='0.6.7'" in s
assert 'resetCountdown' in s and 'windowExpired' in s
assert 'captureClaudeUsageTui' in s and 'refreshClaudeLocalUsageFallback' in s
assert 'parseClaudeUsageText' in s
assert '새 주기 · 업데이트 대기' in h
print('v0.6.7 local fallback + countdown patch applied')
