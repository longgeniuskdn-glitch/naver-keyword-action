from pathlib import Path
import json, re

root = Path('/tmp/src/src/desktop')
p = root / 'main.js'
s = p.read_text()

# Keep the runtime fix that was required in v0.5.2+
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
    const script=[
      `printf '__AICODE_CFG__=%s\\n' "${CLAUDE_CONFIG_DIR:-}"`,
      `printf '__AICODE_CLAUDE__=%s\\n' "$(command -v claude 2>/dev/null || true)"`,
      `printf '__AICODE_APIKEY__=%s\\n' "${ANTHROPIC_API_KEY:+1}"`,
      `printf '__AICODE_AUTHTOKEN__=%s\\n' "${ANTHROPIC_AUTH_TOKEN:+1}"`,
      `printf '__AICODE_BASEURL__=%s\\n' "${ANTHROPIC_BASE_URL:+1}"`,
      `printf '__AICODE_BEDROCK__=%s\\n' "${CLAUDE_CODE_USE_BEDROCK:+1}"`,
      `printf '__AICODE_VERTEX__=%s\\n' "${CLAUDE_CODE_USE_VERTEX:+1}"`,
      `printf '__AICODE_FOUNDRY__=%s\\n' "${CLAUDE_CODE_USE_FOUNDRY:+1}"`,
      `printf '__AICODE_MANTLE__=%s\\n' "${CLAUDE_CODE_USE_MANTLE:+1}"`
    ].join(';');
    const out=String(execFileSync('/bin/zsh',['-lic',script],{encoding:'utf8',timeout:5000,stdio:['ignore','pipe','pipe']}));
    const map={};
    for(const line of out.split(/\\r?\\n/)){
      const m=line.match(/^__AICODE_([A-Z]+)__=(.*)$/);if(m)map[m[1]]=m[2];
    }
    const reasons=[];
    if(map.APIKEY==='1')reasons.push('ANTHROPIC_API_KEY');
    if(map.AUTHTOKEN==='1')reasons.push('ANTHROPIC_AUTH_TOKEN');
    if(map.BASEURL==='1')reasons.push('ANTHROPIC_BASE_URL');
    if(map.BEDROCK==='1')reasons.push('CLAUDE_CODE_USE_BEDROCK');
    if(map.VERTEX==='1')reasons.push('CLAUDE_CODE_USE_VERTEX');
    if(map.FOUNDRY==='1')reasons.push('CLAUDE_CODE_USE_FOUNDRY');
    if(map.MANTLE==='1')reasons.push('CLAUDE_CODE_USE_MANTLE');
    return {configDir:(map.CFG||'').trim()||null,claudePath:(map.CLAUDE||'').trim()||null,apiOverride:reasons.length>0,apiOverrideReasons:reasons};
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
  if(managed.disableAllHooks===true)blockers.push('관리자 설정에서 disableAllHooks=true');
  try{
    const d='/Library/Application Support/ClaudeCode/managed-settings.d';
    for(const name of fs.readdirSync(d).filter(x=>x.endsWith('.json')).sort())if(readJsonSafe(path.join(d,name)).disableAllHooks===true)blockers.push(`관리 설정 ${name}에서 disableAllHooks=true`);
  }catch{}
  if(process.platform==='darwin'){
    try{const v=String(execFileSync('/usr/bin/defaults',['read','com.anthropic.claudecode','disableAllHooks'],{encoding:'utf8',timeout:2000})).trim();if(v==='1'||v.toLowerCase()==='true')blockers.push('macOS 관리 정책에서 disableAllHooks=true')}catch{}
  }
  return blockers;
}
function claudeDiagnostics(){
  const probe=shellClaudeProbe();
  const cfg=claudeConfigDir();
  const user=readJsonSafe(path.join(cfg,'settings.json'));
  const blockers=[];
  if(user.disableAllHooks===true)blockers.push(`${path.join(cfg,'settings.json')} 에 disableAllHooks=true`);
  blockers.push(...claudeManagedBlockers());
  if(probe.apiOverride)blockers.push(`구독 대신 다른 인증/엔드포인트가 활성화됨: ${probe.apiOverrideReasons.join(', ')}`);
  let lastInvocation=null;
  try{lastInvocation=fs.statSync(claudeLogFile()).mtimeMs}catch{}
  return {probe,configDir:cfg,settingsFile:path.join(cfg,'settings.json'),blockers,lastInvocation};
}
function claudeIntegrationStatus(){
  try{const d=claudeDiagnostics();const s=readJsonSafe(d.settingsFile);return {installed:!!s.statusLine&&String(s.statusLine.command||'').includes('.ai-code-usage'),command:s.statusLine?.command||null,...d}}catch{return {installed:false,command:null,blockers:[]}}
}
function writeClaudeWrapper(wrapper,helper){
  const q=s=>String(s).replace(/'/g,"'\\''");
  const text=`#!/bin/zsh\nBASE='${q(claudeDir())}'\nHELPER='${q(helper)}'\nLOG="$BASE/claude-statusline.log"\nINPUT=$(cat)\nprintf '[%s] invoked chars=%s\\n' "$(date '+%Y-%m-%d %H:%M:%S')" "${'#'}INPUT" >> "$LOG"\nOUT=$(printf '%s' "$INPUT" | "$HELPER" 2>> "$LOG")\nRC=$?\nprintf '[%s] rc=%s\\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$RC" >> "$LOG"\n[ -n "$OUT" ] && printf '%s\\n' "$OUT"\nexit $RC\n`;
  fs.writeFileSync(wrapper,text,{mode:0o755});fs.chmodSync(wrapper,0o755);
}
function selfTestClaudeHelper(helper){
  const usage=claudeUsageFile();let old=null,had=false;
  try{old=fs.readFileSync(usage);had=true}catch{}
  try{
    const mock=JSON.stringify({version:'2.1.90',rate_limits:{five_hour:{used_percentage:23.5,resets_at:1738425600},seven_day:{used_percentage:41.2,resets_at:1738857600}}});
    const out=String(execFileSync(helper,[],{input:mock,encoding:'utf8',timeout:5000}));
    const j=readJsonSafe(usage);
    if(!out.includes('CL 5h 24%')||Number(j?.fiveHour?.usedPercent)!==23.5)throw new Error('helper self-test output mismatch');
    return true;
  }finally{
    try{if(had)fs.writeFileSync(usage,old);else fs.unlinkSync(usage)}catch{}
  }
}
function installClaudeIntegration(){
  try{
    const d=claudeDiagnostics();
    fs.mkdirSync(claudeDir(),{recursive:true});fs.mkdirSync(d.configDir,{recursive:true});
    let current=readJsonSafe(d.settingsFile);
    if(current.statusLine&&!String(current.statusLine.command||'').includes('.ai-code-usage'))fs.writeFileSync(path.join(claudeDir(),'previous-statusLine.json'),JSON.stringify(current.statusLine,null,2));
    fs.writeFileSync(path.join(claudeDir(),'settings-before-ai-code-usage.json'),JSON.stringify(current,null,2));
    let command;
    if(process.platform==='win32'){
      const src=path.join(process.resourcesPath,'vendor','claude-statusline.ps1'),dst=path.join(claudeDir(),'claude-statusline.ps1');fs.copyFileSync(src,dst);command=`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${dst}"`;
    }else{
      const src=path.join(process.resourcesPath,'vendor','claude-capture'),helper=path.join(claudeDir(),'claude-capture'),wrapper=path.join(claudeDir(),'claude-statusline-wrapper.sh');
      fs.copyFileSync(src,helper);fs.chmodSync(helper,0o755);writeClaudeWrapper(wrapper,helper);selfTestClaudeHelper(helper);command=`"${wrapper}"`;
    }
    current.statusLine={type:'command',command,refreshInterval:30,padding:1};
    fs.writeFileSync(d.settingsFile,JSON.stringify(current,null,2));
    const after=claudeDiagnostics();
    if(after.blockers.length)state.claudeError='Claude 연동은 설치됐지만 차단 요소가 있습니다: '+after.blockers.join(' / ');
    else state.claudeError=`Claude 연동 설치 완료 (${after.settingsFile}). Claude Code를 완전히 종료 후 다시 실행하고 메시지를 1회 보내세요.`;
  }catch(e){state.claudeError='Claude 연동 실패: '+e.message}
  updateUi();
}
function uninstallClaudeIntegration(){
  try{const d=claudeDiagnostics();let current=readJsonSafe(d.settingsFile);let old=null;try{old=JSON.parse(fs.readFileSync(path.join(claudeDir(),'previous-statusLine.json'),'utf8'))}catch{};if(old)current.statusLine=old;else delete current.statusLine;fs.writeFileSync(d.settingsFile,JSON.stringify(current,null,2));state.claudeError='Claude 연동을 제거했습니다.'}catch(e){state.claudeError=e.message}updateUi();
}
function refreshClaude(){
  const d=claudeDiagnostics();
  try{
    const raw=JSON.parse(fs.readFileSync(claudeUsageFile(),'utf8'));state.claude=normalizeClaude(raw);const age=Date.now()-state.claude.updatedAt;
    if(d.blockers.length)state.claudeError='Claude 진단: '+d.blockers.join(' / ');
    else if(age>15*60*1000)state.claudeError='Claude 값이 15분 이상 갱신되지 않았습니다. Claude Code를 다시 실행하고 메시지를 1회 보내세요.';
    else state.claudeError=null;
  }catch{
    state.claude=null;
    const integ=claudeIntegrationStatus();
    if(!integ.installed)state.claudeError=`Claude 연동이 설치되지 않았습니다. 현재 설정 경로: ${d.settingsFile}`;
    else if(d.blockers.length)state.claudeError='Claude 진단: '+d.blockers.join(' / ');
    else if(d.lastInvocation)state.claudeError='Claude statusLine은 실행됐지만 rate_limits가 아직 없습니다. Pro/Max 구독인지, 첫 API 응답이 끝났는지 확인하세요.';
    else state.claudeError='Claude statusLine 호출 기록이 없습니다. Claude Code를 완전히 종료 후 다시 실행하고 프로젝트 신뢰(Trust)를 승인하세요. 계속 안 되면 Claude Code에서 statusline skipped · restart to fix 알림을 확인하세요.';
  }
}
'''

pattern = r"function claudeDir\(\)\{.*?async function refreshAll\(\)"
ns, n = re.subn(pattern, new_block + "async function refreshAll()", s, count=1, flags=re.S)
if n != 1:
    raise SystemExit(f'Claude block replacement failed: {n}')
s = ns
p.write_text(s)

# v0.2-style mac packaging, current functionality retained.
pkg_path = root / 'package.json'
pkg = json.loads(pkg_path.read_text())
pkg['version'] = '0.5.5'
pkg.setdefault('build', {})['afterPack'] = 'scripts/afterPack.js'
pkg['build'].setdefault('mac', {})['hardenedRuntime'] = False
pkg['build']['mac']['gatekeeperAssess'] = False
pkg['build']['mac']['target'] = ['dmg','zip']
pkg['build'].setdefault('dmg', {})['sign'] = False
pkg['build']['mac']['artifactName'] = 'AI-Code-Usage-Mac-M4-v${version}.${ext}'
pkg_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + '\n')

scripts = root / 'scripts'
scripts.mkdir(exist_ok=True)
(scripts / 'afterPack.js').write_text("""'use strict';
const { execFileSync } = require('child_process');
const path = require('path');
module.exports = async function afterPack(context) {
  if (context.electronPlatformName !== 'darwin') return;
  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  execFileSync('/usr/bin/codesign', ['--force', '--deep', '--sign', '-', appPath], { stdio: 'inherit' });
};
""")

print('v0.5.5 Claude diagnostics patch applied')
