#!/usr/bin/env python3
from __future__ import annotations
import csv, html, json, os, re, time, traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests, yt_dlp, pytesseract
from PIL import Image, ImageEnhance, ImageOps
try:
    from youtube_transcript_api import YouTubeTranscriptApi
except Exception:
    YouTubeTranscriptApi = None

URL=os.getenv('CHANNEL_URL','https://www.youtube.com/@TimSEOGuru/videos')
OUT=Path(os.getenv('OUTPUT_DIR','out'))
BATCH_TOTAL=max(1,int(os.getenv('BATCH_TOTAL','1')))
BATCH_INDEX=int(os.getenv('BATCH_INDEX','0'))
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36'
STOP=set('a an and are as at be by for from how i in is it my of on or that the this to with you your we what why when can will get use using into without not do does did'.split())


def clean(v:Any)->str:return re.sub(r'\s+',' ',html.unescape(str(v or ''))).strip()
def words(s:str)->list[str]:return [x.lower() for x in re.findall(r"[A-Za-z0-9][A-Za-z0-9+'-]*",s) if len(x)>1 and x.lower() not in STOP]
def num(v:Any)->int:
    try:return int(float(v or 0))
    except:return 0
def hms(v:Any)->str:
    s=num(v); h,r=divmod(s,3600); m,s=divmod(r,60); return f'{h}:{m:02}:{s:02}' if h else f'{m}:{s:02}'
def urls(s:str)->list[str]:return list(dict.fromkeys(re.findall(r'https?://[^\s<>()\[\]{}]+',s or '')))
def intent(t:str)->str:
    x=t.lower()
    if re.search(r'\b(vs|versus|comparison|better than|alternative)\b',x):return '비교·선택형'
    if re.search(r'\b(case study|results?|traffic|revenue|\$|visitors?|clicks?|from 0)\b',x):return '사례·성과형'
    if re.search(r'\b(mistake|avoid|warning|stop|never|wrong|dead|destroy|kill)\b',x):return '위험·반론형'
    if re.search(r'\b(best|top \d+|tools?|apps?|prompts?|hacks?)\b',x):return '목록·추천형'
    if re.search(r'\b(update|news|202[0-9]|new|latest|just)\b',x):return '업데이트·시의성형'
    if re.search(r'\b(how to|tutorial|step by step|guide|build|create|use|setup)\b',x):return '튜토리얼·문제해결형'
    return '전략·해설형'
def title_strategy(t:str)->str:
    x=t.lower(); a=[]
    if 'how to' in x or x.startswith('how i'):a.append('How-to/실행 검색어')
    if re.search(r'\d',t):a.append('숫자·시간·금액으로 구체화')
    if re.search(r'\b202[0-9]\b',t):a.append('연도·최신성 신호')
    if re.search(r'\b(best|top|free|secret|exact|insane|crazy|guaranteed|ultimate)\b',x):a.append('강한 효익·감정 단어')
    if re.search(r'\b(stop|never|wrong|dead|warning|destroy|kill|truth)\b',x):a.append('손실회피·반전')
    if '(' in t or '[' in t:a.append('괄호 속 추가 약속')
    return '; '.join(a or ['핵심 주제를 전면에 둔 직접형'])
def primary_topic(t:str,tags:list[str])->str:
    x=t.lower()
    for p in ['programmatic seo','local seo','technical seo','link building','backlinks','keyword research','youtube seo','ai seo','claude code','chatgpt','google maps','seo','automation','content']:
        if p in x:return p.title() if p!='seo' else 'SEO'
    return clean(tags[0]) if tags else (words(t)[0].title() if words(t) else 'SEO')
def top_terms(s:str,n=12)->str:return ', '.join(k for k,_ in Counter(words(s)).most_common(n))


def ydl_opts(flat=False)->dict[str,Any]:
    return {'quiet':True,'no_warnings':True,'skip_download':True,'ignoreerrors':True,
      'extract_flat':'in_playlist' if flat else False,'socket_timeout':40,'retries':4,
      'extractor_args':{'youtube':{'player_client':['web','android_vr'],'skip':['hls','dash','translated_subs']}}}
def list_videos()->list[dict[str,Any]]:
    with yt_dlp.YoutubeDL(ydl_opts(True)) as y:data=y.extract_info(URL,download=False) or {}
    out=[]; seen=set()
    for e in data.get('entries') or []:
        if e and e.get('id') and e['id'] not in seen:seen.add(e['id']);out.append(e)
    return out
def details(vid:str)->tuple[dict[str,Any],str]:
    try:
        with yt_dlp.YoutubeDL(ydl_opts()) as y:return y.extract_info(f'https://www.youtube.com/watch?v={vid}',download=False) or {},''
    except Exception as e:return {},f'{type(e).__name__}: {e}'


