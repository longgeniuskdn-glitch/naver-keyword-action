from pathlib import Path
import json,re

root=Path('/tmp/src/src/desktop')
main=root/'main.js'; pkgp=root/'package.json'; html=root/'index.html'
s=main.read_text(encoding='utf-8')
h=html.read_text(encoding='utf-8')

s=s.replace("const VERSION='0.6.4';","const VERSION='0.6.5';",1)
if not re.search(r"const\s*\{[^}]*\bspawn\b[^}]*\}\s*=\s*require\(['\"]child_process['\"]\)",s):
    s="const {spawn}=require('child_process');\n"+s

new_login=r'''let claudeLoginChild=null;
let claudeLoginAttempt=0;
let claudeLoginMode=null;
let claudeFallbackTerminalWindowId=null;

function cancelClaudeLoginChild(){
  if(!claudeLoginChild)return;
  try{claudeLoginChild.kill('SIGTERM')}catch{}
  claudeLoginChild=null;
}
function closeClaudeFallbackTerminal(){
  const id=Number(claudeFallbackTerminalWindowId||0);
  claudeFallbackTerminalWindowId=null;
  if(!id)return;
  try{
    const script='tell application "Terminal"\nif exists (window id '+id+') then close (window id '+id+')\nend tell';
    execFileSync('/usr/bin/osascript',['-e',script],{encoding:'utf8',timeout:6000,stdio:['ignore','pipe','pipe']});
  }catch{}
}
function claudeCredentialsReady(){
  try{return readClaudeOauthCandidates().items.length>0}catch{return false}
}
function finishClaudeReconnect(attempt){
  if(attempt!==claudeLoginAttempt)return;
  cancelClaudeLoginChild();
  closeClaudeFallbackTerminal();
  claudeLoginMode=null;
  state.claudeError='Claude Code 로그인을 확인했습니다. 사용량을 다시 확인합니다.';
  updateUi();
  refreshClaude(true);
}
function launchClaudeLoginVisibleFallback(attempt){
  if(attempt!==claudeLoginAttempt||claudeLoginMode==='visible')return;
  cancelClaudeLoginChild();
  const claude=findClaudeExecutable();
  if(!claude)throw new Error('Claude Code 실행 파일을 찾지 못했습니다.');
  const q="'"+claude.replace(/'/g,"'\\''")+"'";
  const cmd=q+' auth login';
  const script='tell application "Terminal"\nset w to do script '+JSON.stringify(cmd)+'\nactivate\nreturn id of w\nend tell';
  const raw=String(execFileSync('/usr/bin/osascript',['-e',script],{encoding:'utf8',timeout:10000,stdio:['ignore','pipe','pipe']})).trim();
  const m=raw.match(/(\d+)/);claudeFallbackTerminalWindowId=m?Number(m[1]):null;
  claudeLoginMode='visible';
  state.claudeError='숨은 Claude 로그인이 자동 완료되지 않아 공식 터미널 로그인을 열었습니다. 로그인 성공을 확인하면 이 앱이 연 터미널 창만 자동으로 닫습니다.';
  updateUi();
}
function pollClaudeReconnect(attempt,deadline){
  if(attempt!==claudeLoginAttempt)return;
  if(claudeCredentialsReady()){finishClaudeReconnect(attempt);return}
  if(Date.now()>=deadline){
    if(claudeLoginMode==='hidden'){
      try{launchClaudeLoginVisibleFallback(attempt)}catch(e){state.claudeError='Claude 연결 복구 실패: '+String(e.message||e);updateUi();return}
      setTimeout(()=>pollClaudeReconnect(attempt,Date.now()+180000),3000);
      return;
    }
    state.claudeError='Claude 공식 로그인 완료를 아직 확인하지 못했습니다. 로그인 브라우저/터미널을 확인한 뒤 “Claude 사용량 다시 연결”을 다시 눌러주세요.';
    updateUi();return;
  }
  setTimeout(()=>pollClaudeReconnect(attempt,deadline),3000);
}
function launchClaudeLoginHidden(){
  const claude=findClaudeExecutable();
  if(!claude)throw new Error('Claude Code 실행 파일을 찾지 못했습니다. 먼저 이 Mac에 Claude Code를 설치하거나 Claude 앱의 Code 기능을 한 번 실행하세요.');
  claudeLoginAttempt+=1;const attempt=claudeLoginAttempt;
  cancelClaudeLoginChild();closeClaudeFallbackTerminal();claudeLoginMode='hidden';
  const child=spawn(claude,['auth','login'],{stdio:'ignore',env:{...process.env},windowsHide:true});
  claudeLoginChild=child;
  child.once('error',()=>{
    if(attempt!==claudeLoginAttempt||claudeLoginMode!=='hidden')return;
    try{launchClaudeLoginVisibleFallback(attempt)}catch(e){state.claudeError='Claude 연결 복구 실패: '+String(e.message||e);updateUi()}
  });
  child.once('exit',code=>{
    if(claudeLoginChild===child)claudeLoginChild=null;
    if(attempt!==claudeLoginAttempt)return;
    if(claudeCredentialsReady()){finishClaudeReconnect(attempt);return}
    if(code!==0&&claudeLoginMode==='hidden'){
      try{launchClaudeLoginVisibleFallback(attempt)}catch(e){state.claudeError='Claude 연결 복구 실패: '+String(e.message||e);updateUi()}
    }
  });
  state.claudeError='Claude Code 공식 로그인을 백그라운드에서 시작했습니다. 터미널은 띄우지 않고 로그인 브라우저만 사용합니다. 완료되면 자동으로 사용량을 다시 확인합니다.';
  updateUi();
  setTimeout(()=>pollClaudeReconnect(attempt,Date.now()+120000),2500);
  return claude;
}
function installClaudeIntegration(){
  try{
    const d=readClaudeOauthCandidates();
    if(d.items.length){state.claudeError='이 Mac의 Claude Code 로그인 '+d.items.length+'개를 찾았습니다. 사용량을 다시 확인합니다.';updateUi();refreshClaude(true);return}
  }catch{}
  try{launchClaudeLoginHidden()}
  catch(e){state.claudeError='Claude 연결 복구 실패: '+String(e.message||e);updateUi()}
}
function uninstallClaudeIntegration(){state.claudeError='Claude 직접 조회 방식은 별도 설치 항목이 없습니다.';updateUi()}
'''

