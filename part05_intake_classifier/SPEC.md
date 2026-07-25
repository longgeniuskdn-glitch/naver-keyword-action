# SPEC — 업무 접수·분류실 v1

## 문제

여러 채널의 문의와 업무가 흩어져 있으면 누락, 중복, 담당 혼선과 긴급도 오판이 생깁니다.

## v1 목표

- 외부 서비스 없이 로컬에서 접수·분류 흐름을 검증합니다.
- 여러 입력을 공통 업무 카드로 저장합니다.
- 유형, 긴급도, 담당, 위험과 처리 모드를 제안합니다.
- 사람이 분류를 승인하거나 보류합니다.
- 같은 항목을 두 번 접수하지 않습니다.
- 감사 로그와 백업·복구를 제공합니다.

## 입력

- channel
- sender
- subject
- body

## 자동 분류 결과

- category
- urgency: high / medium / low
- assigned_team
- risk_flags
- handling_mode: standard / prepare_only / human_only
- status

## 상태 흐름

```text
triaged → approved → done
       ↘ rejected
```

## v1에서 하지 않는 일

- Gmail, 카카오톡, Slack 등의 실제 계정 연결
- 자동 답장과 외부 발송
- 환불, 송금, 가격 변경
- 계약 확정과 법률 판단
- AI 자유 생성 답변
- 다중 사용자 SaaS

## 완료 기준

- 수동 접수와 CSV 가져오기
- 샘플 4건 분류
- 중복 차단
- 승인·보류·완료 상태
- CSV 내보내기
- SQLite 백업·복구
- 8개 자동 테스트
- Ubuntu Linux 새 환경 테스트
- Mac·Windows 실행기 제공
