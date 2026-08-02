# USD/KRW 외생변수: 한미 3년물 금리차 후보 조사

## 결론

한미 2년물 금리차는 이번 Validation 설계의 후보로 사용하지 않는다. ECOS의 한국 국고채 2년물은 2021-03-10부터 제공되어 2018~2021 Validation 초기 기준일의 context 756을 구성할 수 없기 때문이다.

대신 같은 만기의 한국·미국 3년물 국채 수익률 차이를 조건부 후속 후보로 선정한다.

```text
프로젝트 후보명: 한미 3년물 금리차
프로젝트 컬럼명: us_kr_3y_yield_spread_pct_point
정의: 미국 국채 3년물 수익률 - 한국 국고채 3년물 수익률
단위: 퍼센트포인트(%p)
용도: USD/KRW 과거 공변량 후보
상태: 조건부 선정 — 공개 시점 정책 확정 전에는 모델 입력으로 사용하지 않음
```

값이 양수이면 미국 3년물 수익률이 한국 3년물보다 높다는 뜻이다. 이 부호 정의는 수집·전처리·평가 단계에서 바꾸지 않는다.

## 2년물 후보를 제외한 이유

ECOS `StatisticItemList` 응답에서 확인한 한국 국고채 일별 시계열의 시작일은 다음과 같다.

| 만기 | ECOS 항목 코드 | 최초 제공일 | 판정 |
|---|---|---:|---|
| 국고채 2년 | `010195000` | 2021-03-10 | 2018~2021 Validation 입력 이력 부족으로 제외 |
| 국고채 3년 | `010200000` | 1998-11-13 | 기간 조건 충족 |

2년물이 경제적으로 부적절해서 제외한 것이 아니다. 현재 고정된 검증 구간과 입력 길이를 유지할 수 없기 때문에 제외했다.

## 한국 3년물 식별값

ECOS 메타데이터와 실제 `StatisticSearch` 응답으로 다음 값을 확인했다.

```text
통계표 코드: 817Y002
통계표명: 1.3.2.1. 시장금리(일별)
주기: D
항목 코드: 010200000
항목명: 국고채(3년)
단위: 연%
최초 제공일: 1998-11-13
최근 제공일(조사 시점 메타데이터): 2026-07-31
기관: 한국은행
```

짧은 실제 조회는 API 키를 가린 다음 구조로 수행했다.

```text
https://ecos.bok.or.kr/api/StatisticSearch/***/json/kr/1/1000/817Y002/D/20240701/20240710/010200000
```

응답 검증 결과:

```text
요청 기간: 2024-07-01~2024-07-10
ECOS list_total_count: 8
실제 응답 행 수: 8
최초 관측: 2024-07-01, 3.21
최종 관측: 2024-07-10, 3.12
STAT_CODE: 817Y002
ITEM_CODE1: 010200000
ITEM_NAME1: 국고채(3년)
UNIT_NAME: 연%
```

이번 조회는 식별값과 응답 구조 확인용이다. 원본 전체 기간 수집이나 모델용 파일 생성은 수행하지 않았다.

## 미국 3년물 식별값

미국 측 후보는 FRED의 `DGS3`다.

```text
FRED series ID: DGS3
시계열명: Market Yield on U.S. Treasury Securities at 3-Year Constant Maturity, Quoted on an Investment Basis
주기: Daily
단위: Percent
계절조정: Not Seasonally Adjusted
출처: Board of Governors of the Federal Reserve System
Release: H.15 Selected Interest Rates
최초 제공일: 1962-01-02
```

공식 자료:

- FRED `DGS3`: https://fred.stlouisfed.org/series/DGS3
- Federal Reserve H.15: https://www.federalreserve.gov/releases/h15/
- H.15 안내: https://www.federalreserve.gov/releases/h15/about.htm
- ECOS: https://ecos.bok.or.kr/

두 시계열은 모두 연율 퍼센트이므로 별도의 100배 또는 0.01배 단위 변환 없이 차이를 계산한다. 결과 단위만 `%`가 아니라 `%p`로 명시한다.

## 공개 시점과 미래 누수 위험

관측 날짜가 같다는 이유만으로 두 금리와 USD/KRW를 같은 날짜에 결합하면 안 된다.

미국 H.15는 현재 영업일마다 미국 동부시간 16:15에 게시되며 휴일에는 게시되지 않는다. 따라서 미국 관측값에는 관측일과 별도로 실제 H.15 공개 시각 또는 보수적인 안전 사용일을 기록해야 한다.

ECOS 응답에서는 한국 국고채 3년물의 정확한 일별 게시 시각을 확인하지 못했다.

```text
한국 국고채 3년물 정확한 게시 시각: 확인 필요
과거 수정치와 최초 공개값 재현 가능성: 확인 필요
미국 DGS3 과거 관측값의 실제 릴리스별 vintage 재현: 확인 필요
```

공개 시점이 확정되기 전에는 다음 방식을 사용하지 않는다.

