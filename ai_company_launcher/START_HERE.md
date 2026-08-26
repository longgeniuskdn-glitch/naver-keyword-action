# 우리 회사 AI 운영실｜통합 런처 MVP

## 현재 기능

- `module.json`을 가진 PART 자동 탐색
- 모듈 이름·버전·포트 표시
- 실행·종료·상태 확인
- 각 모듈 화면 열기
- 모듈별 실행 로그 저장
- 개별 PART 데이터베이스 분리 유지

## 사용 방법

### Mac

`START_MAC.command`를 더블클릭합니다.

### Windows

`START_WINDOWS.bat`를 더블클릭합니다.

### Linux

```bash
python3 -m unittest -v test_launcher.py
python3 launcher.py
```

## 모듈 설치

`modules` 폴더 아래에 PART 폴더를 넣습니다.

```text
ai_company_launcher/
├─ launcher.py
├─ modules/
│  ├─ part06_knowledge/
│  │  ├─ module.json
│  │  ├─ app.py
│  │  └─ ...
│  └─ 다른_PART/
└─ logs/
```

통합 배포판에는 PART 06이 `modules/part06_knowledge`에 포함됩니다.

## 이번 MVP에서 하지 않는 일

- 모든 PART 데이터베이스 통합
- 공통 승인 대기열
- 공통 고객 카드
- 통합 ROI 대시보드
- 라이선스와 결제 관리

위 기능은 모듈 실행 구조가 안정된 뒤 단계적으로 추가합니다.

## 완료 기준

- PART 06이 자동 탐색된다.
- 런처에서 PART 06을 실행할 수 있다.
- 상태가 `정상 실행`으로 바뀐다.
- `화면 열기`로 PART 06 대시보드가 열린다.
- 런처에서 종료할 수 있다.
- 모듈 오류가 런처 전체를 종료시키지 않는다.
