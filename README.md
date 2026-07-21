# NAVER 키워드 최신 신호 GPT Action

이 프로젝트는 글감을 고를 때 다음 세 자료를 한 번에 조회합니다.

1. **네이버 검색광고 API**: PC·모바일 월간 검색량, 클릭률, 경쟁도, 연관 키워드  
2. **NAVER API HUB 검색어 트렌드**: 최근 30~365일의 일간 상대지수와 7일·30일 변화율  
3. **NAVER API HUB 검색 API**: 블로그·뉴스 결과 수와 날짜순 상위 100개 문서의 최근 게시 흐름  

검색어 트렌드는 절대 검색량이 아니라 상대지수입니다. 검색광고의 월간 검색량도 초·분 단위 실시간 값이 아닙니다. 이 Action은 요청 시점마다 공식 API를 새로 호출해 가능한 최신 신호를 반환합니다.

## 1. 필요한 인증 정보 발급

### A. NAVER API HUB

네이버 클라우드 플랫폼 콘솔에서 다음 순서로 진행합니다.

1. `All Services`
2. `Application Services`
3. `NAVER API HUB`
4. `Application` 등록
5. 검색어 트렌드와 검색 API 권한 활성화
6. `인증 정보`에서 **Client ID**와 **Client Secret** 복사

이 프로젝트는 2026년 7월 종료되는 기존 네이버 개발자센터 API가 아니라, 새 NAVER API HUB 주소와 헤더를 사용합니다.

### B. 네이버 검색광고 API

네이버 광고주센터에서 다음 순서로 진행합니다.

1. 광고주센터 로그인
2. `도구`
3. `API 관리자`
4. API 라이선스 생성
5. **API Key(액세스 라이선스)**, **Secret Key**, **Customer ID** 확인

검색광고 API가 아직 준비되지 않아도 NAVER API HUB 데이터는 사용할 수 있습니다. 이 경우 월간 검색량과 광고 경쟁도만 `null`로 반환됩니다.

## 2. Vercel 배포

1. 이 폴더를 GitHub 저장소에 올립니다.
2. Vercel에서 `Add New > Project`로 저장소를 가져옵니다.
3. Framework Preset은 `Other`로 둡니다.
4. 아래 환경 변수를 등록합니다.

```text
ANALYZER_API_KEY=직접 만든 긴 임의 문자열
NAVER_HUB_CLIENT_ID=발급값
NAVER_HUB_CLIENT_SECRET=발급값
NAVER_SEARCHAD_API_KEY=발급값
NAVER_SEARCHAD_SECRET_KEY=발급값
NAVER_SEARCHAD_CUSTOMER_ID=발급값
```

5. 배포 후 아래 주소를 열어 설정 상태를 확인합니다.

```text
https://배포도메인.vercel.app/api/health
```

`ok: true`이면 NAVER API HUB와 Action 인증키가 준비된 상태입니다.

## 3. GPT Action 연결

1. `openapi.yaml`에서 다음 주소를 실제 배포 주소로 교체합니다.

```yaml
servers:
  - url: https://YOUR-VERCEL-DOMAIN.vercel.app
```

2. GPT 편집 화면에서 `Actions > Create new action`을 엽니다.
3. 수정한 `openapi.yaml` 내용을 붙여 넣습니다.
4. 인증 방식은 **API Key**를 선택합니다.
5. 인증 위치는 **Custom header**, 헤더 이름은 `X-Analyzer-Key`로 설정합니다.
6. API Key 값에는 Vercel의 `ANALYZER_API_KEY`와 같은 값을 입력합니다.
7. 테스트에서 `analyzeNaverKeywords`를 실행합니다.

공개 GPT로 배포한다면 개인정보 처리방침 주소로 다음 URL을 사용할 수 있습니다.

```text
https://배포도메인.vercel.app/privacy.html
```

먼저 `public/privacy.html`의 `YOUR-CONTACT-EMAIL`을 실제 연락처로 바꾸십시오.

## 4. 테스트 요청

```bash
curl -X POST "https://배포도메인.vercel.app/api/analyze" \
  -H "Content-Type: application/json" \
  -H "X-Analyzer-Key: ANALYZER_API_KEY값" \
  -d '{
    "keywords": ["영어공부 혼자하기", "영어식 사고", "회사 영어"],
    "trendDays": 90
  }'
```

## 5. GPT 지침에 넣을 호출 규칙

```text
새 글의 주제 후보를 만들기 전에 analyzeNaverKeywords Action을 호출한다.
검색 의도가 다른 한국어 키워드를 최대 5개씩 조회한다.
monthlySearches는 월간 규모로만 해석하고 실시간 검색량이라고 표현하지 않는다.
trend.change7dPct와 trend.change30dPct로 최근 상승세를 판단한다.
freshness.blog와 freshness.news의 최근 문서 수는 날짜순 상위 100개 표본임을 고려한다.
검색량, 상승세, 경쟁도, 글 주제 적합성을 함께 보고 최종 후보 3개만 제시한다.
Action 호출이 실패하면 실패 사실을 짧게 밝히고 공개 검색 기반 정성 분석으로 전환한다.
```

## 반환값 해석

- `searchVolume.monthlySearches.exactTotal`: PC와 모바일 값이 모두 정확한 숫자일 때만 제공
- `searchVolume.monthlySearches.totalRange`: `<10`이 포함된 경우 가능한 범위
- `trend.change7dPct`: 최근 7일 평균과 직전 7일 평균의 변화율
- `trend.change30dPct`: 최근 30일 평균과 직전 30일 평균의 변화율
- `freshness.blog.totalIndexedResults`: 현재 네이버 블로그 검색 전체 결과 수
- `freshness.blog.within7d`: 날짜순 상위 100개 표본 중 최근 7일 문서 수