```text
금지: USD/KRW 날짜 t와 두 금리의 관측 날짜 t를 단순 결합
금지: 근거 없이 모든 시계열에 동일한 lag1 적용
금지: 휴장일 금리를 전일값으로 채운 뒤 실제 관측으로 표시
금지: 최신 개정값을 당시 알려진 최초 공개값으로 간주
```

모델 입력 파일은 각 값이 USD/KRW 예측 기준일에 실제로 이용 가능했음을 증명하는 `observation_date`, `available_at` 또는 `safe_from_krw_date`를 보존해야 한다.

## 공개 시점 조사 결과와 안전 사용 규칙

금융투자협회 「금융투자회사의 영업 및 업무에 관한 규정 시행세칙」은 수익률 보고회사가 11시 30분과 15시 30분 현재 수익률을 보고하고, 협회가 이를 산정해 12시와 16시에 발표한다고 정한다. 국고채권 3년은 최종호가수익률 보고 대상에 포함된다.

공식 근거:

- 금융투자협회 시행세칙 발표 조항: https://law.kofia.or.kr/service/law/detailArticlePrint.do?contentSeq=129510&historySeq=1065&seq=137
- 금융투자협회 최종호가수익률 기준: https://law.kofia.or.kr/service/law/lawFullScreenContent.do?historySeq=482&seq=178

ECOS `817Y002/010200000`의 값이 금융투자협회 16시 발표값을 ECOS 시스템에 몇 시에 반영하는지는 확인하지 못했다. 따라서 ECOS 관측일 당일에는 사용하지 않는다.

```text
kr_yield_observation_date = ECOS TIME
kr_yield_source_published_at = 관측일 16:00 Asia/Seoul
kr_yield_safe_from_krw_date = 관측일 + 1 calendar day
```

`kr_yield_source_published_at`은 금융투자협회 원천 발표 시각이며 ECOS 적재 완료 시각이 아니다. 전체 기간을 ECOS 원본으로 백테스트할 때 이 차이는 남은 한계로 명시한다. 향후 ECOS 적재 시각을 공식적으로 확인하면 안전 사용 규칙을 더 늦출 수는 있지만, 기존 Test 결과를 보고 더 이른 시점으로 당기지 않는다.

미국 연방준비제도는 H.15를 월요일부터 금요일까지 미국 동부시간 16시 15분에 게시하며, 휴일이나 연준 폐쇄일에는 게시하지 않는다고 명시한다. 2024년 7월 공식 달력에는 H.15 공개일이 1·2·3·5일 등으로 기재되어 있고, 7월 4일 예정 통계는 7월 5일로 이동한다고 명시돼 있다.

공식 근거:

- H.15 현재 공개 정책: https://www.federalreserve.gov/releases/h15/
- H.15 공지·폐쇄 이력: https://www.federalreserve.gov/feeds/h15.html
- 2024년 7월 연준 공식 달력: https://www.federalreserve.gov/newsevents/2024-july.htm

미국 값에는 관측 날짜보다 뒤인 최초 공식 H.15 공개일을 연결한다.

```text
us_yield_observation_date = FRED observation_date
h15_release_date = observation_date 이후 최초 공식 H.15 공개일
us_yield_available_at_et = h15_release_date 16:15 America/New_York
us_yield_available_at_kst = ET 시각을 Asia/Seoul로 변환
us_yield_safe_from_krw_date = available_at_kst 날짜 + 1 calendar day
```

KST 변환 뒤 하루를 더 늦추는 이유는 같은 한국 날짜 안에서 ECOS USD/KRW 관측·게시 시각과 H.15 공개값의 선후 관계를 추측하지 않기 위해서다. 관측일 기준 단순 `lag1`은 미국 휴일과 연준 폐쇄에 따른 공개 지연을 처리하지 못하므로 사용하지 않는다.

금리차는 각 USD/KRW 날짜에 다음 조건을 모두 만족하는 최신 유효 금리만 as-of 방식으로 연결한 뒤 계산한다.

```text
kr_yield_safe_from_krw_date <= usd_krw_date
us_yield_safe_from_krw_date <= usd_krw_date
두 금리 모두 숫자값 존재

us_kr_3y_yield_spread_pct_point
= us_treasury_3y_percent - kr_treasury_3y_percent
```

한쪽 값이 비어 있으면 해당 원시 행을 채우거나 금리차를 새로 만들지 않는다. 다만 각 USD/KRW 날짜 당시 이미 공개된 최신 유효 관측을 as-of 조회하는 것은 결측값 보간이 아니라 당시 이용 가능한 상태의 사용이며, 실제 사용된 두 관측 날짜를 결과 열에 보존한다.

## 데이터 품질 및 스냅샷 원칙

다음 수집 단계에서는 한국과 미국 시계열을 각각 원본 스냅샷으로 저장하고 기존 파일을 덮어쓰지 않는다.

