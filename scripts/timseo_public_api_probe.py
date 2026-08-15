#!/usr/bin/env python3
import json, re, sys
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

# Direct watch-page metadata extraction. Playback can be blocked while public metadata remains embedded.
try:
    wr=S.get(VIDEO_URL+'&hl=en',timeout=80)
    page=wr.text
    player=None
    for marker in ['var ytInitialPlayerResponse = ', 'ytInitialPlayerResponse = ', 'window["ytInitialPlayerResponse"] = ']:
        pos=page.find(marker)
        if pos>=0:
            start=page.find('{',pos+len(marker))
            try:
                player=json.JSONDecoder().raw_decode(page[start:])[0]
                break
            except Exception: pass
    if player is None:
        m=re.search(r'"playerResponse":"((?:\\.|[^"\\])*)"',page)
        if m:
            try:player=json.loads(json.loads('"'+m.group(1)+'"'))
            except Exception:pass
    vd=(player or {}).get('videoDetails') or {}
    micro=((player or {}).get('microformat') or {}).get('playerMicroformatRenderer') or {}
    meta={
      'status':wr.status_code,'bytes':len(wr.content),'player_found':bool(player),
      'playability':((player or {}).get('playabilityStatus') or {}).get('status'),
      'title':vd.get('title'),'description_len':len(vd.get('shortDescription') or ''),
      'description_preview':(vd.get('shortDescription') or '')[:500],
      'keywords_count':len(vd.get('keywords') or []),'keywords':(vd.get('keywords') or [])[:20],
      'lengthSeconds':vd.get('lengthSeconds'),'viewCount':vd.get('viewCount'),
      'publishDate':micro.get('publishDate'),'uploadDate':micro.get('uploadDate'),
      'category':micro.get('category'),'ownerChannelName':micro.get('ownerChannelName'),
    }
    results.append({'name':'youtube_watch_html','metadata':meta}); print('WATCH_META',json.dumps(meta,ensure_ascii=False))
except Exception as e:
    results.append({'name':'youtube_watch_html','error':f'{type(e).__name__}: {e}'}); print('WATCH_META_ERR',repr(e))

with open('public_api_probe.json','w',encoding='utf-8') as f:json.dump(results,f,ensure_ascii=False,indent=2)

ok = [x for x in results if (x.get('status') == 200 and x.get('bytes',0) > 100) or (x.get('name')=='youtube_watch_html' and x.get('metadata',{}).get('player_found'))]
print('USABLE_COUNT',len(ok),[x['name'] for x in ok])
if not ok:sys.exit(2)
