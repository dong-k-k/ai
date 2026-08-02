# USD/KRW 외생변수: Broad U.S. Dollar Index 후보 조사

## 결론

ICE U.S. Dollar Index(DXY) 자체는 이번 실험의 무료·재현 가능한 데이터 소스로 확정하지 않는다. 대신 미국 연방준비제도의 일별 `Nominal Broad U.S. Dollar Index`를 별도 후보로 채택한다.

```text
후보명: Nominal Broad U.S. Dollar Index
FRED series ID: DTWEXBGS
프로젝트 컬럼명: broad_usd_index
단위: Index Jan 2006=100
주기: Daily
계절조정: Not Seasonally Adjusted
출처: Board of Governors of the Federal Reserve System
Release: H.10 Foreign Exchange Rates
최초 제공일: 2006-01-02
용도: USD/KRW 과거 공변량 후보
```

이 지수는 DXY와 동일한 지수가 아니다. DXY라는 이름을 코드·설정·결과에 사용하지 않는다.

## DXY와 구분하는 이유

ICE DXY는 ICE가 산출하는 별도 지수이며 ICE FX 현물환율을 사용해 실시간 및 공식 종가를 계산한다. 반면 `DTWEXBGS`는 미국의 주요 교역 상대국 통화를 무역 비중으로 가중한 연준 Broad Dollar Index다.

연준 지수는 26개 경제권의 통화를 포함하고 일별 변화는 양자 환율 변화의 기하가중평균으로 계산한다. 가중치는 상품과 서비스의 양자 무역 자료를 사용한다. 따라서 유로 중심의 고정 구성 지수인 ICE DXY를 대체하는 동일 시계열이 아니라, 경제적 의미가 유사한 별도 달러 강도 변수다.

## 기간 적합성

현행 방법론의 역사 시계열은 2006-01-02부터 제공된다.

```text
USD/KRW 전체 원본 시작: 1964년
Broad Dollar Index 시작: 2006-01-02
현재 Validation: 2018~2021
```

전체 USD/KRW 역사와 결합할 수는 없지만 2018~2021 Validation의 context 756에는 충분하다. 모델 입력은 두 시계열이 모두 존재하고 공개된 구간으로 제한해야 한다.

## 공개 시점과 미래 누수 정책

H.10은 이전 주의 일별 양자 환율과 명목 달러지수를 주간 자료로 공개한다. 역사 데이터는 월요일 미국 동부시간 16:15에 갱신된다.

따라서 다음 정렬은 금지한다.

```text
금지: USD/KRW 날짜 t ↔ DTWEXBGS 관측 날짜 t
금지: 무조건 한 행만 미루는 단순 lag1
```

관측 날짜와 공개 날짜가 다르기 때문이다. 한국 시각은 미국보다 빠르므로 미국 월요일 16:15 ET 공개 자료는 일반적으로 한국의 다음 날짜에야 이용 가능하다.

다음 수집·정렬 단계에서는 각 지수 관측값에 실제 또는 보수적으로 산정한 `available_at`을 부여하고, 각 USD/KRW 입력 시점보다 먼저 공개된 최신 값만 연결한다.

```text
broad_usd_observation_date
broad_usd_available_at
usd_krw_observation_date
```

`broad_usd_available_at < usd_krw 관측 시점`이 증명되지 않으면 해당 값을 입력에 사용하지 않는다. ECOS USD/KRW의 정확한 일별 관측·공개 시각이 전체 기간에 대해 확정되지 않으면 날짜 단위에서 보수적인 추가 지연을 적용하고 그 규칙을 설정에 고정한다.

## 수정치와 스냅샷 정책

연준은 통화 가중치를 매년 갱신하며 가중치 조정으로 과거 명목·실질 지수값이 바뀔 수 있다고 안내한다. FRED도 데이터가 수정될 수 있음을 명시한다.

따라서 다음을 지킨다.

- 다운로드 시각을 포함한 원본 CSV 또는 원본 응답을 보존한다.
- 기존 원본 스냅샷을 덮어쓰지 않는다.
- 수집 시각, series ID, 단위, 최초·최종 관측일을 메타데이터에 기록한다.
- 가능하면 H.10 과거 릴리스 또는 ALFRED vintage로 당시 공개값 재현 가능성을 별도로 검토한다.
- 최신 개정 시계열만 사용한 백테스트라면 point-in-time 완전 재현이 아니라는 한계를 명시한다.

