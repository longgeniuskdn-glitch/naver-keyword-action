from pathlib import Path
import json,re

root=Path('/tmp/src/src/desktop')
main=root/'main.js'; core=root/'usage-core.js'; html=root/'index.html'; pkgp=root/'package.json'
s=main.read_text(encoding='utf-8')
c=core.read_text(encoding='utf-8')
h=html.read_text(encoding='utf-8')

s=s.replace("const VERSION='0.6.7';","const VERSION='0.6.8';",1)

# Codex status bar: percentage only. Do not add countdowns or change Codex collection logic.
old_cx=r'''function cxMenu(data){
  if(!data)return 'CX --';
  const five=remainingPercent(data.fiveHour), seven=remainingPercent(data.sevenDay);
  const win=five!=null?data.fiveHour:(seven!=null?data.sevenDay:null);
  const n=five!=null?five:seven, cd=resetCountdown(win);
  return 'CX '+(n==null?'--':n+'%')+(cd?'·'+cd:'');
}'''
new_cx=r'''function cxMenu(data){
  if(!data)return 'CX : --';
  const five=remainingPercent(data.fiveHour), seven=remainingPercent(data.sevenDay);
  const n=seven!=null?seven:five;
  return 'CX : '+(n==null?'--':n+'%');
}'''
if old_cx not in s: raise SystemExit('v0.6.7 cxMenu not found')
s=s.replace(old_cx,new_cx,1)

# Claude local /usage becomes primary. OAuth remains fallback only.
local_primary=r'''async function refreshClaudeLocalPrimary(force=false){
  const now=Date.now();
  if(claudeLocalUsageBusy)return false;
  if(!force&&claudeLocalUsageLastAttempt&&now-claudeLocalUsageLastAttempt<3*60*1000)return false;
  claudeLocalUsageBusy=true;claudeLocalUsageLastAttempt=now;
  try{
    const raw=await captureClaudeUsageTui();
    const parsed=parseClaudeUsageText(raw,Date.now());
    if(!parsed||(!parsed.fiveHour&&!parsed.sevenDay))return false;
    const prev=state.claude||{};
    const keep=(oldW,newW)=>{
      if(!newW)return oldW||null;
      if(newW.resetsAt)return newW;
      const oldAt=resetAtMs(oldW);
      if(oldAt>Date.now())return {...newW,resetsAt:oldW.resetsAt};
      return newW;
    };
    state.claude={...prev,
      fiveHour:keep(prev.fiveHour,parsed.fiveHour),
      sevenDay:keep(prev.sevenDay,parsed.sevenDay),
      fableWeek:parsed.fableWeek?keep(prev.fableWeek,parsed.fableWeek):prev.fableWeek,
      updatedAt:Date.now(),source:'claude-interactive-usage',credentialSource:'Claude Code /usage (local)'};
    state.claudeError=null;
    saveClaudeOauthCache(state.claude);
    return true;
  }catch{return false}
  finally{claudeLocalUsageBusy=false}
}
'''
needle='function claudeRetryAfterAt(headers,now=Date.now()){'
if needle not in s: raise SystemExit('retry helper missing')
s=s.replace(needle,local_primary+'\n'+needle,1)

# Try Claude /usage before touching the OAuth usage endpoint.
needle2="  if(claudeFetchBusy)return updateUi();\n"
insert2="  if(claudeFetchBusy)return updateUi();\n  const localOkPrimary=await refreshClaudeLocalPrimary(force);\n  if(localOkPrimary){claudeNextAllowedAt=0;claudeRateLimitStreak=0;if(claudeCooldownTimer){clearTimeout(claudeCooldownTimer);claudeCooldownTimer=null;}state.lastRefresh=Date.now();updateUi();return;}\n"
if needle2 not in s: raise SystemExit('refresh busy line missing')
s=s.replace(needle2,insert2,1)