- 수집 시각, 요청 기간, 시계열 ID, 단위와 출처를 기록한다.
- 날짜 오름차순, 중복 날짜, 빈 값, 숫자 변환 실패, 0 이하 값과 기간 밖 행을 보고한다.
- 휴장일에 새 행을 만들거나 보간하지 않는다.
- 두 금리의 차이는 두 값이 모두 안전하게 이용 가능한 USD/KRW 관측일에만 계산한다.
- 최신 개정 시계열만 사용하면 point-in-time 백테스트가 아니라는 한계를 기록한다.
- 2022~2025 최종 Test는 후보 선택이나 정렬 규칙 선택에 사용하지 않는다.

## 다음 단계의 완료 조건

다음 한 단계는 모델 평가가 아니라 짧은 기간 수집과 공개 시점 정책 검증이다.

1. `DGS3`와 `817Y002/010200000`을 같은 짧은 기간으로 수집한다.
2. 원본 응답을 출처별·수집 시각별로 보존한다.
3. 단위, 날짜 범위, 정렬, 중복, 빈 값과 숫자 변환을 검증한다.
4. H.15의 실제 공개일·시각을 자료에 연결한다.
5. 한국 국고채 일별값의 게시 시각을 공식 근거로 확인한다.
6. 5번을 확인할 수 없으면 보수적인 안전 사용 규칙을 먼저 문서화하고 고정한다.
7. 누수 없는 결합 파일이 완성된 뒤에만 개발 기준일 smoke test를 검토한다.

현재 단계에서는 후보 정의와 실제 식별값 검증만 완료했다. 전체 기간 수집, 공변량 결합, Chronos-2 smoke test와 Validation은 아직 수행하지 않았다.

## 짧은 기간 수집 결과

두 시계열을 2024-07-01~2024-07-10으로 실제 수집했다.

한국 국고채 3년물:

```text
ECOS StatisticSearch URL 구조:
https://ecos.bok.or.kr/api/StatisticSearch/***/json/kr/1/1000/817Y002/D/20240701/20240710/010200000

list_total_count: 8
실제 수집 행 수: 8
최초 날짜: 2024-07-01
최종 날짜: 2024-07-10
중복 날짜 수: 0
빈 DATA_VALUE 수: 0
숫자 변환 실패 수: 0
대상 외 항목 혼입 수: 0
단위 오류 수: 0
최솟값: 3.114 연%
최댓값: 3.210 연%
```

미국 국채 3년물:

```text
FRED URL:
https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3&cosd=2024-07-01&coed=2024-07-10

원본 행 수: 8
처리 행 수: 8
최초 날짜: 2024-07-01
최종 날짜: 2024-07-10
중복 날짜 행 수: 0
빈 값 행 수: 1
숫자 변환 실패 수: 0
기간 밖 행 수: 0
0 이하 값 수: 0
유효 최솟값: 4.37 Percent
유효 최댓값: 4.58 Percent
```

FRED의 빈 값은 2024-07-04 행이다. 해당 행을 삭제하거나 전일값으로 채우지 않고 원본과 처리본에 그대로 보존했다.

생성 파일:

```text
data/raw/ecos/kr_treasury_3y_20240701_20240710_20260802T205444.json
data/processed/ecos/kr_treasury_3y_20240701_20240710.csv
data/raw/fred/dgs3_20240701_20240710_20260802T115445Z.csv
data/raw/fred/dgs3_20240701_20240710_20260802T115445Z_metadata.json
data/processed/fred/us_treasury_3y_20240701_20240710_20260802T115445Z.csv
```

원본 ECOS JSON과 FRED 메타데이터에는 API 키를 저장하지 않았다. 두 처리본의 날짜를 단순히 맞춘 금리차 파일은 생성하지 않았다. 한국 국고채 값의 정확한 게시 시각 또는 보수적 안전 사용 규칙이 확정되기 전에는 누수 없는 결합을 증명할 수 없기 때문이다.

현재 단계에서는 후보 정의, 식별값 검증, 짧은 기간 수집·품질 검사와 공개 시점 기반 안전 사용 규칙 확정을 완료했다. 다음 단계는 공식 H.15 공개 달력 수집과 두 금리의 `safe_from_krw_date` 산출 코드 구현이다. 전체 기간 수집, 금리차 결합, Chronos-2 smoke test와 Validation은 아직 수행하지 않았다.

## 짧은 기간 공개시점 적용 결과

연준 2024년 7월 공식 달력 HTML을 원본으로 저장하고 H.15 공개일을 파싱했다.

```text
공식 달력 URL: https://www.federalreserve.gov/newsevents/2024-july.htm
H.15 공식 공개일 수: 22
7월 4일 H.15 공개: 없음
7월 4일 전후 공개일: 2024-07-03, 2024-07-05
```

한국과 미국 금리 처리본 각각 8행에 공개시점 열을 추가했다.

