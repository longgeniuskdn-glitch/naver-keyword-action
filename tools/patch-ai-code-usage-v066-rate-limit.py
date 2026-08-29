from pathlib import Path
import json,re

root=Path('/tmp/src/src/desktop')
main=root/'main.js'; pkgp=root/'package.json'; html=root/'index.html'
s=main.read_text(encoding='utf-8')
h=html.read_text(encoding='utf-8')

s=s.replace("const VERSION='0.6.5';","const VERSION='0.6.6';",1)

old_decl="let claudeFetchBusy=false;\nlet claudeLastAttempt=0;\nlet claudeNextAllowedAt=0;\nconst CLAUDE_REFRESH_MS=5*60*1000;"
new_decl="let claudeFetchBusy=false;\nlet claudeLastAttempt=0;\nlet claudeNextAllowedAt=0;\nlet claudeRateLimitStreak=0;\nlet claudeCooldownTimer=null;\nconst CLAUDE_REFRESH_MS=5*60*1000;"
if old_decl not in s: raise SystemExit('Claude throttle declarations not found')
s=s.replace(old_decl,new_decl,1)

helpers=r'''function claudeRetryAfterAt(headers,now=Date.now()){
  const raw=String(headers?.['retry-after']||'').trim();
  if(raw){
    const sec=Number(raw);
    if(Number.isFinite(sec)&&sec>0)return now+sec*1000;
    const at=Date.parse(raw);
    if(Number.isFinite(at)&&at>now)return at;
  }
  const reset=String(headers?.['x-ratelimit-reset']||headers?.['anthropic-ratelimit-unified-reset']||'').trim();
  if(reset){
    const n=Number(reset);
    if(Number.isFinite(n)&&n>0){
      const at=n>1e12?n:n*1000;
      if(at>now)return at;
    }
    const at=Date.parse(reset);
    if(Number.isFinite(at)&&at>now)return at;
  }
  return 0;
}
function claudeCooldownText(now=Date.now()){
  const ms=Math.max(0,claudeNextAllowedAt-now);
  const min=Math.max(1,Math.ceil(ms/60000));
  return min+'분 후';
}
function scheduleClaudeCooldownRefresh(){
  if(claudeCooldownTimer){clearTimeout(claudeCooldownTimer);claudeCooldownTimer=null;}
  if(!claudeNextAllowedAt)return;
  const delay=Math.max(1500,Math.min(claudeNextAllowedAt-Date.now()+1500,0x7fffffff));
  claudeCooldownTimer=setTimeout(()=>{claudeCooldownTimer=null;refreshClaude(false)},delay);
}
'''
needle="async function refreshClaude(force=false){"
if needle not in s: raise SystemExit('refreshClaude not found')
s=s.replace(needle,helpers+"\n"+needle,1)

old_gate="  if(!force && now<claudeNextAllowedAt)return updateUi();"
new_gate="  if(now<claudeNextAllowedAt){\n    state.claudeError='Claude 사용량 서버 요청 제한 대기 중입니다. 기존 값은 정상적으로 유지됩니다. '+claudeCooldownText(now)+' 자동 재조회합니다.';\n    scheduleClaudeCooldownRefresh();\n    return updateUi();\n  }"
if old_gate not in s: raise SystemExit('Claude cooldown gate not found')
s=s.replace(old_gate,new_gate,1)

old_success="      state.claude=data;state.claudeError=null;claudeNextAllowedAt=0;saveClaudeOauthCache(data);"
new_success="      state.claude=data;state.claudeError=null;claudeNextAllowedAt=0;claudeRateLimitStreak=0;\n      if(claudeCooldownTimer){clearTimeout(claudeCooldownTimer);claudeCooldownTimer=null;}\n      saveClaudeOauthCache(data);"
if old_success not in s: raise SystemExit('Claude success block not found')
s=s.replace(old_success,new_success,1)

new_429=r'''    }else if(response?.status===429){
      const now429=Date.now();
      claudeRateLimitStreak=Math.min(claudeRateLimitStreak+1,8);
      const serverAt=claudeRetryAfterAt(response.headers,now429);
      const fallbackMin=Math.min(60,10*Math.pow(2,Math.max(0,claudeRateLimitStreak-1)));
      claudeNextAllowedAt=Math.max(serverAt||0,now429+fallbackMin*60*1000);
      state.claudeError='Claude 사용량 서버가 요청을 제한 중입니다. 연결은 정상이며 기존 값을 유지합니다. '+claudeCooldownText(now429)+' 자동 재조회합니다.';
      scheduleClaudeCooldownRefresh();
'''
pat=r"    \}else if\(response\?\.status===429\)\{.*?(?=    \}else\{)"
s,n=re.subn(pat,lambda _m:new_429,s,count=1,flags=re.S)
if n!=1: raise SystemExit('429 block not found')

# Clarify the common multi-Mac help text without changing credential behavior.
marker='각 Mac의 Claude Code 로그인을 독립적으로 자동 탐색합니다.'
if marker in h and '429 요청 제한' not in h:
    h=h.replace(marker,marker+' 429 요청 제한이 발생해도 로그인은 끊지 않고 마지막 정상값을 유지하며 대기시간 이후 자동 재조회합니다.',1)

main.write_text(s,encoding='utf-8');html.write_text(h,encoding='utf-8')
pkg=json.loads(pkgp.read_text(encoding='utf-8'));pkg['version']='0.6.6';pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkgp.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

assert "const VERSION='0.6.6'" in s
assert 'claudeRetryAfterAt' in s
assert 'claudeRateLimitStreak' in s
assert 'if(now<claudeNextAllowedAt)' in s
assert 'scheduleClaudeCooldownRefresh' in s
assert 'fallbackMin' in s
assert 'if(!force && now<claudeNextAllowedAt)' not in s
print('v0.6.6 Claude rate-limit stability patch applied')
