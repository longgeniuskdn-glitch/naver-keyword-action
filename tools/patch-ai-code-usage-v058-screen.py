from pathlib import Path
import json, re

root = Path('/tmp/src/src/desktop')
main = root / 'main.js'
core = root / 'usage-core.js'
pkgp = root / 'package.json'

s = main.read_text()
s = s.replace("const VERSION='0.5.7';", "const VERSION='0.5.8';", 1)
s = s.replace(
    "const {normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache, parseClaudeUsageText} = require('./usage-core');",
    "const {normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache, parseClaudeUsageText, stripClaudeTerminalText, parseClaudeCacheDeep} = require('./usage-core');",
    1,
)
# Keep a local diagnostic of the hidden /usage screen only. This contains no auth token.
s = s.replace(
    "const raw=await captureClaudeUsageTui();\n      const parsed=parseClaudeUsageText(raw,Date.now());",
    "const raw=await captureClaudeUsageTui();\n      try{fs.mkdirSync(claudeDir(),{recursive:true});fs.writeFileSync(path.join(claudeDir(),'claude-usage-last.txt'),stripClaudeTerminalText(raw).slice(-120000))}catch{}\n      const parsed=parseClaudeUsageText(raw,Date.now());",
    1,
)
# Add deep cache fallback after the existing cache parser.
s = s.replace(
    "const cached=parseClaudeCache(cacheRoot,cacheTime);\n    if(cached&&(cached.fiveHour||cached.sevenDay))return {data:cached,error:null};",
    "let cached=parseClaudeCache(cacheRoot,cacheTime);\n    if(!(cached&&(cached.fiveHour||cached.sevenDay)))cached=parseClaudeCacheDeep(cacheRoot,cacheTime);\n    if(cached&&(cached.fiveHour||cached.sevenDay))return {data:cached,error:null};",
    1,
)
main.write_text(s)

