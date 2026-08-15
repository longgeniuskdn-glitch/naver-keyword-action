#!/usr/bin/env python3
import json, re, sys, time
from urllib.parse import urljoin
import requests

VIDEO_ID = 'v8KQk3YVG7w'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36'
S = requests.Session(); S.headers.update({'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*'})

bases = []
try:
    text = S.get('https://raw.githubusercontent.com/wiki/TeamPiped/Piped/Instances.md', timeout=20).text
    bases += re.findall(r'https://pipedapi[^\s|)]+', text)
except Exception as e:
    print('PIPED_LIST_ERROR', repr(e))
bases += [
    'https://pipedapi.kavin.rocks','https://pipedapi.tokhmi.xyz',
    'https://pipedapi.moomoo.me','https://pipedapi.syncpundit.io',
    'https://pipedapi.adminforge.de','https://pipedapi.reallyaweso.me',
    'https://pipedapi.leptons.xyz','https://pipedapi.r4fo.com',
]
bases = list(dict.fromkeys(x.rstrip('` ,./') for x in bases if x.startswith('https://')))
print('PIPED_CANDIDATES', len(bases))

piped_ok = []
for base in bases[:40]:
    try:
        r = S.get(f'{base}/streams/{VIDEO_ID}', timeout=12)
        ct = r.headers.get('content-type','')
        if r.status_code == 200 and 'json' in ct:
            d = r.json()
            if d.get('title'):
                subs = d.get('subtitles') or []
                sub_status = ''
                if subs:
                    try:
                        sr = S.get(subs[0].get('url',''), timeout=12)
                        sub_status = f"{sr.status_code}/{len(sr.content)}/{sr.headers.get('content-type','')}"
                    except Exception as e:
                        sub_status = 'ERR:'+repr(e)
                record = {
                    'base':base,'title':d.get('title'),'description_len':len(d.get('description') or ''),
                    'uploadDate':d.get('uploadDate'),'duration':d.get('duration'),'views':d.get('views'),
                    'likes':d.get('likes'),'subtitles':len(subs),'subtitle_fetch':sub_status,
                }
                piped_ok.append(record)
                print('PIPED_OK', json.dumps(record, ensure_ascii=False))
                if len(piped_ok) >= 5: break
        else:
            print('PIPED_FAIL', base, r.status_code, ct, len(r.content))
    except Exception as e:
        print('PIPED_ERR', base, type(e).__name__, str(e)[:160])

print('PIPED_SUCCESS_COUNT', len(piped_ok))

# Invidious fallback
instances = []
try:
    r = S.get('https://api.invidious.io/instances.json?sort_by=health', timeout=20)
    for host, meta in r.json():
        if meta.get('api') and meta.get('type') == 'https':
            instances.append('https://' + host)
except Exception as e:
    print('INVIDIOUS_LIST_ERROR', repr(e))
instances += ['https://inv.nadeko.net','https://inv.thepixora.com','https://yewtu.be','https://invidious.nerdvpn.de']
instances = list(dict.fromkeys(instances))
print('INVIDIOUS_CANDIDATES', len(instances))
inv_ok=[]
for base in instances[:35]:
    try:
        r=S.get(f'{base}/api/v1/videos/{VIDEO_ID}',timeout=12)
        if r.status_code==200 and 'json' in r.headers.get('content-type',''):
            d=r.json(); cr=S.get(f'{base}/api/v1/captions/{VIDEO_ID}',timeout=12)
            caps=[]
            if cr.status_code==200:
                try:caps=cr.json().get('captions') or []
                except Exception:pass
            rec={'base':base,'title':d.get('title'),'description_len':len(d.get('description') or ''),'published':d.get('published'),'lengthSeconds':d.get('lengthSeconds'),'viewCount':d.get('viewCount'),'likeCount':d.get('likeCount'),'captions':len(caps)}
            inv_ok.append(rec); print('INVIDIOUS_OK',json.dumps(rec,ensure_ascii=False))
            if len(inv_ok)>=5:break
        else: print('INVIDIOUS_FAIL',base,r.status_code,r.headers.get('content-type',''),len(r.content))
    except Exception as e: print('INVIDIOUS_ERR',base,type(e).__name__,str(e)[:160])
print('INVIDIOUS_SUCCESS_COUNT',len(inv_ok))

PathOut = 'public_api_probe.json'
with open(PathOut,'w',encoding='utf-8') as f:json.dump({'piped':piped_ok,'invidious':inv_ok},f,ensure_ascii=False,indent=2)
if not piped_ok and not inv_ok: sys.exit(2)