## 다음 단계의 완료 조건

`DTWEXBGS`의 짧은 기간 수집 및 품질 검증은 완료했다. 다음 조건을 모두 확인한 뒤에만 전체 기간을 수집한다.

1. 공식 FRED series ID와 열 구조가 확인된다.
2. 단위와 일별 주기가 메타데이터와 일치한다.
3. 원본 스냅샷을 덮어쓰지 않는다.
4. 날짜 오름차순, 중복, 빈 값, 숫자 변환 실패를 보고한다.
5. 공개일 기준 정렬에 필요한 메타데이터가 확보된다.
6. 코드와 파일에서 DXY가 아닌 `broad_usd_index` 명칭을 사용한다.
7. 2022~2025 최종 Test는 후보 선택에 사용하지 않는다.

## 짧은 기간 수집 결과

```text
요청 기간: 2024-01-01~2024-03-31
실제 최초 날짜: 2024-01-02
실제 최종 날짜: 2024-03-29
원본 행 수: 64
처리 행 수: 64
중복 날짜 행 수: 0
빈 값 행 수: 2
숫자 변환 실패 수: 0
기간 밖 행 수: 0
0 이하 값 수: 0
```

빈 값 날짜는 `2024-01-15`, `2024-02-19`다. 두 행을 조용히 삭제하거나 채우지 않고 원본과 처리본에 보존했다. 둘 다 미국 연방 공휴일에 해당하지만 이번 단계에서는 달력 정보를 이용해 값을 새로 만들지 않았다.

생성 파일:

```text
data/raw/fred/dtwexbgs_20240101_20240331_20260802T073658Z.csv
data/raw/fred/dtwexbgs_20240101_20240331_20260802T073658Z_metadata.json
data/processed/fred/broad_usd_index_20240101_20240331_20260802T073658Z.csv
```

처리본에도 빈 행을 유지했으므로 아직 모델 입력 파일이 아니다. 전체 기간 수집 전에 `available_at` 산정 및 point-in-time 정렬 규칙을 먼저 확정한다.

## 공개시점 규칙 검증 결과

연준 H.10 페이지가 화면의 공개일 목록을 생성할 때 사용하는 공식 JSON을 원본으로 보존했다.

```text
공식 URL: https://www.federalreserve.gov/releases/h10/releaseDates.json
공개일 최초 연도: 1996
공개일 최종 연도: 2026
공개일 수: 1,435
```

공휴일 이동과 비정기 추가 공개를 추정하지 않고 공식 날짜를 사용한다. 각 Broad Dollar 관측값에는 다음 규칙을 적용한다.

```text
h10_release_date
= 관측일이 속한 주의 일요일 이후 최초 공식 H.10 공개일

available_at_et
= h10_release_date 16:15 America/New_York

available_at_kst
= available_at_et을 Asia/Seoul로 변환한 시각

safe_from_krw_date
= available_at_kst의 날짜 + 1 calendar day
```

`safe_from_krw_date`를 하루 더 늦춘 이유는 ECOS USD/KRW 일별값의 전체 역사에 대한 정확한 관측·공개 시각이 확인되지 않았기 때문이다. 같은 한국 날짜 안에서 어떤 값이 먼저 공개됐는지 추측하지 않는다.

첫 행의 검증 결과:

```text
Broad Dollar 관측일: 2024-01-02
H.10 공식 공개일: 2024-01-08
available_at_et: 2024-01-08T16:15:00-05:00
available_at_kst: 2024-01-09T06:15:00+09:00
safe_from_krw_date: 2024-01-10
```

64행 모두 다음 조건을 통과했다.

- 공개일이 관측 주 종료 이후다.
- ET와 KST 시각 및 UTC offset이 보존됐다.
- 공개시점 관련 결측값이 없다.
- 관측 날짜 중복이 없다.
- 기존 빈 지수값 2건이 그대로 보존됐다.

유효 산출물:

```text
data/raw/fred/h10_release_dates_20260802T074312Z.json
data/processed/fred/broad_usd_index_availability_20240101_20240331_20260802T074312Z.csv
```