```text
한국 공개시점 적용 행 수: 8
한국 안전 사용일이 관측일보다 늦은 행: 8/8
미국 공개시점 적용 행 수: 8
미국 H.15 공개일이 관측일보다 늦은 행: 8/8
미국 안전 사용일이 KST 공개일보다 늦은 행: 8/8
미국 빈 값 보존: 1행
```

휴일 지연 예시는 다음과 같다.

```text
DGS3 관측일: 2024-07-03
다음 공식 H.15 공개일: 2024-07-05
available_at_et: 2024-07-05T16:15:00-04:00
available_at_kst: 2024-07-06T05:15:00+09:00
safe_from_krw_date: 2024-07-07
```

유효 산출물:

```text
data/raw/fred/h15_calendar_202407_20260802T120857Z.html
data/processed/ecos/kr_treasury_3y_availability_20240701_20240710_20260802T120939Z.csv
data/processed/fred/us_treasury_3y_availability_20240701_20240710_20260802T120939Z.csv
```

다음 최초 산출물은 한국 `item_code`의 선행 0이 CSV 재로딩 과정에서 사라진 결함이 있으므로 사용하지 않는다. 원인 추적을 위해 삭제하지 않았다.

```text
data/processed/ecos/kr_treasury_3y_availability_20240701_20240710_20260802T120857Z.csv
data/processed/fred/us_treasury_3y_availability_20240701_20240710_20260802T120857Z.csv
```

미국 파일 자체에는 같은 직렬화 결함이 없지만 두 파일을 하나의 실행 단위로 추적하기 위해 최초 실행 산출물 전체를 비유효로 분류한다. 수정된 코드에는 숫자로 읽힌 한국 항목 코드를 검증 후 `010200000`으로 복원하는 테스트를 추가했다.

현재 단계에서는 공식 H.15 달력 수집과 짧은 기간 안전 사용일 산출까지 완료했다. 다음 단계는 전체 Validation 입력 기간을 포함하는 월별 H.15 공식 달력을 수집하고, 한미 3년물 전체 기간에 동일 규칙을 적용하는 것이다. 금리차 as-of 결합, Chronos-2 smoke test와 Validation은 아직 수행하지 않았다.

## Validation 입력 기간 전체 수집 결과

기존 USD/KRW 모델 데이터에서 첫 Validation 요청 기준일 이전의 실제 관측 756개를 역산했다.

```text
첫 Validation 요청 기준일: 2018-01-01
실제 마지막 입력 관측일: 2017-12-29
context_length: 756
필요한 최초 입력 관측일: 2014-12-09
전체 금리 수집 기간: 2014-12-09~2021-12-31
```

한국 국고채 3년물 전체 수집:

```text
ECOS list_total_count 및 실제 수집 행: 1,746
페이지: 1~1000, 1001~2000
최초·최종 날짜: 2014-12-09, 2021-12-31
중복·빈 값·숫자 변환 실패: 0
대상 외 항목·단위 오류: 0
항목 코드와 단위: 010200000, 연%
```

미국 국채 3년물 전체 수집:

```text
원본 및 처리 행: 1,844
최초·최종 날짜: 2014-12-09, 2021-12-31
중복 날짜: 0
빈 값: 76
숫자 변환 실패·기간 밖 행·0 이하 값: 0
유효 범위: 0.10~3.05 Percent
```

미국 빈 값 76행은 삭제하거나 채우지 않았다.

```text
data/raw/ecos/kr_treasury_3y_20141209_20211231_20260802T211955.json
data/processed/ecos/kr_treasury_3y_20141209_20211231.csv
data/raw/fred/dgs3_20141209_20211231_20260802T121957Z.csv
data/raw/fred/dgs3_20141209_20211231_20260802T121957Z_metadata.json
data/processed/fred/us_treasury_3y_20141209_20211231_20260802T121957Z.csv
```

## H.15 공개 체계별 전체 원본 수집

2016-10-11 공개 체계 변경을 반영해 자료를 분리했다.

```text
2014-12-15~2016-09-26 공식 주간판: 94개
주간판 ZIP·manifest SHA-256 일치: 94/94

2017-01~2022-01 요청 월: 61
공식 월별 HTML 보존: 60
공식 달력 미확인: 2019-09
통합 공식 일별 공개일: 1,247개
월별 ZIP·manifest SHA-256 일치: 60/60
```

주간판은 일반적으로 월요일, 월요일 휴일에는 다음 영업일에 게시됐다. 일부 공식 아카이브는 URL 날짜와 본문의 `Release Date`가 달라 본문 날짜가 같은 주 안인지 검증했다. 과거 주간판의 정확한 시각은 전체 기간에 대해 확인되지 않아 공개일의 미국 동부시간 종료 시점을 보수적 상한으로 사용하며 현재 16시 15분 규칙을 소급하지 않는다.

2019년 7·8월은 예외 URL의 실제 HTML 제목을 검증해 수집했다. 2019년 9월 공식 페이지는 확인한 일반·숫자형 URL이 모두 404이므로 공개일을 만들지 않았다.

공식 공개 달력 확인 불가 구간:

