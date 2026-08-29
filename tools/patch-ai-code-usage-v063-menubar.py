from pathlib import Path
import json,re

root=Path('/tmp/src/src/desktop')
main=root/'main.js'; pkgp=root/'package.json'
s=main.read_text(encoding='utf-8')

s=s.replace("const VERSION='0.6.2';","const VERSION='0.6.3';",1)

new_label=r'''function remainingPercent(w){
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
s,n=re.subn(r"function menuPercent\(w\)\{.*?\n\}\nfunction menuUsage\(prefix,data\)\{.*?\n\}\nfunction label\(\)\{.*?\n\}\n",lambda _m:new_label,s,count=1,flags=re.S)
if n!=1: raise SystemExit('v0.6.2 menu block not found')

main.write_text(s,encoding='utf-8')
pkg=json.loads(pkgp.read_text(encoding='utf-8'));pkg['version']='0.6.3';pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkgp.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Static contract checks.
assert "CX : " in s
assert "CL 5H " in s
assert " / W " in s
assert ", F " in s
print('v0.6.3 remaining-percentage menu patch applied')
