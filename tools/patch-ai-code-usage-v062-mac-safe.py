from pathlib import Path
import json, re

root=Path('/tmp/src/src/desktop')
main=root/'main.js'; core=root/'usage-core.js'; html=root/'index.html'; pkgp=root/'package.json'
s=main.read_text(encoding='utf-8')
c=core.read_text(encoding='utf-8')
h=html.read_text(encoding='utf-8')

# Version only; keep v0.6.0 collection architecture as the base.
s=s.replace("const VERSION='0.6.0';","const VERSION='0.6.2';",1)

# Menu-bar title: show both short and weekly overall windows, but not model-specific windows.
new_label=r'''function menuPercent(w){
  const n=Number(w?.usedPercent);return Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null
}
function menuUsage(prefix,data){
  if(!data)return prefix+' --';
  const five=menuPercent(data.fiveHour), seven=menuPercent(data.sevenDay);
  const bits=[];if(five!=null)bits.push('5h'+five+'%');if(seven!=null)bits.push('7d'+seven+'%');
  return prefix+' '+(bits.length?bits.join('/'):'--');
}
function label(){
  const parts=[];
  if(modeShows('codex')) parts.push(menuUsage('CX',state.codex));
  if(modeShows('claude')) parts.push(menuUsage('CL',state.claude));
  return parts.join(' · ');
}
'''
s,n=re.subn(r"function label\(\)\{.*?\n\}\n(?=function detailText\(\))",lambda m:new_label,s,count=1,flags=re.S)
if n!=1: raise SystemExit('label replacement failed')

# Add Fable only to detailed menu text; do not enumerate Opus/Sonnet/other model limits.
needle="    a.push(describeWindow(state.claude?.sevenDay,'주간'));"
if needle not in s: raise SystemExit('Claude detail weekly line not found')
s=s.replace(needle,needle+"\n    if(state.claude?.fableWeek) a.push(describeWindow(state.claude.fableWeek,'주간 Fable'));",1)

# Finder-launched apps often miss shell CLAUDE_CONFIG_DIR. Discover it explicitly.
old_probe=r'''function shellClaudeProbe(){
  const fallback={claudePath:null};
  if(process.platform!=='darwin')return fallback;
  try{
    let claudePath=null;
    try{claudePath=String(execFileSync('/bin/zsh',['-lic','command -v claude || true'],{encoding:'utf8',timeout:3000,stdio:['ignore','pipe','pipe']})).trim()||null}catch{}
    return {claudePath};
  }catch{return fallback}
}'''
new_probe=r'''function shellClaudeProbe(){
  const fallback={claudePath:null,configDir:null,claudeVersion:null};
  if(process.platform!=='darwin')return fallback;
  try{
    let claudePath=null,configDir=null,claudeVersion=null;
    try{claudePath=String(execFileSync('/bin/zsh',['-lic','command -v claude || true'],{encoding:'utf8',timeout:4000,stdio:['ignore','pipe','pipe']})).trim()||null}catch{}
    try{configDir=String(execFileSync('/bin/zsh',['-lic','printf %s "${CLAUDE_CONFIG_DIR:-}"'],{encoding:'utf8',timeout:4000,stdio:['ignore','pipe','pipe']})).trim()||null}catch{}
    if(claudePath){try{claudeVersion=String(execFileSync(claudePath,['--version'],{encoding:'utf8',timeout:4000,stdio:['ignore','pipe','pipe']})).trim().split(/\s+/)[0]||null}catch{}}
    return {claudePath,configDir,claudeVersion};
  }catch{return fallback}
}'''
if old_probe not in s: raise SystemExit('shellClaudeProbe base not found')
s=s.replace(old_probe,new_probe,1)

# Replace single-source credential selection with multi-source candidates.
pat=r"function readClaudeCredentialBlob\(\)\{.*?\n\}\n\nfunction readClaudeOauth\(\)\{.*?\n\}\n"
new_creds=r'''function readClaudeOauthCandidates(){
  const probe=shellClaudeProbe();
  const items=[],seenFiles=new Set(),seenTokens=new Set(),errors=[];
  const addRaw=(raw,source)=>{
    if(!raw||!String(raw).trim())return;
    const parsed=parseClaudeAccessToken(raw);if(!parsed?.accessToken)return;
    if(seenTokens.has(parsed.accessToken))return;seenTokens.add(parsed.accessToken);
    items.push({...parsed,credentialSource:source});
  };
  const addFile=file=>{
    if(!file)return;file=path.resolve(file);if(seenFiles.has(file))return;seenFiles.add(file);
    try{addRaw(fs.readFileSync(file,'utf8'),file)}catch{}
  };
  if(process.env.CLAUDE_CONFIG_DIR)addFile(path.join(process.env.CLAUDE_CONFIG_DIR,'.credentials.json'));
  if(probe.configDir)addFile(path.join(probe.configDir,'.credentials.json'));
  addFile(path.join(os.homedir(),'.claude','.credentials.json'));
  if(process.platform==='darwin'){
    try{
      const out=String(execFileSync('/usr/bin/security',['find-generic-password','-s','Claude Code-credentials','-w'],{encoding:'utf8',timeout:20000,stdio:['ignore','pipe','pipe']}));
      addRaw(out,'macOS Keychain');
    }catch(e){errors.push('Keychain: '+String(e.stderr||e.message||e).trim().slice(0,180))}
  }
  if(!items.length)throw new Error(errors[0]||'Claude Code 로그인 정보를 찾지 못했습니다. Claude Code에서 로그인한 뒤 다시 시도하세요.');
  return {items,probe};
}
'''
s,n=re.subn(pat,lambda m:new_creds,s,count=1,flags=re.S)
if n!=1: raise SystemExit('credential block replacement failed')