```text
2016-09-27~2017-01-02: 주간판 종료 후 월별 공식 달력 미확보
2019-09-01~2019-09-30: 연준 월별 공식 페이지 현재 404
```

다음 안전 사용일 산출 단계에서는 이 구간을 다음으로 확인되는 공식 공개일까지 보수적으로 지연한다. 영업일 달력으로 공개일을 새로 만들지 않는다.

```text
data/raw/fred/h15_weekly_releases_20141215_20160926_20260802T122733Z.zip
data/raw/fred/h15_weekly_releases_20141215_20160926_20260802T122733Z_manifest.json
data/raw/fred/h15_calendars_201701_202201_20260802T122738Z.zip
data/raw/fred/h15_calendars_201701_202201_20260802T122738Z_manifest.json
```

현재 단계에서는 Validation context를 충족하는 한미 금리값과 확인 가능한 공식 공개일 원본 수집을 완료했다. 다음 단계는 공개 체계별 manifest를 읽어 전체 금리에 안전 사용일을 부여하는 것이다. 금리차 as-of 결합, Chronos-2 smoke test와 Validation은 아직 수행하지 않았다.

## 전체 기간 안전 사용일 산출

저장한 원시 금리와 H.15 공개 자료의 manifest·ZIP SHA-256을 다시 검증한 뒤 2014-12-09~2021-12-31 전체 관측에 안전 사용일을 부여했다.

```text
한국 국고채 3년물: 1,746행
미국 국채 3년물: 1,844행
미국 빈 값 보존: 76행
날짜 정렬 오류: 0
중복 관측 날짜: 0
안전 사용일 누락: 0
공개 한국 날짜 이전 또는 당일 사용: 0
```

한국 금리는 16시 KST 공개를 기준으로 다음 달력일부터만 사용한다. 미국 금리는 관측일 이후 최초로 확인되는 공식 H.15 공개에 연결했다. 주간 공표 구간은 정확한 과거 시각을 확인하지 못했으므로 공개일 23:59:59 ET를 적용하고, 일간 공표 구간은 16:15 ET를 적용한 뒤 각각 KST 변환 날짜의 다음 달력일부터만 사용한다.

확인하지 못한 공개일을 영업일 규칙으로 추정하지 않았다.

```text
2016년 공개 체계 전환 공백 보수적 지연: 71행
2019년 9월 공식 달력 결손 보수적 지연: 21행
```

두 구간은 다음으로 확인되는 공식 공개일까지 지연했다. 따라서 당시 실제 공개보다 늦게 사용하는 행이 있을 수 있으나 미래 정보가 일찍 들어가는 방향의 누수는 방지한다. 미국 빈 값 76행에는 가용 시점을 기록하되 금리값을 채우지 않았다.

```text
data/processed/ecos/kr_treasury_3y_availability_20141209_20211231_20260802T123348Z.csv
data/processed/fred/us_treasury_3y_availability_20141209_20211231_20260802T123348Z.csv
```

현재 단계에서는 전체 기간 금리별 안전 사용일 산출까지 완료했다. 다음 단계는 각 USD/KRW 관측일에 당시 안전하게 공개된 최신 유효 한국·미국 금리를 각각 as-of 연결하고 `미국 3년물 - 한국 3년물` 금리차를 계산하는 것이다. 금리차 결합, Chronos-2 smoke test와 Validation은 아직 수행하지 않았다.

## USD/KRW 기준 as-of 금리차 결합

각 USD/KRW 날짜에 `safe_from_krw_date <= date`를 만족하는 최신 유효 한국·미국 3년물 관측을 독립적으로 연결했다. 미국 빈 값 76행은 감사 파일에 보존하고 상태 선택에서 제외했으며, 값을 채우거나 보간하지 않았다.

```text
결합 행 수: 1,740
기간: 2014-12-17~2021-12-31
중복 날짜: 0
핵심 값 결측: 0
미래 안전 사용일 연결: 0
현재 또는 미래 관측일 연결: 0
금리차 계산: 미국 3년물 - 한국 3년물
금리차 범위: -1.338000~1.110000 %p
한국 금리 제외 관측: 0
미국 빈 값 제외·감사 보존: 76
```

한국 금리 최대 경과일은 11일이다. 미국 최대 경과일 103일은 2016년 공개 체계 전환 공백에서 확인되지 않은 공개일을 만들지 않고 마지막 확인 상태를 유지한 결과다. 이는 미래 누수는 아니지만 오래된 값이므로 향후 Validation 결과 해석에서 전환 구간 여부를 추적해야 한다.

```text
data/processed/usd_us_kr_3y_yield_spread_asof_20141217_20211231_20260802T131022Z.csv
data/processed/audit/us_kr_3y_yield_excluded_observations_20260802T131022Z.csv
```

첫 Validation 기준일 2017-12-29까지 필요한 USD/KRW context 756행은 2014-12-09부터 시작한다. 현재 금리차 결합은 2014-12-17부터 750행만 존재해 다음 6개 날짜가 부족하다.

