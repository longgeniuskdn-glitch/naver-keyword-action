# PART 05 업무 접수·분류실

외부 패키지 없이 Python 표준 라이브러리만으로 실행되는 로컬 웹앱입니다.

## 기능

- 수동 업무 접수
- CSV 붙여넣기 가져오기
- 키워드 기반 유형·긴급도·담당 분류
- 환불·결제·계약·법률·개인정보 위험 표시
- `분류 후 사람 승인 / AI 준비만 / 사람 직접 처리` 구분
- 같은 채널·보낸 사람·제목·본문의 중복 차단
- 승인·보류·완료 상태
- 감사 로그
- CSV 내보내기
- SQLite 백업·복구
- 8개 자동 테스트

## 요구 환경

- Python 3.10 이상
- 추가 pip 패키지 없음
- 브라우저

## 직접 실행

```bash
python3 app.py
```

주소: `http://127.0.0.1:8795`

## 데이터 위치

- `data/intake.db`: SQLite 데이터베이스
- `backups/`: 백업 DB
- 실제 외부 서비스 계정과 비밀번호는 저장하지 않음

## 안전 범위

이 앱은 업무를 접수하고 분류하는 데까지만 사용합니다. 메일 답장, 환불, 송금, 계약 확정, 법률 판단과 공개 게시를 자동 실행하지 않습니다.

## 프로젝트 구조

```text
part05_intake_classifier/
├── app.py
├── test_unittest.py
├── START_MAC.command
├── START_WINDOWS.bat
├── START_HERE.md
├── AI_CODING_GUIDE.md
├── AGENTS.md
├── SPEC.md
├── APPROVAL_POLICY.md
├── VERIFICATION.md
├── CHANGELOG.md
└── samples/sample_intakes.csv
```