다음 파일은 첫 직렬화에서 시각과 UTC offset이 날짜로 축약된 결함이 있으므로 사용하지 않는다. 원인 추적을 위해 삭제하지 않았다.

```text
data/raw/fred/h10_release_dates_20260802T074158Z.json
data/processed/fred/broad_usd_index_availability_20240101_20240331_20260802T074158Z.csv
```

짧은 기간 검증 이후 아래와 같이 전체 기간 수집과 공개시점 적용을 진행했다. USD/KRW as-of 결합은 아직 수행하지 않았다.

## 전체 기간 수집 및 공개시점 적용 결과

전체 요청 범위 수집을 완료했다.

```text
요청 기간: 2006-01-02~2026-07-30
실제 반환 기간: 2006-01-02~2026-07-24
원본 행 수: 5,365
처리 행 수: 5,365
빈 값 행 수: 211
중복 날짜 행 수: 0
숫자 변환 실패 수: 0
기간 밖 행 수: 0
0 이하 값 수: 0
```

전체 공개시점 처리 결과:

```text
2009년 이전 공개시점 확인 필요: 785행
주간 H.10 공식 공개시점 적용: 4,580행
2009년 이후 공개시점 누락: 0행
2015년 이후 공개시점 미확인: 0행
```

2006-01-02~2008-12-31은 주간 H.10 중단과 일별 업데이트 체계가 포함된 구간이다. 현재 주간 공개일 규칙을 소급하지 않고 다음 값들을 비워 두었다.

```text
h10_release_date
available_at_et
available_at_kst
safe_from_krw_date
```

해당 행은 삭제하지 않았으며 `release_regime=pre-2009 daily-update availability not implemented`로 표시했다. 현재 Validation의 context 756은 2015년 이후 자료를 사용하므로 이 미확인 구간이 후보 실험 입력에는 포함되지 않는다.

마지막 관측 검증:

```text
관측일: 2026-07-24
H.10 공개일: 2026-07-27
available_at_et: 2026-07-27T16:15:00-04:00
available_at_kst: 2026-07-28T05:15:00+09:00
safe_from_krw_date: 2026-07-29
```

일광절약시간에 따라 ET offset과 한국 도착 시각은 계절별로 달라진다. 저장된 timezone-aware 시각을 사용하며 고정 시차를 하드코딩하지 않는다.

생성 파일:

```text
data/raw/fred/dtwexbgs_20060102_20260730_20260802T074701Z.csv
data/raw/fred/dtwexbgs_20060102_20260730_20260802T074701Z_metadata.json
data/processed/fred/broad_usd_index_20060102_20260730_20260802T074701Z.csv
data/processed/fred/broad_usd_index_availability_20060102_20260724_20260802T074709Z.csv
```

빈 지수값 211행은 원본과 처리본에 보존했다. 다음 as-of 결합에서는 이 행을 전일 값으로 채우거나 보간하지 않는다. 값이 존재하고 `safe_from_krw_date`가 지난 최신 실제 지수 관측만 USD/KRW 날짜에 연결한다.

전체 수집과 공개시점 적용 이후 아래와 같이 USD/KRW as-of 결합을 진행했다. Chronos 공변량 실험은 아직 수행하지 않았다.

## USD/KRW 누수 방지 as-of 결합 결과

각 USD/KRW 날짜에는 다음 조건을 만족하는 최신 유효 Broad Dollar 관측만 연결했다.

```text
broad_usd_safe_from_krw_date <= usd_krw_date
broad_usd_observation_date < usd_krw_date
broad_usd_index is not empty
```

결합 결과:

```text
기간: 2009-01-14~2026-07-30
결합 행 수: 4,342
USD 날짜 중복: 0
필수값 결측: 0
안전 사용일 위반: 0
현재·미래 Broad Dollar 관측 혼입: 0
사용된 Broad Dollar 실제 관측: 916개
한 실제 관측의 최대 반복: 8개 USD 날짜
공변량 관측 경과일 최대: 14일
```

같은 Broad Dollar 값이 다음 공식 발표 전까지 여러 USD/KRW 날짜에 반복되는 것은 빈 날짜에 값을 만들어 넣는 전일값 채우기가 아니다. 각 USD 날짜 당시 공식적으로 이용할 수 있었던 최신 상태를 as-of 방식으로 조회한 결과다. 어떤 실제 관측이 사용됐는지 `broad_usd_observation_date`로 추적할 수 있다.

