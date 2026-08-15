#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SRC = Path(os.environ.get('BATCH_ROOT', 'downloaded_batches'))
OUT = Path(os.environ.get('FINAL_DIR', 'final'))
EXPECTED = int(os.environ.get('EXPECTED_COUNT', '351'))


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def to_int(value: Any) -> int:
    try:
        return int(float(str(value or '0').replace(',', '')))
    except Exception:
        return 0


def to_float(value: Any) -> float:
    try:
        return float(str(value or '0').replace(',', ''))
    except Exception:
        return 0.0


def copy_tree_contents(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for path in src.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    csv_files = sorted(SRC.rglob('01_longform_video_analysis.csv'))
    if not csv_files:
        raise SystemExit('No batch CSV files found')

    by_id: dict[str, dict[str, str]] = {}
    fieldnames: list[str] = []
    field_seen: set[str] = set()
    error_entries: list[dict[str, Any]] = []
    batch_summaries: list[dict[str, Any]] = []

    for csv_file in csv_files:
        for row in read_rows(csv_file):
            vid = str(row.get('video_id') or '').strip()
            if not vid:
                continue
            by_id[vid] = row
            for key in row:
                if key not in field_seen:
                    field_seen.add(key)
                    fieldnames.append(key)
        batch_dir = csv_file.parent
        for err_file in batch_dir.glob('99_errors.json'):
            try:
                data = json.loads(err_file.read_text(encoding='utf-8'))
                if isinstance(data, list):
                    error_entries.extend(data)
            except Exception as exc:
                error_entries.append({'video_id': '', 'error': f'Could not parse {err_file}: {exc}'})
        for summary_file in batch_dir.glob('collection_summary.json'):
            try:
                batch_summaries.append(json.loads(summary_file.read_text(encoding='utf-8')))
            except Exception:
                pass
        copy_tree_contents(batch_dir / 'metadata', OUT / 'metadata')
        copy_tree_contents(batch_dir / 'transcripts', OUT / 'transcripts')
        copy_tree_contents(batch_dir / 'thumbnails', OUT / 'thumbnails')

    rows = list(by_id.values())
    rows.sort(key=lambda r: (str(r.get('upload_date') or ''), str(r.get('video_id') or '')), reverse=True)

    out_csv = OUT / '01_longform_video_analysis.csv'
    with out_csv.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    intent_counts = Counter(str(r.get('search_intent') or '미분류') for r in rows)
    topic_counts = Counter(str(r.get('primary_topic') or '미분류') for r in rows)
    transcript_success = sum(str(r.get('transcript_status')) == 'ok' for r in rows)
    ocr_success = sum(bool(str(r.get('thumbnail_ocr') or '').strip()) for r in rows)
    chapter_success = sum(to_int(r.get('chapter_count')) > 0 for r in rows)
    link_success = sum(to_int(r.get('description_url_count')) > 0 for r in rows)
    title_number = sum(str(r.get('title_has_number')).lower() in {'true', '1'} for r in rows)
    title_year = sum(str(r.get('title_has_year')).lower() in {'true', '1'} for r in rows)
    top_by_views = sorted(rows, key=lambda r: to_int(r.get('view_count')), reverse=True)[:30]
    top_by_velocity = sorted(rows, key=lambda r: to_float(r.get('views_per_day')), reverse=True)[:30]

    summary = {
        'channel_url': 'https://www.youtube.com/@TimSEOGuru/videos',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'expected_videos_tab_count': EXPECTED,
        'merged_unique_videos': len(rows),
        'coverage_pct': round(len(rows) / EXPECTED * 100, 2) if EXPECTED else 0,
        'batch_csv_files': len(csv_files),
        'batch_summaries': batch_summaries,
        'metadata_errors': len(error_entries),
        'transcript_success': transcript_success,
        'thumbnail_ocr_success': ocr_success,
        'videos_with_chapters': chapter_success,
        'videos_with_description_links': link_success,
        'titles_with_numbers': title_number,
        'titles_with_year': title_year,
        'search_intent_counts': dict(intent_counts.most_common()),
        'topic_counts': dict(topic_counts.most_common()),
    }
    (OUT / '00_collection_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / '99_errors.json').write_text(json.dumps(error_entries, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        '# Tim The SEO Guru 롱폼 SEO 전체 분석',
        '',
        f'- 대상: YouTube **Videos 탭 {EXPECTED}개** (Shorts 제외)',
        f'- 실제 통합: **{len(rows)}개 / {EXPECTED}개 ({summary["coverage_pct"]}%)**',
        f'- 공개 자막 확보: {transcript_success}개',
        f'- 썸네일 문구 OCR 확보: {ocr_success}개',
        f'- 챕터 사용: {chapter_success}개',
        f'- 설명란 링크 사용: {link_success}개',
        '',
        '## 채널 공통 제목 SEO 공식',
        '',
        f'- 숫자·금액·시간 등 구체성 신호를 넣은 제목: {title_number}개',
        f'- 연도·업데이트 시의성을 넣은 제목: {title_year}개',
        '- 제목 앞부분에 SEO·Google·Claude·AI·Backlink 등 핵심 주제를 두고, 뒤에는 결과·시간·수치·위험을 결합합니다.',
        '- “How I…”, “How to…”, “This…”, “Why…”, “Top N…”, “Google just…” 같은 반복 가능한 검색·후킹 프레임을 사용합니다.',
        '- 단순 정보형보다 “#1”, “24 hours”, “10X”, “1,000s”, “$10K/mo”, “INSANE”, “Do This”처럼 결과와 긴급성을 앞세웁니다.',
        '',
        '## 검색 의도 분포',
        '',
    ]
    for key, count in intent_counts.most_common():
        lines.append(f'- {key}: {count}개')
    lines += ['', '## 핵심 주제 분포', '']
    for key, count in topic_counts.most_common(30):
        lines.append(f'- {key}: {count}개')
    lines += ['', '## 조회수 상위 30개', '']
    for r in top_by_views:
        lines.append(f"- **{r.get('title','')}** — {to_int(r.get('view_count')):,}회 / {r.get('search_intent','')} / {r.get('video_url','')}")
    lines += ['', '## 조회속도 상위 30개', '']
    for r in top_by_velocity:
        lines.append(f"- **{r.get('title','')}** — 일평균 {to_float(r.get('views_per_day')):,.2f}회 / {r.get('video_url','')}")
    lines += [
        '',
        '## MyVision 적용 원칙',
        '',
        '- 한 영상은 하나의 검색 문제만 해결하고 제목 앞 40자 안에 핵심 키워드와 결과 약속을 함께 둡니다.',
        '- 썸네일은 제목 전체를 복사하지 않고 숫자·결과·위험·반전 중 하나만 크게 제시합니다.',
        '- 첫 30~60초에 문제 → 얻게 될 결과 → 실제 근거 순서로 말하고 제목 핵심어를 음성에서 재확인합니다.',
        '- 설명란 첫 3줄은 핵심 요약·키워드·단일 CTA, 이후 챕터·관련 영상·외부 링크 순으로 구성합니다.',
        '- 같은 키워드 군집의 영상끼리 설명란, 고정댓글, 엔드스크린으로 연결해 주제 권위를 쌓습니다.',
        '',
        '## 영상별 상세',
        '',
    ]
    for r in rows:
        lines += [
            f"### {r.get('title','')}",
            f"- URL: {r.get('video_url','')}",
            f"- 게시일/길이/조회수: {r.get('upload_date','')} / {r.get('duration','')} / {to_int(r.get('view_count')):,}",
            f"- 검색 의도·주제: {r.get('search_intent','')} / {r.get('primary_topic','')}",
            f"- 제목 전략: {r.get('title_strategy','')}",
            f"- 썸네일 전략: {r.get('thumbnail_strategy','')}",
            f"- 초반 훅: {r.get('hook_formula','')}",
            f"- CTA: {r.get('cta_pattern','')}",
            f"- 강점: {r.get('seo_strengths','')}",
            f"- 보완점: {r.get('seo_weaknesses','')}",
            f"- MyVision 적용: {r.get('apply_to_myvision','')}",
            '',
        ]
    (OUT / '02_channel_and_video_report.md').write_text('\n'.join(lines), encoding='utf-8')

    print(f'MERGED_ROWS={len(rows)} EXPECTED={EXPECTED} BATCH_CSV={len(csv_files)} ERRORS={len(error_entries)}')
    return 0 if rows else 2


if __name__ == '__main__':
    raise SystemExit(main())
