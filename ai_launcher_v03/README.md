# 우리 회사 AI 운영실 v0.3

통합 런처 v0.2의 모듈 실행 기능 위에 공통 피드백·Markdown 규칙 승인 엔진을 추가한 버전입니다.

## 이번 버전에서 실제로 동작하는 기능

- PART 02~06을 선택해 수정 전 결과, 수정본, 수정 이유, 검토자를 저장
- 같은 모듈·규칙 키·수정 이유의 반복 횟수 계산
- 반복 후보를 `collecting`과 `pending`으로 구분
- 사람의 승인 전에는 업무 규칙 MD에 반영하지 않음
- 승인 시 모듈별 MD 파일에 규칙과 근거를 기록
- 같은 규칙 키의 기존 활성 규칙과 충돌하면 적용 중단
- 명시적 충돌 덮어쓰기 승인
- 승인 규칙 롤백과 이전 MD 내용 복구
- 회사 공통 MD와 모듈별 MD의 버전·승인자·해시 레지스트리
- 첫 10건의 수정 이유, 검토 시간, 평균 검토 시간 자동 기록
- 피드백·승인·거절·충돌·롤백 감사 로그

## 저장 위치

```text
runtime/feedback.db
memory/
├─ common/
│  ├─ COMPANY_PROFILE.md
│  ├─ APPROVAL_POLICY.md
│  └─ AI_WORK_RULES.md
└─ modules/
   ├─ part02-threads/
   ├─ part03-blog/
   ├─ part04-ai-diagnosis/
   ├─ part05-work-intake/
   └─ part06-knowledge-vault/
```

개별 사건과 수정 이력은 SQLite에 저장하고, 반복 가치가 있는 승인 규칙만 MD에 반영합니다.

## 실행

저장소에서 개발 실행:

```bash
python ai_launcher_v03/launcher.py
```

통합 ZIP에서는 기존 `START_MAC.command`, `START_WINDOWS.bat`, `START_LINUX.sh`를 사용합니다.

## 안전 경계

계약, 법률, 결제, 환불, 개인정보, 보안, 대외 공개 답변은 `protected` 후보로 표시합니다. 후보가 많이 쌓여도 자동 승인하지 않습니다. 규칙 충돌도 자동 덮어쓰지 않습니다.

## 아직 포함하지 않은 범위

- 결과의 의미를 AI 모델이 해석하는 의미 기반 군집화
- PART 02·03 실행 프로그램 내부의 직접 피드백 버튼
- PART 04~06 각 업무 화면에서 현재 항목 ID를 자동 전달하는 연결
- 외부 서버 동기화와 다중 사용자 권한

현재 v0.3은 로컬 단일 사용자용 공통 엔진과 통합 승인 화면입니다. 다음 단계에서 PART 05 업무 상세 화면부터 직접 피드백 버튼을 연결합니다.