pat=r"function launchClaudeLogin\(\)\{.*?\}\s*function scheduleClaudeReconnectChecks\(\)\{.*?\}\s*function installClaudeIntegration\(\)\{.*?\}\s*function uninstallClaudeIntegration\(\)\{.*?\}\s*"
s,n=re.subn(pat,lambda _m:new_login,s,count=1,flags=re.S)
if n!=1: raise SystemExit('v0.6.4 Claude login block not found')

h=h.replace('다른 Mac에서 자동 인식되지 않으면 “Claude 사용량 다시 연결”을 눌러 그 Mac에서 공식 Claude Code 로그인만 완료하세요.','다른 Mac에서 자동 인식되지 않으면 “Claude 사용량 다시 연결”을 누르세요. 공식 로그인은 기본적으로 터미널을 띄우지 않고 백그라운드에서 실행하며 로그인 브라우저만 열립니다. 자동 방식이 실패할 때만 터미널 fallback을 열고, 성공하면 앱이 연 그 창만 자동으로 닫습니다.')

main.write_text(s,encoding='utf-8');html.write_text(h,encoding='utf-8')
pkg=json.loads(pkgp.read_text(encoding='utf-8'));pkg['version']='0.6.5';pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkgp.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

assert "const VERSION='0.6.5'" in s
assert "spawn(claude,['auth','login']" in s
assert 'launchClaudeLoginVisibleFallback' in s
assert 'closeClaudeFallbackTerminal' in s
assert "claudeLoginMode='hidden'" in s
print('v0.6.5 hidden Claude login patch applied')