# Make OAuth usage request look like Claude Code and support source failover.
s=s.replace("function claudeHttpJson(token){","function claudeHttpJson(token,userAgent='claude-code/2.1.0'){",1)
s=s.replace("headers:{'Authorization':'Bearer '+token,'anthropic-beta':'oauth-2025-04-20','Accept':'application/json'},","headers:{'Authorization':'Bearer '+token,'anthropic-beta':'oauth-2025-04-20','Accept':'application/json','User-Agent':userAgent},",1)

new_refresh=r'''async function refreshClaude(force=false){
  const now=Date.now();
  if(!state.claude){const cached=loadClaudeOauthCache();if(cached)state.claude=cached}
  if(claudeFetchBusy)return updateUi();
  if(!force && now<claudeNextAllowedAt)return updateUi();
  if(!force && claudeLastAttempt && now-claudeLastAttempt<CLAUDE_REFRESH_MS)return updateUi();
  claudeFetchBusy=true;claudeLastAttempt=now;
  try{
    const discovered=readClaudeOauthCandidates();
    const authStatus=readClaudeAuthStatus();
    const ua='claude-code/'+(discovered.probe.claudeVersion||'2.1.0');
    let response=null,chosen=null,lastAuthError=null;
    for(const auth of discovered.items){
      const r=await claudeHttpJson(auth.accessToken,ua);
      if(r.status===200){response=r;chosen=auth;break}
      if(r.status===401||r.status===403){lastAuthError=r;continue}
      response=r;chosen=auth;break;
    }
    if(!response&&lastAuthError)response=lastAuthError;
    if(response?.status===200){
      const data=normalizeClaudeOauthUsage(response.data,Date.now());
      if(!data||(!data.fiveHour&&!data.sevenDay))throw new Error('Claude 사용량 응답에 5시간/7일 한도가 없습니다.');
      data.planType=authStatus?.subscriptionType||chosen?.subscriptionType||chosen?.rateLimitTier||null;
      data.credentialSource=chosen?.credentialSource||null;
      data.credentialCandidates=discovered.items.length;
      state.claude=data;state.claudeError=null;claudeNextAllowedAt=0;saveClaudeOauthCache(data);
    }else if(response?.status===401||response?.status===403){
      state.claudeError='발견한 Claude 로그인 '+discovered.items.length+'개를 모두 확인했지만 OAuth가 거부됐습니다. Claude Code에서 로그인 상태를 갱신한 뒤 다시 시도하세요.';
    }else if(response?.status===429){
      const hh=String(response.headers?.['retry-after']||'').trim(),sec=Number(hh);
      claudeNextAllowedAt=Date.now()+((Number.isFinite(sec)&&sec>0?sec:300)*1000);
      state.claudeError='Claude 사용량 서버가 요청을 제한 중입니다. 기존 값을 유지하고 잠시 후 자동 재시도합니다.';
    }else{
      const msg=response?.data?.error?.message||response?.data?.message||response?.body||('HTTP '+(response?.status||0));
      state.claudeError='Claude 사용량 조회 실패: '+String(msg).slice(0,260);
    }
  }catch(e){state.claudeError='Claude 사용량 조회 실패: '+String(e.message||e)}
  finally{claudeFetchBusy=false;state.lastRefresh=Date.now();updateUi()}
}
'''
s,n=re.subn(r"async function refreshClaude\(force=false\)\{.*?\n\}\n\n(?=function installClaudeIntegration)",lambda m:new_refresh,s,count=1,flags=re.S)
if n!=1: raise SystemExit('refreshClaude replacement failed')

