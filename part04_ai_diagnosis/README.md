# PART 04｜AI 자동화 진단실

반복 업무를 입력해 시간·비용·규칙성·검수 난이도·위험도를 비교하고, 첫 자동화 후보와 안전한 운영 모드를 제안하는 로컬 앱입니다.

## 실행

### Mac
`START_MAC.command`를 더블클릭합니다.

### Windows
`START_WINDOWS.bat`를 더블클릭합니다.

### Linux
```bash
python3 app.py
```

브라우저 주소: `http://127.0.0.1:8794`

## 기능
- 반복 업무 등록
- 우선순위와 월간 가치 가정 계산
- 사람 승인선 자동 분류
- 첫 프로젝트 승인
- TASK_BRIEF.md 생성
- CSV 내보내기
- SQLite 백업·복구
- 중복 업무 차단

## 테스트
외부 패키지 없이 Python 표준 라이브러리만 사용합니다.

```bash
python3 -m unittest -v test_unittest.py
python3 app.py --preflight
```

## 운영 원칙
결제·계약·환불·삭제·법률·의료 판단은 사람 직접 처리로 분류합니다. 개인정보·공개 발행·가격·권한 변경은 AI가 준비만 하고 사람이 실행합니다.
