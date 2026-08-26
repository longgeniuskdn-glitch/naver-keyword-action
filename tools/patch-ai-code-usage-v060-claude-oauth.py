from pathlib import Path
import json, re

root = Path('/tmp/src/src/desktop')
main = root / 'main.js'
core = root / 'usage-core.js'
html = root / 'index.html'
pkgp = root / 'package.json'

s = main.read_text()
s = s.replace("const http = require('http');", "const http = require('http');\nconst https = require('https');", 1)
s = s.replace("const {normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache, parseClaudeUsageText, stripClaudeTerminalText} = require('./usage-core');", "const {normalizeCodex, shortValue, describeWindow, normalizeClaudeOauthUsage, parseClaudeAccessToken} = require('./usage-core');", 1)
s = s.replace("const VERSION='0.5.7';", "const VERSION='0.6.0';", 1)

new_block = r'''function readJsonSafe(file){try{return JSON.parse(fs.readFileSync(file,'utf8'))}catch{return {}}}
function shellClaudeProbe(){
  const fallback={claudePath:null};
  if(process.platform!=='darwin')return fallback;
  try{
    let claudePath=null;
    try{claudePath=String(execFileSync('/bin/zsh',['-lic','command -v claude || true'],{encoding:'utf8',timeout:3000,stdio:['ignore','pipe','pipe']})).trim()||null}catch{}
    return {claudePath};
  }catch{return fallback}
}
function claudeDir(){return path.join(os.homedir(),'.ai-code-usage')}
function claudeOauthCacheFile(){return path.join(claudeDir(),'claude-oauth-usage.json')}
function claudeIntegrationStatus(){return {installed:true,method:'oauth-api',command:null,blockers:[]}}

function readClaudeCredentialBlob(){
  const errors=[];
  if(process.platform==='darwin'){
    try{
      const out=String(execFileSync('/usr/bin/security',['find-generic-password','-s','Claude Code-credentials','-w'],{encoding:'utf8',timeout:20000,stdio:['ignore','pipe','pipe']}));
      if(out.trim())return {raw:out,source:'macOS Keychain'};
    }catch(e){errors.push('Keychain: '+String(e.stderr||e.message||e).trim().slice(0,180))}
  }
  const candidates=[];
  if(process.env.CLAUDE_CONFIG_DIR)candidates.push(path.join(process.env.CLAUDE_CONFIG_DIR,'.credentials.json'));
  candidates.push(path.join(os.homedir(),'.claude','.credentials.json'));
  for(const file of candidates){
    try{const raw=fs.readFileSync(file,'utf8');if(raw.trim())return {raw,source:file}}catch{}
  }
  throw new Error(errors[0]||'Claude Code 로그인 정보를 찾지 못했습니다. 터미널에서 claude를 실행해 로그인하세요.');
}

function readClaudeOauth(){
  const blob=readClaudeCredentialBlob();
  const parsed=parseClaudeAccessToken(blob.raw);
  if(!parsed?.accessToken)throw new Error('Claude Code OAuth access token을 찾지 못했습니다. 터미널에서 claude를 한 번 실행해 로그인 상태를 갱신하세요.');
  return {...parsed,credentialSource:blob.source};
}

function readClaudeAuthStatus(){
  try{
    const claude=shellClaudeProbe().claudePath;
    if(!claude)return null;
    const raw=String(execFileSync(claude,['auth','status','--json'],{encoding:'utf8',timeout:10000,stdio:['ignore','pipe','pipe']}));
    return JSON.parse(raw);
  }catch{return null}
}

function claudeHttpJson(token){
  return new Promise((resolve,reject)=>{
    const req=https.request('https://api.anthropic.com/api/oauth/usage',{
      method:'GET',
      headers:{'Authorization':'Bearer '+token,'anthropic-beta':'oauth-2025-04-20','Accept':'application/json'},
      timeout:20000
    },res=>{
      const chunks=[];let size=0;
      res.on('data',b=>{size+=b.length;if(size<=2_000_000)chunks.push(b)});
      res.on('end',()=>{
        const body=Buffer.concat(chunks).toString('utf8');let data=null;
        try{data=body?JSON.parse(body):null}catch{}
        resolve({status:Number(res.statusCode||0),headers:res.headers,data,body:body.slice(0,1200)});
      });
    });
    req.on('timeout',()=>req.destroy(new Error('Claude 사용량 서버 응답 시간 초과')));
    req.on('error',reject);req.end();
  });
}

function loadClaudeOauthCache(){
  try{
    const raw=JSON.parse(fs.readFileSync(claudeOauthCacheFile(),'utf8'));
    if(raw?.fiveHour||raw?.sevenDay)return raw;
  }catch{}
  return null;
}
function saveClaudeOauthCache(data){
  try{fs.mkdirSync(claudeDir(),{recursive:true});fs.writeFileSync(claudeOauthCacheFile(),JSON.stringify(data,null,2),{mode:0o600})}catch{}
}

let claudeFetchBusy=false;
let claudeLastAttempt=0;
let claudeNextAllowedAt=0;
const CLAUDE_REFRESH_MS=5*60*1000;

async function refreshClaude(force=false){
  const now=Date.now();
  if(!state.claude){const cached=loadClaudeOauthCache();if(cached)state.claude=cached}
  if(claudeFetchBusy)return updateUi();
  if(!force && now<claudeNextAllowedAt)return updateUi();
  if(!force && claudeLastAttempt && now-claudeLastAttempt<CLAUDE_REFRESH_MS)return updateUi();
  claudeFetchBusy=true;claudeLastAttempt=now;
  try{
    const auth=readClaudeOauth();
    const authStatus=readClaudeAuthStatus();
    let response=await claudeHttpJson(auth.accessToken);
    if(response.status===401){
      // Claude Code may have rotated credentials since the first read. Re-read once.
      const again=readClaudeOauth();
      if(again.accessToken!==auth.accessToken)response=await claudeHttpJson(again.accessToken);
    }
    if(response.status===200){
      const data=normalizeClaudeOauthUsage(response.data,Date.now());
      if(!data||( !data.fiveHour && !data.sevenDay))throw new Error('Claude 사용량 응답에 5시간/7일 한도가 없습니다.');
      data.planType=authStatus?.subscriptionType||auth.subscriptionType||auth.rateLimitTier||null;
      data.credentialSource=auth.credentialSource;
      state.claude=data;state.claudeError=null;claudeNextAllowedAt=0;saveClaudeOauthCache(data);
    }else if(response.status===401||response.status===403){
      state.claudeError='Claude OAuth가 거부됐습니다. 터미널에서 claude를 한 번 실행해 로그인 상태를 갱신한 뒤 새로고침하세요.';
    }else if(response.status===429){
      const h=String(response.headers?.['retry-after']||'').trim();const sec=Number(h);
      claudeNextAllowedAt=Date.now()+((Number.isFinite(sec)&&sec>0?sec:300)*1000);
      state.claudeError='Claude 사용량 서버가 요청을 제한 중입니다. 기존 값을 유지하고 잠시 후 자동 재시도합니다.';
    }else{
      const msg=response.data?.error?.message||response.data?.message||response.body||('HTTP '+response.status);
      state.claudeError='Claude 사용량 조회 실패: '+String(msg).slice(0,260);
    }
  }catch(e){state.claudeError='Claude 사용량 조회 실패: '+String(e.message||e)}
  finally{claudeFetchBusy=false;state.lastRefresh=Date.now();updateUi()}
}

function installClaudeIntegration(){state.claudeError='Claude는 별도 연동 설치가 필요 없습니다. 기존 Claude Code 로그인을 사용해 직접 조회합니다.';refreshClaude(true)}
function uninstallClaudeIntegration(){state.claudeError='Claude 직접 조회 방식은 별도 설치 항목이 없습니다.';updateUi()}
'''