제외 관측 감사 결과:

```text
release_availability_unresolved: 783행
empty_value: 209행
release_availability_unresolved;empty_value: 2행
합계: 994행
```

2018년 첫 Validation 기준일까지 결합 이력은 2,230행으로 context 756을 충족한다. 2015년 이후 공변량 결측 행은 없다.

마지막 결합 행:

```text
USD/KRW 날짜: 2026-07-30
Broad Dollar 관측일: 2026-07-24
Broad Dollar 값: 120.7105
H.10 공개일: 2026-07-27
KST 공개시각: 2026-07-28T05:15:00+09:00
안전 사용일: 2026-07-29
관측 경과일: 6일
```

생성 파일:

```text
data/processed/usd_broad_usd_covariates_weekdays_asof_20090114_20260730.csv
data/processed/audit/broad_usd_excluded_observations_20060102_20260724.csv
src/experiments/broad_usd/prepare_broad_usd_covariates.py
tests/test_prepare_broad_usd_covariates.py
```

as-of 모델 입력 후보 생성 이후 아래와 같이 Chronos-2 smoke test를 진행했다. Validation 성능 평가는 아직 수행하지 않았다.

## Chronos-2 과거 공변량 smoke test

개발 구간 기준일 하나에서 실제 MPS 예측을 완료했다.

```text
요청 기준일: 2017-11-01
실제 입력 종료일: 2017-11-01
입력 기간: 2014-10-13~2017-11-01
입력 행 수: 756
Prediction length: 20
Target 기간: 2017-11-02~2017-11-29
Device: MPS
Future covariates: 없음
```

입력 검증:

```text
broad_usd_safe_from_krw_date <= usd_krw_date: 전체 통과
broad_usd_observation_date < usd_krw_date: 전체 통과
입력 내 최대 공변량 관측 경과일: 13일
```

출력 검증:

```text
예측 행 수: 20
중복 target date: 0
비유한 값: 0
q0.1 <= q0.5 <= q0.9: 전체 통과
날짜 오름차순: 통과
```

단일 기준일 진단 MAE:

| 모델 | MAE |
|---|---:|
| Broad Dollar 공변량 Chronos | 16.579562원 |
| Random Walk | **15.835000원** |

이 수치는 입력·출력 연결을 확인한 단일 smoke 결과이므로 후보 채택 또는 탈락에 사용하지 않는다.

생성 파일:

```text
src/experiments/broad_usd/broad_usd_covariate_smoke.py
tests/test_broad_usd_covariate_smoke.py
outputs/forecasts/experiments/broad_usd/usd_krw_chronos2_broad_usd_asof_smoke_origin20171101.csv
```

smoke test 이후 아래와 같이 2018~2021 Validation 성능 평가를 진행했다.

## 2018~2021 Validation 결과

결과를 확인하기 전에 `configs/broad_usd_validation.json`에 다음 조건을 고정했다.

1. 단변량 수준값 Chronos보다 전체 MAE와 RMSE가 모두 낮아야 한다.
2. Random Walk보다 전체 MAE와 RMSE가 모두 낮아야 한다.
3. 48개 기준일 중 MAE와 RMSE를 각각 최소 25회 단변량보다 개선해야 한다.
4. 모든 Broad Dollar 관측일과 안전 사용일이 입력 날짜 조건을 충족해야 한다.

평가 설정:

```text
Validation: 2018~2021
기준일: 월별 48개
예측 행: 960
Context length: 756
Prediction length: 20
Device: MPS
Future covariates: 없음
Final Test 2022~2025: 미사용
```

전체 결과:

| 모델 | MAE | RMSE | 방향 정확도 |
|---|---:|---:|---:|
| Broad Dollar 공변량 Chronos | 11.996555 | **15.715258** | 62.08% |
| 단변량 Chronos | **11.968236** | 15.724912 | **63.65%** |
| Random Walk | 12.259792 | 15.967171 | 1.25% |

Broad Dollar 공변량은 Random Walk 대비 MAE 약 2.15%, RMSE 약 1.58% 개선됐다. 그러나 단변량 Chronos 대비 MAE는 약 0.24% 악화됐고 RMSE만 약 0.06% 개선됐다.