def captions(info:dict[str,Any],vid:str)->tuple[list[dict[str,Any]],str,str]:
    tracks=info.get('subtitles') or info.get('automatic_captions') or {}
    for lang in ['en','en-US','en-GB']+list(tracks):
        for tr in tracks.get(lang) or []:
            if tr.get('ext')!='json3' or not tr.get('url'):continue
            try:
                data=requests.get(tr['url'],headers={'User-Agent':UA},timeout=30).json(); out=[]
                for ev in data.get('events') or []:
                    text=clean(''.join(x.get('utf8','') for x in ev.get('segs') or []))
                    if text:out.append({'text':text,'start':(ev.get('tStartMs') or 0)/1000,'duration':(ev.get('dDurationMs') or 0)/1000})
                if out:return out,lang,'yt-dlp caption URL'
            except Exception:pass
    if YouTubeTranscriptApi:
        try:
            api=YouTubeTranscriptApi(); tl=api.list(vid); chosen=None
            try:chosen=tl.find_transcript(['en','en-US','en-GB'])
            except Exception:
                all_tracks=list(tl); chosen=all_tracks[0] if all_tracks else None
            if chosen:
                out=[]
                for x in chosen.fetch():
                    if hasattr(x,'text'):out.append({'text':clean(x.text),'start':float(x.start),'duration':float(x.duration)})
                    else:out.append({'text':clean(x.get('text')),'start':float(x.get('start',0)),'duration':float(x.get('duration',0))})
                if out:return out,getattr(chosen,'language_code',''),'youtube-transcript-api'
        except Exception as e:return [],'',f'{type(e).__name__}: {e}'
    return [],'','no public captions'


