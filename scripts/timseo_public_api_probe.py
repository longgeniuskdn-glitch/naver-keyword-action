#!/usr/bin/env python3
import json, sys
import requests

VIDEO_ID = 'v8KQk3YVG7w'
VIDEO_URL = f'https://www.youtube.com/watch?v={VIDEO_ID}'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36'
S = requests.Session()
S.headers.update({'User-Agent': UA, 'Accept': 'application/json,text/plain,text/vtt,*/*'})
results = []

def record(name, url, headers=None, timeout=50):
    try:
        r = S.get(url, headers=headers or {}, timeout=timeout)
        ct = r.headers.get('content-type','')
        body = r.text
        rec = {'name':name,'status':r.status_code,'content_type':ct,'bytes':len(r.content),'preview':body[:500]}
        try:
            data=r.json(); rec['json_keys']=list(data)[:30] if isinstance(data,dict) else []; rec['json_type']=type(data).__name__
            if isinstance(data,dict):
                for key in ['title','video_id','language','transcript','text','segments','success','error','message']:
                    if key in data:
                        val=data[key]; rec[key+'_summary']=len(val) if isinstance(val,(list,dict,str)) else val
        except Exception: pass
        results.append(rec); print('PROBE',json.dumps(rec,ensure_ascii=False))
        return r
    except Exception as e:
        rec={'name':name,'error':f'{type(e).__name__}: {e}'}; results.append(rec); print('PROBE',json.dumps(rec,ensure_ascii=False)); return None

record('khabaroff_json', f'https://youtubetranscribe.khabaroff.studio/transcript/{VIDEO_ID}')
record('khabaroff_txt', f'https://youtubetranscribe.khabaroff.studio/transcript/{VIDEO_ID}/txt')
record('khabaroff_vtt', f'https://youtubetranscribe.khabaroff.studio/transcript/{VIDEO_ID}/vtt')
record('transcriptapi_live', f'https://api.transcriptapi.io/transcript?video_id={VIDEO_ID}')
record('transcriptapi_channel', 'https://api.transcriptapi.io/channel/videos?channel_id=UCEYla_ISXZ0-Hd_htnsBn_g')

key_resp=record('youtube2text_demo_key','https://youtube2text.org/api/demo-key')
if key_resp is not None:
    try:key=key_resp.json().get('apiKey')
    except Exception:key=None
    if key:
        record('youtube2text_transcript',f'https://youtube2text.org/api/transcribe?url={VIDEO_URL}&maxChars=12000',headers={'x-api-key':key})

record('google_timedtext_manual',f'https://www.youtube.com/api/timedtext?v={VIDEO_ID}&lang=en&fmt=vtt')
record('google_timedtext_asr',f'https://www.youtube.com/api/timedtext?v={VIDEO_ID}&lang=en&kind=asr&fmt=vtt')

with open('public_api_probe.json','w',encoding='utf-8') as f:json.dump(results,f,ensure_ascii=False,indent=2)

ok = [x for x in results if x.get('status') == 200 and x.get('bytes',0) > 100]
print('USABLE_COUNT',len(ok),[x['name'] for x in ok])
if not ok:sys.exit(2)