```text
2014-12-09
2014-12-10
2014-12-11
2014-12-12
2014-12-15
2014-12-16
```

현재 수집 시작일과 최초 H.15 주간판 공개일이 너무 늦어 발생한 시작 경계 손실이다. 날짜를 복제하거나 이후 금리를 과거로 역전파하지 않는다. 따라서 as-of 결합 로직과 산출물 검증은 완료했지만 Validation 입력 준비는 부분 완료다. 다음 단계는 2014-12-09 이전의 한미 금리 및 H.15 주간판 원자료를 앞당겨 수집하고 첫 기준일에 실제 756행이 확보되는지 재검증하는 것이다. 그 전에는 Chronos-2 smoke test나 Validation을 실행하지 않는다.

## 시작 경계 확장 진행 결과

미국 DGS3와 H.15 공식 주간판의 시작점을 2014-12-01로 앞당겼다.

```text
FRED DGS3 2014-12-01~2021-12-31: 1,850행
FRED 빈 값: 76
FRED 중복: 0
H.15 주간판 2014-12-01~2016-09-26: 96개
최초 H.15 공식 공개일: 2014-12-01
최종 H.15 공식 공개일: 2016-09-26
ZIP·manifest 해시 검증: 통과
```

```text
data/raw/fred/dgs3_20141201_20211231_20260802T131449Z.csv
data/raw/fred/dgs3_20141201_20211231_20260802T131449Z_metadata.json
data/processed/fred/us_treasury_3y_20141201_20211231_20260802T131449Z.csv
data/raw/fred/h15_weekly_releases_20141201_20160926_20260802T131511Z.zip
data/raw/fred/h15_weekly_releases_20141201_20160926_20260802T131511Z_manifest.json
data/processed/fred/us_treasury_3y_availability_20141201_20211231_20260802T131538Z.csv
```

새 미국 가용일 처리본과 기존 한국 처리본을 메모리에서 결합하면 기간은 2014-12-10~2021-12-31, 첫 Validation 기준일까지 755행이다. 미국 시작 경계 6행은 해결됐지만 2014-12-09 한 행은 여전히 연결할 한국 금리가 없다.

현재 환경에는 `ECOS_API_KEY`가 설정되지 않아 한국 국고채 3년물의 2014-12-01 시작 확장 수집을 실행하지 않았다. 키 값을 문서나 로그에 기록하지 않는다. 다음 단계는 키가 설정된 환경에서 ECOS `817Y002/010200000`, 일별, `20141201~20211231`을 수집하고 전체 가용일·as-of 결합을 재생성하여 첫 기준일 756행을 검증하는 것이다. 이후 금리를 2014-12-09로 역전파하거나 임의로 채우지 않는다.

## 시작 경계 확장 완료

이후 상위 저장소 `.env`에서 `ECOS_API_KEY` 설정 여부만 확인했고 실제 값은 출력하지 않았다. 한국 국고채 3년물을 2014-12-01부터 다시 수집했다.

```text
ECOS 817Y002/010200000: 2014-12-01~2021-12-31
행 수: 1,752
중복·빈 값·숫자 변환·대상 외 항목·단위 오류: 0
```

미국은 2014-12-01 시작만으로 최초 DGS3 관측의 보수적 안전 사용일이 12월 10일이 되어 한 행이 계속 부족했다. 이후 금리를 과거로 보내지 않고 DGS3와 H.15 시작 주를 2014-11-24로 한 주 더 앞당겼다.

```text
FRED DGS3 2014-11-24~2021-12-31: 1,855행
FRED 빈 값: 77
FRED 중복: 0
H.15 주간판 2014-11-24~2016-09-26: 97개
최초 공식 공개일: 2014-11-24
```

최종 가용일과 as-of 결합 품질은 다음과 같다.

```text
결합 기간: 2014-12-03~2021-12-31
결합 행 수: 1,750
첫 Validation 기준일 2017-12-29까지: 760행
실제 context 756 범위: 2014-12-09~2017-12-29
중복·핵심 결측·미래 안전 사용일·현재 또는 미래 관측 연결: 0
금리차 계산 오차: 부동소수점 허용 범위 이내
감사 보존 미국 빈 값: 77행
```

```text
data/processed/ecos/kr_treasury_3y_20141201_20211231.csv
data/raw/ecos/kr_treasury_3y_20141201_20211231_20260802T221751.json
data/processed/ecos/kr_treasury_3y_availability_20141201_20211231_20260802T131936Z.csv
data/processed/fred/us_treasury_3y_20141124_20211231_20260802T131857Z.csv
data/raw/fred/h15_weekly_releases_20141124_20160926_20260802T131918Z.zip
data/raw/fred/h15_weekly_releases_20141124_20160926_20260802T131918Z_manifest.json
data/processed/fred/us_treasury_3y_availability_20141124_20211231_20260802T131936Z.csv
data/processed/usd_us_kr_3y_yield_spread_asof_20141203_20211231_20260802T131941Z.csv
data/processed/audit/us_kr_3y_yield_excluded_observations_20260802T131941Z.csv
```