def thumbnail(info:dict[str,Any],vid:str)->tuple[str,str,str]:
    dest=OUT/'thumbnails'/f'{vid}.jpg'; err=''
    for u in [info.get('thumbnail'),f'https://i.ytimg.com/vi/{vid}/maxresdefault.jpg',f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg']:
        if not u:continue
        try:
            r=requests.get(u,headers={'User-Agent':UA},timeout=25); r.raise_for_status()
            if len(r.content)<2000:continue
            dest.write_bytes(r.content)
            with Image.open(dest) as im:
                im=im.convert('RGB'); scale=max(1,1400/max(im.width,1)); im=im.resize((int(im.width*scale),int(im.height*scale)))
                g=ImageEnhance.Contrast(ImageOps.grayscale(im)).enhance(2.1)
                text=clean(pytesseract.image_to_string(g,config='--psm 11',lang='eng'))[:400]
            return u,text,''
        except Exception as e:err=f'{type(e).__name__}: {e}'
    return '','',err


def make_row(flat:dict[str,Any],info:dict[str,Any],meta_err:str)->tuple[dict[str,Any],list[dict[str,Any]]]:
    vid=str(flat['id']); title=clean(info.get('title') or flat.get('title')); desc=str(info.get('description') or '')
    dur=num(info.get('duration') or flat.get('duration')); views=num(info.get('view_count') or flat.get('view_count')); likes=num(info.get('like_count'))
    date=clean(info.get('upload_date') or flat.get('upload_date')); date=f'{date[:4]}-{date[4:6]}-{date[6:]}' if len(date)==8 and date.isdigit() else date
    tags=[clean(x) for x in info.get('tags') or [] if clean(x)]; chapters=info.get('chapters') or []
    snips,lang,tr_src=captions(info,vid); full=clean(' '.join(x['text'] for x in snips)); first=clean(' '.join(x['text'] for x in snips if x['start']<60)); ending=full[-1800:]
    thumb_url,ocr,thumb_err=thumbnail(info,vid); durls=urls(desc); tks=words(title); oset=set(words(ocr)); tset=set(tks); overlap=round(len(oset&tset)/len(oset|tset),3) if oset and tset else 0
    hook=[]
    if re.search(r"\b(in this video|today|i'll show|i will show|you'll learn|we're going to)\b",first.lower()):hook.append('초반 결과 약속')
    if re.search(r'\b(problem|mistake|wrong|fail|traffic|rank|revenue|\$|thousand|million)\b',first.lower()):hook.append('문제·수치·증거 선제시')
    if any(w in first.lower() for w in tks[:5]):hook.append('제목 핵심어 음성 반복')
    strengths=[]; gaps=[]
    if len(title)<=70:strengths.append('검색결과 절단 위험 낮은 제목')
    if chapters:strengths.append('챕터로 구간 탐색 강화')
    if len(desc.split())>=80:strengths.append('설명란 문맥 충분')
    if snips:strengths.append('자막으로 주제 문맥 축적')
    if dur>=480 and not chapters:gaps.append('긴 영상인데 챕터 없음')
    if not snips:gaps.append('공개 자막 미확보')
    if not durls:gaps.append('설명란 전환 링크 미확인')
    return {
      'video_id':vid,'video_url':f'https://www.youtube.com/watch?v={vid}','title':title,'upload_date':date,'duration_seconds':dur,'duration':hms(dur),'view_count':views,'like_count':likes,
      'primary_topic':primary_topic(title,tags),'search_intent':intent(title),'title_chars':len(title),'title_words':len(title.split()),'title_has_number':bool(re.search(r'\d',title)),'title_has_year':bool(re.search(r'\b202[0-9]\b',title)),'title_strategy':title_strategy(title),
      'thumbnail_url':thumb_url,'thumbnail_file':f'thumbnails/{vid}.jpg','thumbnail_ocr':ocr,'thumbnail_words':len(words(ocr)),'thumbnail_title_overlap':overlap,'thumbnail_strategy':('짧은 대형 문구' if len(words(ocr))<=5 else '설명형 문구')+('; 제목과 다른 보조 후킹' if overlap<.25 else '; 제목 핵심어 반복'),
      'description_first_220':clean(desc)[:220],'description_words':len(desc.split()),'description_url_count':len(durls),'description_urls':'\n'.join(durls),'chapter_count':len(chapters),'chapter_titles':' | '.join(clean(x.get('title')) for x in chapters),'tag_count':len(tags),'tags':', '.join(tags),
      'transcript_status':'ok' if snips else 'missing','transcript_language':lang,'transcript_source':tr_src,'transcript_words':len(full.split()),'transcript_first_60s':first[:2200],'transcript_last_90s':ending,'transcript_top_terms':top_terms(full),'hook_formula':'; '.join(hook or ['자막 미확보 또는 배경설명형']),
      'cta_pattern':f"설명란 링크 {len(durls)}개; "+(', '.join(x for x in ['subscribe','comment','download','newsletter','course','link below','watch next'] if x in (desc+' '+ending).lower()) or '명시적 CTA 약함'),
      'seo_strengths':'; '.join(strengths or ['명확한 단일 주제']),'seo_weaknesses':'; '.join(gaps or ['큰 구조적 약점 미확인']),'apply_to_myvision':f"‘{primary_topic(title,tags)}’ 한 주제에 {intent(title)} 제목 적용; 첫 60초 문제→결과→증거; 설명란 첫 3줄 요약+단일 CTA",
      'metadata_error':meta_err,'transcript_error':'' if snips else tr_src,'thumbnail_error':thumb_err,
    },snips


def main()->int:
    for d in [OUT,OUT/'metadata',OUT/'transcripts',OUT/'thumbnails']:d.mkdir(parents=True,exist_ok=True)
    entries=list_videos(); assigned=entries[BATCH_INDEX::BATCH_TOTAL]
    print(f'[CHANNEL] {len(entries)} [BATCH] {BATCH_INDEX}/{BATCH_TOTAL} assigned={len(assigned)}',flush=True)
    (OUT/'00_flat_entries.json').write_text(json.dumps(assigned,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    rows=[]; errors=[]
    for i,e in enumerate(assigned,1):
        vid=str(e['id']); print(f'[{i}/{len(assigned)}] {vid}',flush=True)
        try:
            info,err=details(vid); row,snips=make_row(e,info,err); rows.append(row)
            keep={k:info.get(k) for k in ['id','title','description','duration','upload_date','view_count','like_count','tags','chapters','thumbnail','width','height','live_status','language']}
            (OUT/'metadata'/f'{vid}.json').write_text(json.dumps(keep,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            (OUT/'transcripts'/f'{vid}.json').write_text(json.dumps(snips,ensure_ascii=False,indent=2),encoding='utf-8')
            (OUT/'transcripts'/f'{vid}.txt').write_text(clean(' '.join(x['text'] for x in snips)),encoding='utf-8')
        except Exception as ex:errors.append({'video_id':vid,'error':f'{type(ex).__name__}: {ex}','traceback':traceback.format_exc()[-2500:]})
        time.sleep(.25)
    fields=list(rows[0]) if rows else []
    with (OUT/'01_longform_video_analysis.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,quoting=csv.QUOTE_ALL); w.writeheader(); w.writerows(rows)
    (OUT/'99_errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'collection_summary.json').write_text(json.dumps({'videos_tab_count':len(entries),'batch_index':BATCH_INDEX,'batch_total':BATCH_TOTAL,'assigned_count':len(assigned),'rows':len(rows),'errors':len(errors),'collected_utc':datetime.now(timezone.utc).isoformat()},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'[DONE] rows={len(rows)} errors={len(errors)}',flush=True); return 0
if __name__=='__main__':raise SystemExit(main())
