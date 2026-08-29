from pathlib import Path
import json,re

root=Path('/tmp/src/src/desktop')
main=root/'main.js'; pkgp=root/'package.json'; html=root/'index.html'
s=main.read_text(encoding='utf-8')
h=html.read_text(encoding='utf-8')

s=s.replace("const VERSION='0.6.3';","const VERSION='0.6.4';",1)

# Multi-Mac Claude credential discovery. Keep the successful v0.6.0 OAuth usage path,
# but discover credentials the way different Claude Code/macOS installations actually store them.
new_candidates=r'''function shellEnvValue(name){
  try{
    const safe=String(name).replace(/[^A-Z0-9_]/g,'');
    if(!safe)return null;
    return String(execFileSync('/bin/zsh',['-lic',`printf %s \"\${${safe}:-}\"`],{encoding:'utf8',timeout:4000,stdio:['ignore','pipe','pipe']})).trim()||null;
  }catch{return null}
}
function findClaudeExecutable(){
  const found=[];
  const add=p=>{if(p&&!found.includes(p)){try{if(fs.statSync(p).isFile())found.push(p)}catch{}}};
  try{add(shellClaudeProbe().claudePath)}catch{}
  add(path.join(os.homedir(),'.local','bin','claude'));
  add('/opt/homebrew/bin/claude');
  add('/usr/local/bin/claude');
  try{
    const base=path.join(os.homedir(),'Library','Application Support','Claude','claude-code');
    const names=fs.readdirSync(base).sort((a,b)=>b.localeCompare(a,undefined,{numeric:true}));
    for(const name of names)add(path.join(base,name,'claude.app','Contents','MacOS','claude'));
  }catch{}
  return found[0]||null;
}
function readClaudeAuthStatus(){
  try{
    const claude=findClaudeExecutable();
    if(!claude)return null;
    const raw=String(execFileSync(claude,['auth','status','--json'],{encoding:'utf8',timeout:12000,stdio:['ignore','pipe','pipe']}));
    const j=JSON.parse(raw);return {...j,claudePath:claude};
  }catch{return null}
}
function keychainRead(service,account=null){
  const args=['find-generic-password','-s',service];
  if(account)args.push('-a',account);
  args.push('-w');
  return String(execFileSync('/usr/bin/security',args,{encoding:'utf8',timeout:20000,stdio:['ignore','pipe','pipe']}));
}
function keychainServiceNames(){
  const names=['Claude Code-credentials'];
  try{
    const out=String(execFileSync('/usr/bin/security',['dump-keychain'],{encoding:'utf8',timeout:12000,stdio:['ignore','pipe','pipe']}));
    const re=/\"svce\"<blob>=\"(Claude Code-credentials[^\"]*)\"/g;let m;
    while((m=re.exec(out))){if(m[1]&&!names.includes(m[1]))names.push(m[1]);}
  }catch{}
  return names;
}
function hasClaudeSafeStorage(){
  try{execFileSync('/usr/bin/security',['find-generic-password','-s','Claude Safe Storage','-a','Claude Key'],{encoding:'utf8',timeout:8000,stdio:['ignore','pipe','pipe']});return true}catch{return false}
}
function readClaudeOauthCandidates(){
  const probe=shellClaudeProbe();
  const items=[],seenFiles=new Set(),seenTokens=new Set(),errors=[];
  const addRaw=(raw,source)=>{
    if(!raw||!String(raw).trim())return;
    let parsed=parseClaudeAccessToken(raw);
    if(!parsed?.accessToken && /^sk-ant-/i.test(String(raw).trim()))parsed={accessToken:String(raw).trim(),subscriptionType:null,rateLimitTier:null,expiresAt:null};
    if(!parsed?.accessToken)return;
    if(seenTokens.has(parsed.accessToken))return;seenTokens.add(parsed.accessToken);
    items.push({...parsed,credentialSource:source});
  };
  const addFile=file=>{
    if(!file)return;file=path.resolve(file);if(seenFiles.has(file))return;seenFiles.add(file);
    try{addRaw(fs.readFileSync(file,'utf8'),file)}catch{}
  };

  // Official Claude Code auth precedence includes CLAUDE_CODE_OAUTH_TOKEN.
  if(process.env.CLAUDE_CODE_OAUTH_TOKEN)addRaw(process.env.CLAUDE_CODE_OAUTH_TOKEN,'CLAUDE_CODE_OAUTH_TOKEN (app env)');
  const shellToken=shellEnvValue('CLAUDE_CODE_OAUTH_TOKEN');
  if(shellToken)addRaw(shellToken,'CLAUDE_CODE_OAUTH_TOKEN (login shell)');

  // Config-dir and default file fallbacks.
  if(process.env.CLAUDE_CONFIG_DIR)addFile(path.join(process.env.CLAUDE_CONFIG_DIR,'.credentials.json'));
  if(probe.configDir)addFile(path.join(probe.configDir,'.credentials.json'));
  const shellCfg=shellEnvValue('CLAUDE_CONFIG_DIR');if(shellCfg)addFile(path.join(shellCfg,'.credentials.json'));
  addFile(path.join(os.homedir(),'.claude','.credentials.json'));

  // Current and older Claude Code builds may key the service by the OS account,
  // and some builds create suffixed secondary-session services.
  if(process.platform==='darwin'){
    const accounts=[];
    try{accounts.push(os.userInfo().username)}catch{}
    if(process.env.USER)accounts.push(process.env.USER);
    const who=shellEnvValue('USER');if(who)accounts.push(who);
    for(const service of keychainServiceNames()){
      for(const account of [...new Set(accounts.filter(Boolean)),null]){
        try{addRaw(keychainRead(service,account),`macOS Keychain: ${service}${account?' / '+account:''}`)}catch(e){
          const msg=String(e.stderr||e.message||e).trim();if(msg&&!errors.includes(msg))errors.push(msg.slice(0,180));
        }
      }
    }
  }

  const authStatus=readClaudeAuthStatus();
  const legacySafeStorage=process.platform==='darwin'&&hasClaudeSafeStorage();
  if(!items.length){
    if(authStatus?.loggedIn){
      const extra=legacySafeStorage?' 이 Mac은 Claude Safe Storage 방식도 감지됐습니다.':'';
      throw new Error('Claude Code 로그인은 확인됐지만 사용량 조회용 OAuth 자격증명을 직접 찾지 못했습니다.'+extra+' 아래 “Claude 사용량 다시 연결”을 눌러 이 Mac의 Claude Code 로그인을 새 형식으로 갱신하세요.');
    }
    throw new Error('이 Mac에서 Claude Code 구독 로그인을 찾지 못했습니다. 아래 “Claude 사용량 다시 연결”을 눌러 Claude Code에 로그인하세요.');
  }
  return {items,probe,authStatus,legacySafeStorage};
}
'''

