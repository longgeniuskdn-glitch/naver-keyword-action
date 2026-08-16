from pathlib import Path
import json, re

root = Path('/tmp/src/src/desktop')
main = root / 'main.js'
core = root / 'usage-core.js'
pkgp = root / 'package.json'

s = main.read_text()
s = s.replace("const VERSION='0.5.5';", "const VERSION='0.5.6';", 1)
s = s.replace(
    "const {normalizeCodex, normalizeClaude, shortValue, describeWindow} = require('./usage-core');",
    "const {normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache} = require('./usage-core');",
    1,
)

old_refresh = r'''function refreshClaude(){
  const d=claudeDiagnostics();
  try{
    const raw=JSON.parse(fs.readFileSync(claudeUsageFile(),'utf8'));state.claude=normalizeClaude(raw);const age=Date.now()-state.claude.updatedAt;const has=!!(state.claude?.fiveHour||state.claude?.sevenDay);
    if(d.blockers.length)state.claudeError='Claude 진단: '+d.blockers.join(' / ');
    else if(!has&&d.lastInvocation)state.claudeError='Claude statusLine은 실행 중이지만 rate_limits가 없습니다. Pro/Max 구독, 첫 API 응답, API키/Bedrock/Vertex 사용 여부를 확인하세요.';
    else if(age>15*60*1000)state.claudeError='Claude 값이 15분 이상 갱신되지 않았습니다. Claude Code를 다시 실행하고 메시지를 1회 보내세요.';
    else state.claudeError=null;
  }catch{
    state.claude=null;const integ=claudeIntegrationStatus();
    if(!integ.installed)state.claudeError=`Claude 연동이 설치되지 않았습니다. 현재 설정 경로: ${d.settingsFile}`;
    else if(d.blockers.length)state.claudeError='Claude 진단: '+d.blockers.join(' / ');
    else if(d.lastInvocation)state.claudeError='Claude statusLine 호출은 확인됐지만 사용량 값이 없습니다.';
    else state.claudeError='Claude statusLine 호출 기록이 없습니다. Claude Code를 완전히 종료 후 다시 실행하고 프로젝트 Trust를 승인하세요. Claude에 statusline skipped · restart to fix가 뜨면 재시작이 필요합니다.';
  }
}
'''

new_refresh = r'''function refreshClaude(){
  const d=claudeDiagnostics();
  // Primary source on macOS: Claude Code's own local cache used by /usage.
  // This avoids the upstream statusLine regression where rate_limits can be absent for Pro/Max accounts.
  try{
    const cacheFile=path.join(os.homedir(),'.claude.json');
    const cacheRoot=readJsonSafe(cacheFile);
    let cacheTime=Date.now();try{cacheTime=fs.statSync(cacheFile).mtimeMs}catch{}
    const cached=parseClaudeCache(cacheRoot,cacheTime);
    if(cached&&(cached.fiveHour||cached.sevenDay)){
      state.claude=cached;
      const age=Date.now()-cached.updatedAt;
      if(d.blockers.length)state.claudeError='Claude 진단: '+d.blockers.join(' / ');
      else if(age>60*60*1000)state.claudeError='Claude 로컬 사용량 캐시가 1시간 이상 갱신되지 않았습니다. Claude Code에서 메시지를 보내거나 /usage를 한 번 열어 갱신하세요.';
      else state.claudeError=null;
      return;
    }
  }catch{}

  // Secondary source: statusLine capture when Claude Code actually includes rate_limits.
  try{
    const raw=JSON.parse(fs.readFileSync(claudeUsageFile(),'utf8'));state.claude=normalizeClaude(raw);const age=Date.now()-state.claude.updatedAt;const has=!!(state.claude?.fiveHour||state.claude?.sevenDay);
    if(d.blockers.length)state.claudeError='Claude 진단: '+d.blockers.join(' / ');
    else if(!has&&d.lastInvocation)state.claudeError='Claude statusLine은 실행 중이지만 rate_limits가 없습니다. Claude Code의 알려진 statusLine 누락 문제일 수 있습니다.';
    else if(age>15*60*1000)state.claudeError='Claude 값이 15분 이상 갱신되지 않았습니다. Claude Code에서 메시지를 보내거나 /usage를 한 번 열어보세요.';
    else state.claudeError=null;
  }catch{
    state.claude=null;const integ=claudeIntegrationStatus();
    if(d.blockers.length)state.claudeError='Claude 진단: '+d.blockers.join(' / ');
    else if(d.lastInvocation)state.claudeError='Claude statusLine은 호출됐지만 rate_limits가 없습니다. Claude Code에서 /usage를 한 번 열면 로컬 캐시를 읽어 자동 표시합니다.';
    else if(!integ.installed)state.claudeError='Claude 사용량 캐시가 아직 없습니다. Claude Code에서 /usage를 한 번 열거나 메시지를 1회 보내세요.';
    else state.claudeError='Claude 사용량을 아직 찾지 못했습니다. Claude Code에서 /usage를 한 번 열고 이 앱에서 새로고침하세요.';
  }
}
'''

