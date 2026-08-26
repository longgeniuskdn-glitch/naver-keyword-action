from pathlib import Path
import json, re

root = Path('/tmp/src/src/desktop')
p = root / 'main.js'
s = p.read_text()

needle = "  setTimeout(refreshAll,800);setInterval(()=>{refreshClaude();if(modeShows('codex'))codex.refresh();else updateUi()},60000);\napp.on('before-quit'"
repl = "  setTimeout(refreshAll,800);setInterval(()=>{refreshClaude();if(modeShows('codex'))codex.refresh();else updateUi()},60000);\n});\napp.on('before-quit'"
if needle in s:
    s = s.replace(needle, repl, 1)

s = s.replace("const {spawn} = require('child_process');", "const {spawn, execFileSync} = require('child_process');", 1)
s = s.replace("const VERSION='0.5.0';", "const VERSION='0.5.5';", 1)

new_block = r'''function readJsonSafe(file){try{return JSON.parse(fs.readFileSync(file,'utf8'))}catch{return {}}}
function shellClaudeProbe(){
  const fallback={configDir:null,claudePath:null,apiOverride:false,apiOverrideReasons:[]};
  if(process.platform!=='darwin')return fallback;
  try{
    const envText=String(execFileSync('/bin/zsh',['-lic','env'],{encoding:'utf8',timeout:5000,stdio:['ignore','pipe','pipe']}));
    const envMap={};
    for(const line of envText.split(/\r?\n/)){const i=line.indexOf('=');if(i>0)envMap[line.slice(0,i)]=line.slice(i+1)}
    let claudePath=null;try{claudePath=String(execFileSync('/bin/zsh',['-lic','command -v claude || true'],{encoding:'utf8',timeout:3000})).trim()||null}catch{}
    const keys=['ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL','CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY','CLAUDE_CODE_USE_MANTLE'];
    const reasons=keys.filter(k=>envMap[k]);
    return {configDir:(envMap.CLAUDE_CONFIG_DIR||'').trim()||null,claudePath,apiOverride:reasons.length>0,apiOverrideReasons:reasons};
  }catch{return fallback}
}
function claudeDir(){return path.join(os.homedir(),'.ai-code-usage')}
function claudeConfigDir(){const probe=shellClaudeProbe();return process.env.CLAUDE_CONFIG_DIR||probe.configDir||path.join(os.homedir(),'.claude')}
function claudeSettings(){return path.join(claudeConfigDir(),'settings.json')}
function claudeUsageFile(){return path.join(claudeDir(),'claude-usage.json')}
function claudeLogFile(){return path.join(claudeDir(),'claude-statusline.log')}
function claudeManagedBlockers(){
  const blockers=[];
  const managed=readJsonSafe('/Library/Application Support/ClaudeCode/managed-settings.json');
  if(managed.disableAllHooks===true)blockers.push('관리자 설정 disableAllHooks=true');
  try{const d='/Library/Application Support/ClaudeCode/managed-settings.d';for(const name of fs.readdirSync(d).filter(x=>x.endsWith('.json')).sort())if(readJsonSafe(path.join(d,name)).disableAllHooks===true)blockers.push(`관리 설정 ${name}: disableAllHooks=true`)}catch{}
  if(process.platform==='darwin'){try{const v=String(execFileSync('/usr/bin/defaults',['read','com.anthropic.claudecode','disableAllHooks'],{encoding:'utf8',timeout:2000})).trim();if(v==='1'||v.toLowerCase()==='true')blockers.push('macOS 관리 정책 disableAllHooks=true')}catch{}}
  return blockers;
}
function claudeDiagnostics(){
  const probe=shellClaudeProbe(),cfg=claudeConfigDir(),user=readJsonSafe(path.join(cfg,'settings.json')),blockers=[];
  if(user.disableAllHooks===true)blockers.push(`${path.join(cfg,'settings.json')}: disableAllHooks=true`);
  blockers.push(...claudeManagedBlockers());
  if(probe.apiOverride)blockers.push(`구독 외 인증/엔드포인트 활성화: ${probe.apiOverrideReasons.join(', ')}`);
  let lastInvocation=null;try{lastInvocation=fs.statSync(claudeLogFile()).mtimeMs}catch{}
  return {probe,configDir:cfg,settingsFile:path.join(cfg,'settings.json'),blockers,lastInvocation};
}
function claudeIntegrationStatus(){try{const d=claudeDiagnostics(),j=readJsonSafe(d.settingsFile);return {installed:!!j.statusLine&&String(j.statusLine.command||'').includes('.ai-code-usage'),command:j.statusLine?.command||null,...d}}catch{return {installed:false,command:null,blockers:[]}}}
function selfTestClaudeHelper(helper){
  const usage=claudeUsageFile();let old=null,had=false;try{old=fs.readFileSync(usage);had=true}catch{}
  try{const mock=JSON.stringify({version:'2.1.90',rate_limits:{five_hour:{used_percentage:23.5,resets_at:1738425600},seven_day:{used_percentage:41.2,resets_at:1738857600}}});const out=String(execFileSync(helper,[],{input:mock,encoding:'utf8',timeout:5000}));const j=readJsonSafe(usage);if(!out.includes('CL 5h 24%')||Number(j?.fiveHour?.usedPercent)!==23.5)throw new Error('Claude helper self-test mismatch');return true}
  finally{try{if(had)fs.writeFileSync(usage,old);else fs.unlinkSync(usage)}catch{}}
}
function installClaudeIntegration(){
  try{
    const d=claudeDiagnostics();fs.mkdirSync(claudeDir(),{recursive:true});fs.mkdirSync(d.configDir,{recursive:true});let current=readJsonSafe(d.settingsFile);
    if(current.statusLine&&!String(current.statusLine.command||'').includes('.ai-code-usage'))fs.writeFileSync(path.join(claudeDir(),'previous-statusLine.json'),JSON.stringify(current.statusLine,null,2));
    fs.writeFileSync(path.join(claudeDir(),'settings-before-ai-code-usage.json'),JSON.stringify(current,null,2));
    let command;
    if(process.platform==='win32'){
      const src=path.join(process.resourcesPath,'vendor','claude-statusline.ps1'),dst=path.join(claudeDir(),'claude-statusline.ps1');fs.copyFileSync(src,dst);command=`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${dst}"`;
    }else{
      const src=path.join(process.resourcesPath,'vendor','claude-capture-v055'),dst=path.join(claudeDir(),'claude-capture-v055');fs.copyFileSync(src,dst);fs.chmodSync(dst,0o755);selfTestClaudeHelper(dst);command=`"${dst}"`;
    }
    current.statusLine={type:'command',command,refreshInterval:30,padding:1};fs.writeFileSync(d.settingsFile,JSON.stringify(current,null,2));
    const after=claudeDiagnostics();
    state.claudeError=after.blockers.length?'Claude 연동 설치됨. 차단 요소: '+after.blockers.join(' / '):`Claude 연동 설치 완료. 설정: ${after.settingsFile} · Claude Code를 완전히 종료 후 다시 실행하고 메시지를 1회 보내세요.`;
  }catch(e){state.claudeError='Claude 연동 실패: '+e.message}
  updateUi();
}
function uninstallClaudeIntegration(){try{const d=claudeDiagnostics();let current=readJsonSafe(d.settingsFile),old=null;try{old=JSON.parse(fs.readFileSync(path.join(claudeDir(),'previous-statusLine.json'),'utf8'))}catch{};if(old)current.statusLine=old;else delete current.statusLine;fs.writeFileSync(d.settingsFile,JSON.stringify(current,null,2));state.claudeError='Claude 연동을 제거했습니다.'}catch(e){state.claudeError=e.message}updateUi()}
function refreshClaude(){
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

pattern=r"function claudeDir\(\)\{.*?async function refreshAll\(\)"
s,n=re.subn(pattern,lambda m:new_block+"async function refreshAll()",s,count=1,flags=re.S)
if n!=1: raise SystemExit(f'Claude block replacement failed: {n}')
p.write_text(s)

pkg_path=root/'package.json';pkg=json.loads(pkg_path.read_text());pkg['version']='0.5.5';pkg.setdefault('build',{})['afterPack']='scripts/afterPack.js';pkg['build'].setdefault('mac',{})['hardenedRuntime']=False;pkg['build']['mac']['gatekeeperAssess']=False;pkg['build']['mac']['target']=['dmg','zip'];pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkg['build'].setdefault('dmg',{})['sign']=False;pkg_path.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n')

scripts=root/'scripts';scripts.mkdir(exist_ok=True);(scripts/'afterPack.js').write_text("""'use strict';
const { execFileSync } = require('child_process');
const path = require('path');
module.exports = async function afterPack(context) {
  if (context.electronPlatformName !== 'darwin') return;
  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  execFileSync('/usr/bin/codesign', ['--force', '--deep', '--sign', '-', appPath], { stdio: 'inherit' });
};
""")
print('v0.5.5b patch applied')