s,n=re.subn(r"function readClaudeOauthCandidates\(\)\{.*?\n\}\n(?=function claudeHttpJson)",lambda _m:new_candidates,s,count=1,flags=re.S)
if n!=1: raise SystemExit('readClaudeOauthCandidates block not found')

# Refresh should prefer the auth status already discovered, but keep candidate failover.
s=s.replace("    const authStatus=readClaudeAuthStatus();\n    const ua='claude-code/'+(discovered.probe.claudeVersion||'2.1.0');","    const authStatus=discovered.authStatus||readClaudeAuthStatus();\n    const ua='claude-code/'+(discovered.probe.claudeVersion||'2.1.0');",1)

# One-click per-Mac recovery: open the official Claude Code login in Terminal, then rescan.
new_install=r'''function launchClaudeLogin(){
  const claude=findClaudeExecutable();
  if(!claude)throw new Error('Claude Code 실행 파일을 찾지 못했습니다. 먼저 이 Mac에 Claude Code를 설치하거나 Claude 앱의 Code 기능을 한 번 실행하세요.');
  const q="'"+claude.replace(/'/g,"'\\''")+"'";
  const cmd=q+' auth login';
  const script='tell application "Terminal"\nactivate\ndo script '+JSON.stringify(cmd)+'\nend tell';
  execFileSync('/usr/bin/osascript',['-e',script],{encoding:'utf8',timeout:10000,stdio:['ignore','pipe','pipe']});
  return claude;
}
function scheduleClaudeReconnectChecks(){
  for(const ms of [7000,15000,30000,60000,120000])setTimeout(()=>refreshClaude(true),ms);
}
function installClaudeIntegration(){
  try{
    const d=readClaudeOauthCandidates();
    if(d.items.length){state.claudeError='이 Mac의 Claude Code 로그인 '+d.items.length+'개를 찾았습니다. 사용량을 다시 확인합니다.';updateUi();refreshClaude(true);return}
  }catch{}
  try{
    launchClaudeLogin();
    state.claudeError='Claude Code 공식 로그인 창을 열었습니다. 브라우저 로그인을 완료하면 이 앱이 자동으로 다시 확인합니다.';
    updateUi();scheduleClaudeReconnectChecks();
  }catch(e){state.claudeError='Claude 연결 복구 실패: '+String(e.message||e);updateUi()}
}
function uninstallClaudeIntegration(){state.claudeError='Claude 직접 조회 방식은 별도 설치 항목이 없습니다.';updateUi()}
'''
s,n=re.subn(r"function installClaudeIntegration\(\)\{.*?\n\}\nfunction uninstallClaudeIntegration\(\)\{.*?\n\}\n",lambda _m:new_install,s,count=1,flags=re.S)
if n!=1: raise SystemExit('installClaudeIntegration block not found')

# Better user-facing explanation for multi-Mac behavior.
h=h.replace('Claude Code의 기존 OAuth를 자격증명 파일과 macOS Keychain에서 모두 확인합니다. Max 요금제는 주간 전체와 Fable만 표시합니다.','각 Mac의 Claude Code 로그인을 독립적으로 자동 탐색합니다. 자격증명 파일, CLAUDE_CONFIG_DIR, macOS Keychain의 기본/계정별/보조 세션 항목을 확인합니다. 다른 Mac에서 자동 인식되지 않으면 “Claude 사용량 다시 연결”을 눌러 그 Mac에서 공식 Claude Code 로그인만 완료하세요.')

main.write_text(s,encoding='utf-8');html.write_text(h,encoding='utf-8')
pkg=json.loads(pkgp.read_text(encoding='utf-8'));pkg['version']='0.6.4';pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkgp.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

assert 'Claude Code-credentials' in s
assert 'dump-keychain' in s
assert 'CLAUDE_CODE_OAUTH_TOKEN' in s
assert 'auth login' in s
assert 'Claude Safe Storage' in s
assert "const VERSION='0.6.4'" in s
print('v0.6.4 multi-Mac Claude discovery patch applied')