# Parser: keep overall 5h + 7d, add only Fable scoped weekly window.
old_return="  return {service:'claude',fiveHour,sevenDay,updatedAt:Number(capturedAt)||Date.now(),source:'claude-oauth-usage'};"
if old_return not in c: raise SystemExit('OAuth parser return not found')
fable_code=r'''  let fableWeek=win(raw.seven_day_fable);
  if(!fableWeek){
    const scoped=limits.find(x=>{
      const name=String(x?.scope?.model?.display_name??x?.scope?.model?.displayName??'').trim().toLowerCase();
      return name==='fable' && String(x?.kind??'').toLowerCase().includes('weekly');
    });
    if(scoped)fableWeek=win(scoped,'percent');
  }
  return {service:'claude',fiveHour,sevenDay,fableWeek,updatedAt:Number(capturedAt)||Date.now(),source:'claude-oauth-usage'};'''
c=c.replace(old_return,fable_code,1)

# Desktop detail UI. Claude shows only 5h, weekly overall, and optional Fable.
old_svc="function svc(id,title,data,err,buttons=''){document.getElementById(id).innerHTML=`<div class=svc>${title}</div>${wline(data?.fiveHour,'5시간')}${wline(data?.sevenDay,'7일')}${err?`<div class=err>${err}</div>`:''}<div class=row style=\"margin-top:10px\">${buttons}</div>`}"
if old_svc not in h: raise SystemExit('svc function not found')
new_svc=old_svc+"\nfunction claudeSvc(data,err,buttons=''){const f=data?.fableWeek?wline(data.fableWeek,'주간 · Fable'):'';const src=data?.credentialSource?`<div class=muted style=\"margin-top:8px\">연결: ${data.credentialSource}</div>`:'';document.getElementById('claude').innerHTML=`<div class=svc>Claude Code</div>${wline(data?.fiveHour,'5시간')}${wline(data?.sevenDay,'주간 · 전체')}${f}${src}${err?`<div class=err>${err}</div>`:''}<div class=row style=\"margin-top:10px\">${buttons}</div>`}"
h=h.replace(old_svc,new_svc,1)
old_render="svc('claude','Claude Code',d.state.claude,d.state.claudeError,`<button onclick=\"installClaude()\">Claude 사용량 다시 연결</button><span class=\"muted\">${d.claudeInstall.method==='oauth-api'?'OAuth 직접 조회':''}</span>`)"
if old_render not in h: raise SystemExit('Claude render call not found')
h=h.replace(old_render,"claudeSvc(d.state.claude,d.state.claudeError,`<button onclick=\"installClaude()\">Claude 사용량 다시 연결</button><span class=\"muted\">${d.claudeInstall.method==='oauth-api'?'OAuth 직접 조회':''}</span>`)",1)
h=h.replace('Claude Code의 기존 로그인 OAuth를 macOS Keychain에서 읽어 사용량 서버를 직접 조회합니다. 별도 Claude 로그인이나 토큰 입력은 필요 없습니다.','Claude Code의 기존 OAuth를 자격증명 파일과 macOS Keychain에서 모두 확인합니다. Max 요금제는 주간 전체와 Fable만 표시합니다.')

# Package version.
pkg=json.loads(pkgp.read_text(encoding='utf-8'));pkg['version']='0.6.2';pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkgp.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
main.write_text(s,encoding='utf-8');core.write_text(c,encoding='utf-8');html.write_text(h,encoding='utf-8')

# Tests for the new Max/Fable shape and menu contract. Do not include credentials/tokens in outputs.
t=(root/'test');t.mkdir(exist_ok=True)
(t/'claude-v062.test.js').write_text(r'''const test=require('node:test');
const assert=require('node:assert/strict');
const {normalizeClaudeOauthUsage}=require('../usage-core');

test('keeps overall and only extracts Fable scoped weekly window',()=>{
 const d=normalizeClaudeOauthUsage({five_hour:{utilization:78,resets_at:'2026-08-29T11:00:00Z'},seven_day:{utilization:22,resets_at:'2026-08-29T13:00:00Z'},limits:[{kind:'weekly_scoped',group:'weekly',percent:24,resets_at:'2026-08-29T13:00:00Z',scope:{model:{id:'fable-x',display_name:'Fable'}}},{kind:'weekly_scoped',group:'weekly',percent:55,scope:{model:{display_name:'Opus'}}}]});
 assert.equal(d.fiveHour.usedPercent,78);assert.equal(d.sevenDay.usedPercent,22);assert.equal(d.fableWeek.usedPercent,24);assert.equal(d.opusWeek,undefined);
});

test('hides Fable when account has no Fable scoped window',()=>{
 const d=normalizeClaudeOauthUsage({five_hour:{utilization:10},seven_day:{utilization:20},limits:[{kind:'weekly_scoped',percent:30,scope:{model:{display_name:'Sonnet'}}}]});
 assert.equal(d.fableWeek,null);
});
''',encoding='utf-8')
print('v0.6.2 Mac safe update patch applied')