pat=r"function readJsonSafe\(file\).*?\nasync function refreshAll\(\)"
s,n=re.subn(pat,lambda _m:new_block+"\nasync function refreshAll()",s,count=1,flags=re.S)
if n!=1: raise SystemExit(f'Claude block replacement failed: {n}')
s=s.replace("async function refreshAll(){refreshClaude();if(modeShows('codex'))await codex.refresh();else updateUi()}", "async function refreshAll(){refreshClaude(true);if(modeShows('codex'))await codex.refresh();else updateUi()}", 1)
s=s.replace("setTimeout(refreshAll,800);setInterval(()=>{refreshClaude();if(modeShows('codex'))codex.refresh();else updateUi()},60000);", "setTimeout(refreshAll,800);setInterval(()=>{refreshClaude(false);if(modeShows('codex'))codex.refresh();else updateUi()},60000);", 1)
main.write_text(s)

c=core.read_text()
insert=r'''
function claudeResetSeconds(v){
  if(v==null)return null;
  const n=Number(v);if(Number.isFinite(n)&&n>0)return n>1e12?Math.round(n/1000):Math.round(n);
  const ms=Date.parse(String(v));return Number.isFinite(ms)?Math.round(ms/1000):null;
}

function parseClaudeAccessToken(raw){
  let root=raw;
  if(typeof raw==='string'||Buffer.isBuffer(raw)){try{root=JSON.parse(String(raw))}catch{return null}}
  if(!root||typeof root!=='object')return null;
  const oauth=root.claudeAiOauth||root.claude_ai_oauth||{};
  const accessToken=oauth.accessToken||oauth.access_token||null;
  if(!accessToken)return null;
  return {accessToken:String(accessToken),subscriptionType:oauth.subscriptionType||oauth.subscription_type||null,rateLimitTier:oauth.rateLimitTier||oauth.rate_limit_tier||null,expiresAt:Number(oauth.expiresAt||oauth.expires_at)||null};
}

function normalizeClaudeOauthUsage(raw,capturedAt=Date.now()){
  if(!raw||typeof raw!=='object')return null;
  const pct=v=>clampPercent(v);
  const win=(v,pctKey='utilization')=>{
    if(!v||typeof v!=='object')return null;
    const p=pct(v[pctKey]??v.percent??v.usedPercent??v.used_percentage);
    return p==null?null:{usedPercent:p,resetsAt:claudeResetSeconds(v.resets_at??v.resetsAt)};
  };
  let fiveHour=win(raw.five_hour),sevenDay=win(raw.seven_day);
  const limits=Array.isArray(raw.limits)?raw.limits:[];
  if(!fiveHour){const x=limits.find(x=>String(x?.kind||'').toLowerCase()==='session');fiveHour=win(x,'percent')}
  if(!sevenDay){const x=limits.find(x=>String(x?.kind||'').toLowerCase()==='weekly_all');sevenDay=win(x,'percent')}
  if(!fiveHour&&!sevenDay)return null;
  return {service:'claude',fiveHour,sevenDay,updatedAt:Number(capturedAt)||Date.now(),source:'claude-oauth-usage'};
}
'''
if 'function normalizeClaudeOauthUsage(' not in c:
    c=c.replace('\nmodule.exports = ',insert+'\nmodule.exports = ')
