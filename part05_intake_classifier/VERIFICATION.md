# VERIFICATION

## 검증 기준

- 기존 개발 데이터와 캐시를 사용하지 않습니다.
- Ubuntu Linux 새 작업 폴더에서 시작합니다.
- 외부 Python 패키지를 설치하지 않습니다.
- 자동 테스트, 사전 점검, 서버, HTTP 화면, 중복, CSV, 백업·복구를 분리해 확인합니다.

## 검증 환경

- 검증일: 2026-07-26
- 운영체제: Ubuntu 24.04.4 LTS
- Python: 3.13
- GitHub Actions 성공 이력과 패키지 해시는 저장소의 해당 workflow run에서 확인합니다.
- 패키지 안에 고정 해시를 적지 않습니다. 문서 한 줄만 바뀌어도 ZIP 해시가 달라져 오래된 값이 될 수 있기 때문입니다.

## 자동 검증 명령

```bash
python3 -m unittest -v test_unittest.py
python3 app.py --preflight
```

## 확인한 8개 테스트

1. 배송 문의 분류
2. 긴급 환불의 prepare_only 분류
3. 계약·법률의 human_only 분류
4. 동일 접수 중복 차단
5. CSV 가져오기와 중복 집계
6. 승인 상태와 감사 로그
7. 백업·복구와 CSV 내보내기
8. 로컬 서버 `/health`와 대시보드

## 첫 Linux 실패와 수정

### 실패 1 — 계약 분쟁 오분류

- 실제 결과: `불만·분쟁`
- 기대 결과: `계약·법무`
- 원인: `분쟁` 키워드가 계약 키워드보다 먼저 평가됨
- 수정: 계약·법무 규칙을 일반 불만보다 먼저 평가
- 재검증: 통과

### 실패 2 — 백업 복구 후 0건

- 실제 결과: 백업 파일 복구 후 접수 항목 0건
- 원인: WAL 방식 SQLite를 단순 파일 복사해 최신 트랜잭션이 백업본에 포함되지 않음
- 수정: SQLite connection backup API로 백업·복구
- 재검증: 샘플 4건 백업, 원본 DB 삭제, 복구 후 4건 확인

## 최종 Linux 검증 결과

- 8개 자동 테스트: 통과
- 사전 점검 `ready: true`: 통과
- 로컬 서버 실행: 통과
- `/health`: 통과
- 대시보드 HTML: 통과
- 샘플 4건: 통과
- DB 백업·복구: 통과
- DB·캐시·pyc 제외 패키징: 통과
- Mac 실행 파일 executable 권한: 적용
- GitHub Actions artifact 생성: 통과

## Linux smoke test

```bash
rm -rf data output backups __pycache__
python3 -m unittest -v test_unittest.py
python3 app.py --preflight
python3 app.py --no-browser &
APP_PID=$!
sleep 2
curl --fail http://127.0.0.1:8795/health
curl --fail http://127.0.0.1:8795/ | grep "업무 접수·분류실"
kill $APP_PID
```

## 추가 확인이 필요한 범위

- Mac 실행기: 제공, 실제 사용자 macOS 첫 실행과 보안 경고 확인 필요
- Windows 실행기: 제공, 실제 사용자 Windows 첫 실행과 Python 설치 상태 확인 필요
- 외부 이메일·문의폼: v1 범위에서 미연결
- 실제 외부 답장: 구현하지 않음

## 판매 가능한 1차 완료선

- 8개 테스트 통과
- 사전 점검 `ready: true`
- `/health` 정상
- 대시보드 정상
- 중복 차단
- CSV 내보내기
- SQLite backup API 백업 후 복구
- ZIP 안에 DB·캐시·비밀정보 없음
