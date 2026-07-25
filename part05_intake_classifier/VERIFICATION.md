# VERIFICATION

## 검증 기준

- 기존 개발 데이터와 캐시를 사용하지 않습니다.
- Ubuntu Linux 새 작업 폴더에서 시작합니다.
- 외부 Python 패키지를 설치하지 않습니다.
- 자동 테스트, 사전 점검, 서버, HTTP 화면, 중복, CSV, 백업·복구를 분리해 확인합니다.

## 자동 검증 명령

```bash
python3 -m unittest -v test_unittest.py
python3 app.py --preflight
```

## 확인할 8개 테스트

1. 배송 문의 분류
2. 긴급 환불의 prepare_only 분류
3. 계약·법률의 human_only 분류
4. 동일 접수 중복 차단
5. CSV 가져오기와 중복 집계
6. 승인 상태와 감사 로그
7. 백업·복구와 CSV 내보내기
8. 로컬 서버 `/health`와 대시보드

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

## 검증 상태

- Linux 자동 검증: GitHub Actions 실행 후 기록
- Mac 실행기: 제공, 실제 사용자 macOS 첫 실행 확인 필요
- Windows 실행기: 제공, 실제 사용자 Windows 첫 실행 확인 필요
- 외부 이메일·문의폼: v1 범위에서 미연결
- 실제 외부 답장: 구현하지 않음

## 판매 가능한 완료선

- 8개 테스트 통과
- 사전 점검 `ready: true`
- `/health` 정상
- 대시보드 정상
- 중복 차단
- CSV 내보내기
- 백업 후 복구
- ZIP 안에 DB·캐시·비밀정보 없음