Validation context 756 시작 경계는 해결됐다. 다음 단계는 이 최종 고정 데이터셋으로 개발 기준일 하나의 Chronos-2 과거 공변량 smoke test를 수행해 입력 스키마·분위수·날짜·누수 검사를 확인하는 것이다. 전체 2018~2021 Validation은 smoke test와 사전 진입 조건 확인 이후에만 실행한다.

## Chronos-2 과거 공변량 smoke test

최초 Validation 기준일 2017-12-29에서 입력 구조 확인용 smoke test를 수행했다. 이 기준일의 수치로 후보를 채택·탈락시키거나 설정을 다시 선택하지 않는다.

```text
모델: amazon/chronos-2
장치: mps:0
타깃: USD/KRW
과거 공변량: US 3Y - KR 3Y yield spread point-in-time as-of
미래 공변량 제공: False
context: 2014-12-09~2017-12-29, 756행
prediction length: 20
실제 목표 날짜: 2018-01-02~2018-01-29
```

출력은 20행이며 날짜 오름차순, 중복·결측 0건, 모든 목표 날짜가 기준일 이후이고 `q0.1 <= q0.5 <= q0.9`를 만족했다. 모델 입력에는 기준일까지 안전하게 공개된 과거 금리차만 제공했고 미래 금리차 실제값은 제공하지 않았다.

```text
금리차 공변량 Chronos MAE: 5.237224원
Random Walk MAE:           4.845000원
```

단일 기준일에서는 Random Walk가 더 좋지만 smoke test는 성능 평가가 아니므로 후보를 탈락시키지 않는다. 샌드박스 내부에서는 `mps.is_available()`이 `False`였으나 동일 `.venv`를 샌드박스 밖에서 실행하면 `True`이고 MPS 텐서 및 Chronos 예측이 성공했다. 따라서 현재 확인된 차이는 코드나 패키지 설치가 아니라 실행 격리 환경의 장치 접근 차이다.

```text
outputs/forecasts/experiments/yield_spread/usd_krw_chronos2_us_kr_3y_yield_spread_asof_smoke_origin20171229.csv
```

다음 단계는 전체 2018~2021 Validation을 보기 전에 고정 설정과 사전 진입·탈락 조건을 확정하는 것이다. 이후 동일한 48개 기준일에서 Random Walk, 단변량 Chronos와 금리차 공변량 Chronos를 비교한다.

## Validation 설정과 사전 판정 기준 고정

전체 결과를 보기 전에 `configs/yield_spread_validation.json`에 다음 설정을 고정했다.

```text
모델: amazon/chronos-2
Target: USD/KRW
Past covariate: US 3Y - KR 3Y yield spread point-in-time as-of
Future covariates: 없음
Validation: 2018-01-01~2021-12-31
기준일: 월별 48개
예측 행: 960
Context length: 756
Prediction length: 20
Device: MPS
Batch size: 8
Cross learning: false
```

최종 금리차 입력과 기존 단변량 Validation 예측 파일은 경로와 SHA-256을 설정에 고정했다. `chronos-forecasting 2.3.1`, `torch 2.13.0`도 기록했다.

사전 진입 조건은 다음을 모두 만족해야 한다.

1. 단변량 Chronos보다 전체 MAE가 낮아야 한다.
2. 단변량 Chronos보다 전체 RMSE가 낮아야 한다.
3. Random Walk보다 전체 MAE가 낮아야 한다.
4. Random Walk보다 전체 RMSE가 낮아야 한다.
5. 48개 기준일 중 MAE를 최소 25회 단변량보다 개선해야 한다.
6. 48개 기준일 중 RMSE를 최소 25회 단변량보다 개선해야 한다.
7. 모든 한국·미국 금리 관측일과 안전 사용일 누수 검사를 통과해야 한다.

방향 정확도, q0.1~q0.9 포함률, 평균 구간 폭, 연도별·예측 구간별 성능과 최대 금리 경과일은 반드시 보고하지만 단독 진입 조건으로 사용하지 않는다. 하나라도 사전 진입 조건을 통과하지 못하면 금리차 공변량을 현재 후보에서 제외하고 이 입력 구조에 LoRA를 적용하지 않는다.

2022~2025 최종 Test는 설정 선택이나 이 Validation 판정에 사용하지 않는다. 결과 확인 뒤 context, horizon, 금리차 정의, 공개시점 규칙 또는 진입 기준을 다시 맞추지 않는다.

현재는 설정 고정까지만 완료했으며 전체 Validation은 아직 실행하지 않았다. 다음 단계는 고정 설정과 입력 해시를 검증하는 평가 코드를 구현하고 단위 테스트를 통과시키는 것이다.

## Validation 평가 코드 준비