c = core.read_text()
# Replace v0.5.7 terminal stripping/parser block with a VT-aware parser that keeps the best usage-screen frame.
pat = r"function stripClaudeTerminalText\(text\) \{.*?\nfunction parseClaudeUsageText\(text, capturedAt = Date\.now\(\)\) \{.*?\n\}\n"
replacement = r'''function stripClaudeTerminalText(text) {
  let s=String(text||'');
  s=s.replace(/\u001b\][\s\S]*?(?:\u0007|\u001b\\)/g,' ');
  s=s.replace(/\u001b\[[0-9;?<>]*[ -/]*[@-~]/g,' ');
  s=s.replace(/\u001b[()][A-Za-z0-9]/g,' ');
  s=s.replace(/\r/g,'\n');
  for(let i=0;i<20&&s.includes('\b');i++)s=s.replace(/[^\b]\b/g,'');
  s=s.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g,' ');
  return s.replace(/[ \t]+/g,' ').replace(/\n{3,}/g,'\n\n');
}

function claudeUsageFromPlainText(text, capturedAt = Date.now()) {
  const s=String(text||'');
  const clamp=(n)=>Math.max(0,Math.min(100,Number(n)));
  const last=(re)=>{let v=null;for(const m of s.matchAll(re))v=clamp(m[1]);return v};
  let five=last(/Current\s+session[\s\S]{0,12000}?(\d{1,3})\s*%\s*(?:used)?/gi);
  let seven=last(/Current\s+week\s*\(all\s+models\)[\s\S]{0,12000}?(\d{1,3})\s*%\s*(?:used)?/gi);
  if(five==null)five=last(/Current\s+session\s*[:\-]?[\s\S]{0,4000}?(\d{1,3})\s*%/gi);
  if(seven==null)seven=last(/Current\s+week[^\n]{0,140}[\s\S]{0,6000}?(\d{1,3})\s*%/gi);
  if(five==null)five=last(/현재\s*세션[\s\S]{0,12000}?(\d{1,3})\s*%/gi);
  if(seven==null)seven=last(/현재\s*주[^\n]{0,140}[\s\S]{0,12000}?(\d{1,3})\s*%/gi);
  if(five==null||seven==null){
    const vals=[...s.matchAll(/(\d{1,3})\s*%\s*(?:used|사용)/gi)].map(m=>clamp(m[1]));
    if(five==null&&vals.length>0)five=vals[vals.length>=2?vals.length-2:0];
    if(seven==null&&vals.length>1)seven=vals[vals.length-1];
  }
  if(five==null&&seven==null)return null;
  return {service:'claude',fiveHour:five==null?null:{usedPercent:five,resetsAt:null},sevenDay:seven==null?null:{usedPercent:seven,resetsAt:null},updatedAt:Number(capturedAt)||Date.now(),source:'claude-interactive-usage'};
}

function reconstructAnsiFrames(input, rows=70, cols=220) {
  const text=String(input||'');
  let screen=Array.from({length:rows},()=>Array(cols).fill(' '));
  let r=0,c=0,savedR=0,savedC=0;
  const frames=[];
  const snapshot=()=>{
    const out=screen.map(line=>line.join('').replace(/\s+$/,'')).join('\n');
    if(/Current\s+session|현재\s*세션/i.test(out))frames.push(out);
  };
  const clearScreen=()=>{snapshot();screen=Array.from({length:rows},()=>Array(cols).fill(' '));r=0;c=0};
  const ensure=()=>{r=Math.max(0,Math.min(rows-1,r));c=Math.max(0,Math.min(cols-1,c))};
  let i=0,printed=0;
  while(i<text.length){
    const ch=text[i];
    if(ch==='\u001b'){
      if(text[i+1]==='['){
        let j=i+2;while(j<text.length&&!/[\x40-\x7e]/.test(text[j]))j++;
        if(j>=text.length)break;
        const fin=text[j], body=text.slice(i+2,j), nums=body.replace(/^[?<>=!]+/,'').split(';').filter(Boolean).map(x=>Number(x));
        const n=(k,d=1)=>Number.isFinite(nums[k])&&nums[k]!==0?nums[k]:d;
        if(fin==='A')r-=n(0); else if(fin==='B')r+=n(0); else if(fin==='C')c+=n(0); else if(fin==='D')c-=n(0);
        else if(fin==='E'){r+=n(0);c=0} else if(fin==='F'){r-=n(0);c=0} else if(fin==='G')c=n(0)-1;
        else if(fin==='H'||fin==='f'){r=n(0)-1;c=n(1)-1} else if(fin==='d')r=n(0)-1;
        else if(fin==='s'){savedR=r;savedC=c} else if(fin==='u'){r=savedR;c=savedC}
        else if(fin==='J'){
          const mode=nums[0]||0;
          if(mode===2||mode===3)clearScreen();
          else if(mode===0){for(let x=c;x<cols;x++)screen[r][x]=' ';for(let y=r+1;y<rows;y++)screen[y].fill(' ')}
          else if(mode===1){for(let x=0;x<=c;x++)screen[r][x]=' ';for(let y=0;y<r;y++)screen[y].fill(' ')}
        } else if(fin==='K'){
          const mode=nums[0]||0;if(mode===0)for(let x=c;x<cols;x++)screen[r][x]=' ';else if(mode===1)for(let x=0;x<=c;x++)screen[r][x]=' ';else if(mode===2)screen[r].fill(' ');
        }
        ensure();i=j+1;continue;
      }
      if(text[i+1]===']'){
        let j=i+2;while(j<text.length&&text[j]!=='\u0007'&&!(text[j]==='\u001b'&&text[j+1]==='\\'))j++;i=(text[j]==='\u001b'?j+2:j+1);continue;
      }
      if(text[i+1]==='7'){savedR=r;savedC=c;i+=2;continue} if(text[i+1]==='8'){r=savedR;c=savedC;i+=2;continue}
      i+=2;continue;
    }
    if(ch==='\r'){c=0;i++;continue}
    if(ch==='\n'){r++;c=0;if(r>=rows){screen.shift();screen.push(Array(cols).fill(' '));r=rows-1}snapshot();i++;continue}
    if(ch==='\b'){c=Math.max(0,c-1);i++;continue}
    const code=ch.charCodeAt(0);if(code<32||code===127){i++;continue}
    ensure();screen[r][c]=ch;c++;if(c>=cols){c=0;r++;if(r>=rows){screen.shift();screen.push(Array(cols).fill(' '));r=rows-1}}
    printed++;if(printed%600===0)snapshot();i++;
  }
  snapshot();
  return frames;
}

function parseClaudeUsageText(text, capturedAt = Date.now()) {
  // 1) Fast path: many Claude versions are parseable after simply removing ANSI codes.
  const plain=stripClaudeTerminalText(text);
  let parsed=claudeUsageFromPlainText(plain,capturedAt);
  if(parsed&&parsed.fiveHour&&parsed.sevenDay)return parsed;
  // 2) Claude's Ink TUI frequently moves the cursor and repaints. Rebuild visible screen frames.
  let best=parsed, bestScore=parsed?1:0;
  for(const frame of reconstructAnsiFrames(text)){
    const p=claudeUsageFromPlainText(frame,capturedAt);if(!p)continue;
    const score=(p.fiveHour?2:0)+(p.sevenDay?2:0)+(/Current\s+session/i.test(frame)?1:0)+(/Current\s+week/i.test(frame)?1:0);
    if(score>bestScore){best=p;bestScore=score}
    if(score>=6)break;
  }
  return best;
}

function parseClaudeCacheDeep(root, capturedAt = Date.now()) {
  let five=null, seven=null;
  const clamp=n=>Math.max(0,Math.min(100,Number(n)));
  const walk=(v,depth=0)=>{
    if(depth>12||v==null)return;
    if(Array.isArray(v)){for(const x of v)walk(x,depth+1);return}
    if(typeof v!=='object')return;
    const kind=String(v.kind||v.type||v.window||'').toLowerCase();
    const group=String(v.group||'').toLowerCase();
    const pct=v.percent??v.used_percentage??v.usedPercent??v.utilization??null;
    if(pct!=null&&Number.isFinite(Number(pct))){
      const n=clamp(pct), model=v.scope?.model??v.model??null;
      if(five==null&&(kind.includes('five')||kind.includes('5h')||kind.includes('session')))five={usedPercent:n,resetsAt:v.resets_at??v.resetsAt??null};
      if(seven==null&&(kind.includes('week')||group.includes('week'))&&(model==null||model?.id==null&&model?.display_name==null))seven={usedPercent:n,resetsAt:v.resets_at??v.resetsAt??null};
    }
    for(const x of Object.values(v))walk(x,depth+1);
  };
  walk(root);
  if(!five&&!seven)return null;
  return {service:'claude',fiveHour:five,sevenDay:seven,updatedAt:Number(capturedAt)||Date.now(),source:'claude-cache-deep'};
}
'''
c,n=re.subn(pat,lambda _m:replacement,c,count=1,flags=re.S)
if n!=1:
    raise SystemExit(f'v0.5.8 parser block replacement failed: {n}')