# Replace any existing export object robustly.
c=re.sub(r"module\.exports\s*=\s*\{[^}]*\};", "module.exports = { normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache, parseClaudeUsageText, stripClaudeTerminalText, normalizeClaudeOauthUsage, parseClaudeAccessToken };", c, count=1)
core.write_text(c)

h=html.read_text()
h=h.replace('Claude Code는 공식 statusLine JSON의 rate_limits.five_hour / seven_day 값을 저장합니다. 첫 API 응답 전에는 값이 비어 있을 수 있습니다.','Claude Code의 기존 로그인 OAuth를 macOS Keychain에서 읽어 사용량 서버를 직접 조회합니다. 별도 Claude 로그인이나 토큰 입력은 필요 없습니다.')
h=h.replace('Claude 연동 설치/복구','Claude 사용량 다시 연결')
h=h.replace('<button onclick="removeClaude()">연동 제거</button>','')
h=h.replace("${d.claudeInstall.installed?'설치됨':'미설치'}", "${d.claudeInstall.method==='oauth-api'?'OAuth 직접 조회':''}")
html.write_text(h)

pkg=json.loads(pkgp.read_text());pkg['version']='0.6.0';pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkgp.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n')

tdir=root/'test';tdir.mkdir(exist_ok=True)
(tdir/'claude-oauth.test.js').write_text(r'''const test=require('node:test');
const assert=require('node:assert/strict');
const {normalizeClaudeOauthUsage,parseClaudeAccessToken}=require('../usage-core');

test('parses Claude Code credential JSON',()=>{
 const x=parseClaudeAccessToken(JSON.stringify({claudeAiOauth:{accessToken:'tok',subscriptionType:'max',rateLimitTier:'default_claude_max_5x',expiresAt:123}}));
 assert.equal(x.accessToken,'tok');assert.equal(x.subscriptionType,'max');
});

test('parses named OAuth usage windows',()=>{
 const d=normalizeClaudeOauthUsage({five_hour:{utilization:37.5,resets_at:'2026-08-27T10:00:00Z'},seven_day:{utilization:18,resets_at:'2026-09-01T00:00:00Z'}},1000);
 assert.equal(d.fiveHour.usedPercent,37.5);assert.equal(d.sevenDay.usedPercent,18);assert.equal(d.source,'claude-oauth-usage');
});

test('parses limits-array OAuth usage fallback',()=>{
 const d=normalizeClaudeOauthUsage({limits:[{kind:'session',percent:42,resets_at:'2026-08-27T10:00:00Z'},{kind:'weekly_all',percent:17,resets_at:'2026-09-01T00:00:00Z'}]});
 assert.equal(d.fiveHour.usedPercent,42);assert.equal(d.sevenDay.usedPercent,17);
});
''')
print('v0.6.0 direct Claude OAuth usage patch applied')