`src/experiments/yield_spread/evaluate_yield_spread_validation.py`와 단위 테스트를 추가했다. 평가 코드는 실행 직전에 설정 JSON의 입력·기준 파일 SHA-256을 다시 계산해 고정값과 다르면 중단한다. 기존 단변량 Validation의 기준일·실제값·Random Walk를 그대로 사용하며 금리차 모델의 q0.1·q0.5·q0.9만 새로 생성한다.

출력 후보는 다음과 같이 분리한다.

```text
48개 기준일 전체 예측
전체 요약
기준일별 지표
연도별 지표
D+1~D+5, D+6~D+10, D+11~D+20 지표
사전 조건별 통과 여부와 최종 판정 JSON
```

모델 실행 전 실제 입력 드라이런 결과는 다음과 같다.

```text
입력 그룹: 48
참조 행: 960
모든 target 길이: 756
모든 과거 금리차 길이: 756
미래 공변량: 없음
한국 금리 최대 경과일: 11
미국 금리 최대 경과일: 103
```

미국 최대 103일은 이미 확인한 2016년 공개 체계 전환 공백의 보수적 상태 유지다. 평가 결과에 이 값을 함께 기록해 해석 가능하게 한다. 단위 테스트에서는 모든 고정 조건 통과, Random Walk 우세 시 탈락, 입력 SHA-256 변경 시 실행 차단을 확인했다.

현재 평가 코드와 입력 구성 검증까지만 완료했으며 실제 48개 Chronos 예측과 성능 판정은 아직 실행하지 않았다. 다음 단계는 고정 설정을 변경하지 않고 MPS에서 전체 Validation을 한 번 실행하는 것이다.

## 2018~2021 전체 Validation 결과

고정 설정을 변경하지 않고 MPS에서 월별 48개 기준일과 20영업일 horizon을 한 번 평가했다. 전체 예측은 960행이며 2022~2025 최종 Test와 미래 공변량은 사용하지 않았다.

| 모델 | MAE(원) | RMSE(원) |
|---|---:|---:|
| 한미 3년물 금리차 과거 공변량 Chronos-2 | 12.098771 | 15.782616 |
| 단변량 Chronos-2 | 11.968236 | 15.724912 |
| Random Walk | 12.259792 | 15.967171 |

금리차 공변량 모델의 방향 정확도는 0.606250, q0.1~q0.9 포함률은 0.754167, 평균 구간 폭은 35.982143원이다. 기준일별 단변량 Chronos 대비 승리는 MAE 18/48, RMSE 19/48이다. 한국 금리 최대 경과일은 11일, 미국 금리 최대 경과일은 103일이며 후자는 앞서 기록한 2016년 공식 공개 체계 전환 공백의 보수적 처리 결과다.

| 사전 진입 조건 | 결과 |
|---|---|
| 단변량 Chronos보다 전체 MAE가 낮음 | 실패 |
| 단변량 Chronos보다 전체 RMSE가 낮음 | 실패 |
| Random Walk보다 전체 MAE가 낮음 | 통과 |
| Random Walk보다 전체 RMSE가 낮음 | 통과 |
| 기준일별 MAE 승리 최소 25/48 | 실패: 18/48 |
| 기준일별 RMSE 승리 최소 25/48 | 실패: 19/48 |
| 모든 관측일·안전 사용일 누수 검사 | 통과 |

산출물 품질 재검사에서는 날짜 오름차순 정렬을 확인했고, 기준일·목표일 중복, 결측값, Validation 기간 밖 행, 분위수 순서 오류가 모두 0건이었다.

```text
outputs/forecasts/experiments/yield_spread/usd_krw_chronos2_us_kr_3y_yield_spread_asof_h20_ctx756_validation_2018_2021.csv
outputs/metrics/experiments/yield_spread/usd_krw_chronos2_us_kr_3y_yield_spread_asof_h20_ctx756_validation_2018_2021_summary.csv
outputs/metrics/experiments/yield_spread/usd_krw_chronos2_us_kr_3y_yield_spread_asof_h20_ctx756_validation_2018_2021_by_origin.csv
outputs/metrics/experiments/yield_spread/usd_krw_chronos2_us_kr_3y_yield_spread_asof_h20_ctx756_validation_2018_2021_by_year.csv
outputs/metrics/experiments/yield_spread/usd_krw_chronos2_us_kr_3y_yield_spread_asof_h20_ctx756_validation_2018_2021_by_lead_segment.csv
outputs/metrics/experiments/yield_spread/usd_krw_chronos2_us_kr_3y_yield_spread_asof_h20_ctx756_validation_2018_2021_decision.json
```

모든 조건을 동시에 만족하지 못했으므로 이 한미 3년물 금리차 입력 구조는 현재 후보에서 제외한다. 사전 규칙에 따라 2022~2025 최종 Test, LoRA, 앙상블 후보로 넘기지 않으며, 이 결과를 보고 context·horizon·금리차 정의·공개시점 규칙 또는 판정 기준을 다시 맞추지 않는다.