c=c.replace(
  "module.exports = { normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache, parseClaudeUsageText, stripClaudeTerminalText };",
  "module.exports = { normalizeCodex, normalizeClaude, shortValue, describeWindow, parseClaudeCache, parseClaudeUsageText, stripClaudeTerminalText, parseClaudeCacheDeep };",
  1,
)
core.write_text(c)

pkg=json.loads(pkgp.read_text());pkg['version']='0.5.8';pkg['build']['mac']['artifactName']='AI-Code-Usage-Mac-M4-v${version}.${ext}';pkgp.write_text(json.dumps(pkg,ensure_ascii=False,indent=2)+'\n')

# Tests include real cursor positioning/repaint rather than only linear text.
tdir=root/'test';tdir.mkdir(exist_ok=True)
(tdir/'claude-ansi-screen.test.js').write_text(r'''const test=require('node:test');
const assert=require('node:assert/strict');
const {parseClaudeUsageText,parseClaudeCacheDeep}=require('../usage-core');

test('reconstructs cursor-positioned Claude usage screen',()=>{
 const raw='\x1b[2J\x1b[4;3HCurrent session\x1b[5;45H42% used\x1b[8;3HCurrent week (all models)\x1b[9;45H17% used\x1b[12;1H';
 const d=parseClaudeUsageText(raw,99);assert.equal(d.fiveHour.usedPercent,42);assert.equal(d.sevenDay.usedPercent,17);assert.equal(d.updatedAt,99);
});

test('keeps a useful frame even if TUI clears before exit',()=>{
 const raw='\x1b[2J\x1b[2;1HCurrent session\x1b[3;20H61% used\x1b[5;1HCurrent week (all models)\x1b[6;20H28% used\x1b[2J\x1b[1;1HClaude Code ready';
 const d=parseClaudeUsageText(raw);assert.equal(d.fiveHour.usedPercent,61);assert.equal(d.sevenDay.usedPercent,28);
});

test('deep cache parses generic five-hour and weekly entries',()=>{
 const d=parseClaudeCacheDeep({cachedUsageUtilization:{limits:[{kind:'five_hour',percent:33,resets_at:'a'},{kind:'weekly',group:'weekly',percent:44,resets_at:'b',scope:{model:null}}]}});assert.equal(d.fiveHour.usedPercent,33);assert.equal(d.sevenDay.usedPercent,44);
});
''')
print('v0.5.8 ANSI screen parser patch applied')