단변량 Chronos 대비 기준일별 승수:

```text
MAE: 23/48
RMSE: 27/48
사전 기준: 각각 최소 25/48
```

연도별 MAE:

| 연도 | Broad Dollar 공변량 | 단변량 Chronos | Random Walk |
|---:|---:|---:|---:|
| 2018 | **8.879827** | 8.920143 | 9.181250 |
| 2019 | **14.420967** | 14.462754 | 14.590833 |
| 2020 | **12.767069** | 12.805630 | 13.186250 |
| 2021 | 11.918356 | **11.684419** | 12.080833 |

2018~2020년에는 단변량보다 MAE가 소폭 개선됐지만 2021년 악화가 전체 결과를 상쇄했다.

예측 리드구간별 결과:

| 구간 | 공변량 MAE | 단변량 MAE | 공변량 RMSE | 단변량 RMSE |
|---|---:|---:|---:|---:|
| D+1~D+5 | **7.246106** | 7.263431 | **9.723564** | 9.753166 |
| D+6~D+10 | 11.423063 | **11.396811** | **14.670817** | 14.691018 |
| D+11~D+20 | 14.658525 | **14.606352** | **18.413266** | 18.413869 |

D+1~D+5에서는 MAE와 RMSE가 모두 소폭 개선됐지만 이후 구간 MAE는 나빠졌다. D+11~D+20 RMSE 차이는 약 0.0006원으로 실질적인 개선이라고 보기 어렵다.

예측구간:

```text
q0.1~q0.9 포함률: 74.17%
평균 구간 폭: 35.03원
명목 목표: 80%
```

목표 포함률에 미달했으므로 확정적인 80% 구간으로 해석하지 않는다.

판정:

```text
passed_candidate_entry_criteria: false
next_action: drop_broad_usd_covariate_candidate
```

Random Walk보다 전체 MAE·RMSE가 좋고 단변량보다 RMSE 및 일부 연도·리드구간이 개선됐지만, 사전에 정한 전체 조건을 모두 만족하지 못했다. 따라서 이 결과를 보고 조건을 낮추거나 context·정렬 규칙을 재탐색하지 않는다. Broad Dollar 후보는 2022~2025 최종 Test, LoRA 또는 앙상블 입력으로 넘기지 않는다.

Validation 생성 파일:

```text
configs/broad_usd_validation.json
src/experiments/broad_usd/evaluate_broad_usd_validation.py
tests/test_evaluate_broad_usd_validation.py
outputs/forecasts/experiments/broad_usd/usd_krw_chronos2_broad_usd_asof_h20_ctx756_validation_2018_2021.csv
outputs/metrics/experiments/broad_usd/usd_krw_chronos2_broad_usd_asof_h20_ctx756_validation_2018_2021_summary.csv
outputs/metrics/experiments/broad_usd/usd_krw_chronos2_broad_usd_asof_h20_ctx756_validation_2018_2021_by_origin.csv
outputs/metrics/experiments/broad_usd/usd_krw_chronos2_broad_usd_asof_h20_ctx756_validation_2018_2021_by_year.csv
outputs/metrics/experiments/broad_usd/usd_krw_chronos2_broad_usd_asof_h20_ctx756_validation_2018_2021_by_lead_segment.csv
outputs/metrics/experiments/broad_usd/usd_krw_chronos2_broad_usd_asof_h20_ctx756_validation_2018_2021_decision.json
```

## 공식 근거

- [FRED DTWEXBGS 시계열](https://fred.stlouisfed.org/series/DTWEXBGS)
- [Federal Reserve H.10 Nominal/Real Indexes](https://www.federalreserve.gov/releases/h10/summary/)
- [Federal Reserve H.10 About](https://www.federalreserve.gov/releases/H10/About.HTM)
- [Revisions to the Federal Reserve Dollar Indexes](https://www.federalreserve.gov/econres/notes/ifdp-notes/Revisions_to_the_Federal_Reserve_Dollar_Indexes_Jan_2019.pdf)
- [ICE FX Indices Methodology](https://www.ice.com/publicdocs/data/ICE_FX_Indexes_Methodology.pdf)