# OAuth rejection no longer means the Claude Code login itself is broken.
old403="      state.claudeError='발견한 Claude 로그인 '+discovered.items.length+'개를 모두 확인했지만 OAuth가 거부됐습니다. Claude Code에서 로그인 상태를 갱신한 뒤 다시 시도하세요.';"
new403="      const statusNow=discovered.authStatus||readClaudeAuthStatus();\n      state.claudeError=statusNow?.loggedIn?'Claude Code 로그인은 정상입니다. 로컬 /usage를 읽지 못했고 OAuth 보조 조회도 거부됐습니다. 아래 버튼으로 Claude Code 로그인을 갱신한 뒤 다시 시도하세요.':'Claude Code 로그인이 확인되지 않습니다. 아래 버튼으로 로그인하세요.';"
if old403 not in s: raise SystemExit('403 message block missing')
s=s.replace(old403,new403,1)

# Reconnect: first retry local /usage. Only launch official auth if local usage still fails.
pat=r"function installClaudeIntegration\(\)\{.*?\n\}\nfunction uninstallClaudeIntegration\(\)\{"
m=re.search(pat,s,flags=re.S)
if not m: raise SystemExit('installClaudeIntegration block missing')
new_install=r'''async function installClaudeIntegration(){
  state.claudeError='Claude Code 로컬 /usage를 다시 확인합니다.';updateUi();
  if(await refreshClaudeLocalPrimary(true)){state.claudeError=null;updateUi();return}
  const auth=readClaudeAuthStatus();
  if(auth?.loggedIn){state.claudeError='Claude Code 로그인은 확인됐지만 로컬 /usage 읽기에 실패했습니다. 공식 로그인을 한 번 갱신합니다.';updateUi();}
  try{launchClaudeLoginHidden()}
  catch(e){state.claudeError='Claude 연결 복구 실패: '+String(e.message||e);updateUi()}
}
function uninstallClaudeIntegration(){'''
s=s[:m.start()]+new_install+s[m.end():]

# Clarify source in the UI.
h=h.replace('Claude Code의 공식 /usage를 이 Mac에서 백그라운드로 직접 읽는 방식이 기본입니다. 터미널은 열지 않습니다. OAuth 직접 조회는 로컬 /usage가 실패할 때만 보조로 사용합니다.',
'Claude Code의 공식 /usage를 이 Mac에서 백그라운드로 직접 읽습니다. 터미널은 열지 않습니다. OAuth 직접 조회는 로컬 /usage가 실패할 때만 보조로 사용합니다.')

# Extend the local /usage parser to capture a Fable weekly section when present.
old_return="  return {service:'claude',\n    fiveHour:five==null?null:{usedPercent:five,resetsAt:claudeRelativeReset(session,capturedAt)},\n    sevenDay:seven==null?null:{usedPercent:seven,resetsAt:claudeRelativeReset(week,capturedAt)},\n    updatedAt:Number(capturedAt)||Date.now(),source:'claude-interactive-usage'};"
new_return="  const fableMatch=s.match(/(?:Current\\s+week\\s*\\([^)]*Fable[^)]*\\)|(?:주간|현재\\s*주)[^\\n]*Fable)([\\s\\S]*?)(?=Current\\s+week|현재\\s*주|$)/i);\n  const fableSec=fableMatch?fableMatch[1]:'';\n  const fable=fableSec?pct(fableSec):null;\n  return {service:'claude',\n    fiveHour:five==null?null:{usedPercent:five,resetsAt:claudeRelativeReset(session,capturedAt)},\n    sevenDay:seven==null?null:{usedPercent:seven,resetsAt:claudeRelativeReset(week,capturedAt)},\n    fableWeek:fable==null?null:{usedPercent:fable,resetsAt:claudeRelativeReset(fableSec,capturedAt)},\n    updatedAt:Number(capturedAt)||Date.now(),source:'claude-interactive-usage'};"
if old_return not in c: raise SystemExit('local parser return missing')
c=c.replace(old_return,new_return,1)

# Package version.
pkg=json.loads(pkgp.read_text(encoding='utf-8'));pkg['version']='0.6.8';pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkgp.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
main.write_text(s,encoding='utf-8');core.write_text(c,encoding='utf-8');html.write_text(h,encoding='utf-8')

assert "const VERSION='0.6.8'" in s
assert "return 'CX : '" in s
assert 'refreshClaudeLocalPrimary' in s
assert "credentialSource:'Claude Code /usage (local)'" in s
assert 'fableWeek' in c
print('v0.6.8 Claude local-first patch applied')
