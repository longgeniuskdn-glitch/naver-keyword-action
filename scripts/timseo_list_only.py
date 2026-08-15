import csv, json
from pathlib import Path
import yt_dlp

url = 'https://www.youtube.com/@TimSEOGuru/videos'
out = Path('out_list')
out.mkdir(exist_ok=True)
opts = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'extract_flat': 'in_playlist',
    'ignoreerrors': True,
    'socket_timeout': 30,
    'retries': 3,
    'extractor_args': {'youtube': {'player_client': ['web', 'android_vr']}},
}
with yt_dlp.YoutubeDL(opts) as ydl:
    data = ydl.extract_info(url, download=False)
entries = []
seen = set()
for e in (data or {}).get('entries') or []:
    if e and e.get('id') and e['id'] not in seen:
        seen.add(e['id'])
        entries.append({
            'video_id': e.get('id'),
            'title': e.get('title'),
            'url': e.get('url') or e.get('webpage_url') or f"https://www.youtube.com/watch?v={e.get('id')}",
            'duration': e.get('duration'),
            'view_count': e.get('view_count'),
            'upload_date': e.get('upload_date'),
        })
(out / 'videos_tab.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
with (out / 'videos_tab.csv').open('w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['video_id','title','url','duration','view_count','upload_date'])
    w.writeheader(); w.writerows(entries)
(out / 'count.txt').write_text(str(len(entries)), encoding='utf-8')
print(f'VIDEOS_TAB_COUNT={len(entries)}')
for i, e in enumerate(entries, 1):
    print(f"{i:04d}\t{e['video_id']}\t{e.get('title') or ''}")