if old_refresh not in s:
    raise SystemExit('refreshClaude block not found after v0.5.5 patch')
s = s.replace(old_refresh, new_refresh, 1)
main.write_text(s)

c = core.read_text()
insert = r'''
function parseClaudeCache(root, capturedAt = Date.now()) {
  if (!root || typeof root !== 'object') return null;
  const cache = root.cachedUsageUtilization || root.cached_usage_utilization;
  if (!cache) return null;
  const pct = (v) => {
    if (v == null) return null;
    if (typeof v === 'number' && Number.isFinite(v)) return clampPercent(v);
    if (typeof v !== 'object') return null;
    for (const k of ['usedPercent','used_percentage','utilization','percent']) {
      const n = Number(v[k]); if (Number.isFinite(n)) return clampPercent(n);
    }
    return null;
  };
  const reset = (v) => {
    if (!v || typeof v !== 'object') return null;
    const raw = v.resetsAt ?? v.resets_at ?? v.resetAt ?? v.reset_at;
    if (raw == null) return null;
    const n = Number(raw);
    if (Number.isFinite(n) && n > 0) return n > 1e12 ? Math.round(n/1000) : Math.round(n);
    const ms = Date.parse(String(raw)); return Number.isFinite(ms) ? Math.round(ms/1000) : null;
  };
  const win = (v) => { const p = pct(v); return p == null ? null : {usedPercent:p,resetsAt:reset(v)}; };
  const arr = Array.isArray(cache) ? cache : (Array.isArray(cache.limits) ? cache.limits : []);
  const modelScoped = (x) => !!(x && x.scope && x.scope.model);
  const findFive = () => arr.find(x => {
    const kind=String(x?.kind||'').toLowerCase(), group=String(x?.group||'').toLowerCase();
    return kind.includes('five') || kind.includes('session') || group==='session' || group==='five_hour';
  });
  const findSeven = () => arr.find(x => {
    const kind=String(x?.kind||'').toLowerCase(), group=String(x?.group||'').toLowerCase();
    return !modelScoped(x) && (kind==='weekly' || kind.includes('seven') || group==='weekly' || group==='seven_day');
  });
  const fiveRaw = cache.five_hour || cache.fiveHour || cache.current_session || cache.session || findFive();
  const sevenRaw = cache.seven_day || cache.sevenDay || cache.current_week || cache.weekly || findSeven();
  const fiveHour = win(fiveRaw), sevenDay = win(sevenRaw);
  if (!fiveHour && !sevenDay) return null;
  return {service:'claude',fiveHour,sevenDay,updatedAt:Number(capturedAt)||Date.now(),source:'claude-local-cache'};
}
'''

if 'function parseClaudeCache(' not in c:
    c = c.replace('\nmodule.exports = { normalizeCodex, normalizeClaude, shortValue, describeWindow };', insert + '\nmodule.exports = { normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache };')
else:
    raise SystemExit('parseClaudeCache already exists')
core.write_text(c)

pkg = json.loads(pkgp.read_text())
pkg['version'] = '0.5.6'
pkg['build']['mac']['artifactName'] = 'AI-Code-Usage-Mac-M4-v${version}.${ext}'
pkgp.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + '\n')

test = root / 'test' / 'claude-cache.test.js'
test.write_text(r'''const test=require('node:test');
const assert=require('node:assert/strict');
const {parseClaudeCache}=require('../usage-core');

test('parses OAuth-style cachedUsageUtilization',()=>{
  const d=parseClaudeCache({cachedUsageUtilization:{five_hour:{utilization:37,resets_at:'2026-08-17T08:00:00Z'},seven_day:{utilization:62,resets_at:'2026-08-20T00:00:00Z'}}},1234567890000);
  assert.equal(d.fiveHour.usedPercent,37);assert.equal(d.sevenDay.usedPercent,62);assert.equal(d.source,'claude-local-cache');assert.equal(d.updatedAt,1234567890000);
});

test('parses limits array and ignores model-scoped weekly item',()=>{
  const d=parseClaudeCache({cachedUsageUtilization:{limits:[
    {kind:'session',group:'session',percent:11,resets_at:'2026-08-17T08:00:00Z'},
    {kind:'weekly',group:'weekly',percent:44,resets_at:'2026-08-20T00:00:00Z',scope:{model:null}},
    {kind:'weekly_scoped',group:'weekly',percent:88,resets_at:'2026-08-20T00:00:00Z',scope:{model:{display_name:'Fable'}}}
  ]}});
  assert.equal(d.fiveHour.usedPercent,11);assert.equal(d.sevenDay.usedPercent,44);
});

test('returns null when cache has no account windows',()=>{assert.equal(parseClaudeCache({cachedUsageUtilization:{limits:[]}}),null)});
''')
print('v0.5.6 Claude local cache fallback patch applied')
