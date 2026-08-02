# USD/KRW 20영업일 JPY/KRW lag1 과거 공변량 Validation

## 1. 평가 대상

USD/KRW만 미래 예측 타깃으로 유지하고 JPY/KRW는 과거 공변량으로만 사용했다. JPY/KRW의 정확한 당일 공개 시각이 전체 기간에 대해 확인되지 않았으므로 직전 실제 공통 관측값을 한 시점 지연한 `lag1`을 사용했다.

```text
Target: USD/KRW
Past covariate: JPY/KRW lag1 observation
Future covariates: 없음
Validation: 2018~2021
기준일: 월별 48개
예측 행: 960
Context length: 756
Prediction length: 20
Device: MPS
CNY/KRW: 사용하지 않음
```

2022~2025 최종 Test는 읽거나 설정 선택에 사용하지 않았다.

## 2. 사전 진입 조건

결과 확인 전에 `configs/covariate_validation.json`에 다음 조건을 고정했다.

1. 단변량 Chronos보다 전체 MAE와 RMSE가 모두 낮아야 한다.
2. Random Walk 대비 MAE·RMSE 격차가 모두 줄거나 Random Walk를 이겨야 한다.
3. 48개 기준일 중 MAE와 RMSE를 각각 최소 25회 단변량보다 개선해야 한다.
4. 모든 JPY source date가 해당 USD 입력 날짜보다 과거여야 한다.

## 3. 전체 결과

| 모델 | MAE | RMSE | 방향 정확도 |
|---|---:|---:|---:|
| JPY lag1 공변량 Chronos | 12.050549 | 15.781493 | 60.10% |
| 단변량 Chronos | **11.968236** | **15.724912** | **63.65%** |
| Random Walk | 12.259792 | 15.967171 | 1.25% |

JPY 공변량 모델은 Random Walk 대비 MAE 1.707%, RMSE 1.163% 개선됐다. 그러나 단변량 Chronos보다 MAE 0.688%, RMSE 0.360% 악화됐다.

단변량 대비 기준일 승리 횟수:

```text
MAE: 22/48
RMSE: 24/48
사전 기준: 각각 최소 25/48
```

## 4. 연도별 결과

| 연도 | JPY 공변량 MAE | 단변량 MAE | JPY 공변량 RMSE | 단변량 RMSE |
|---:|---:|---:|---:|---:|
| 2018 | 8.967679 | **8.920143** | **12.504139** | 12.649948 |
| 2019 | 14.496146 | **14.462754** | 17.972744 | **17.884101** |
| 2020 | 13.002988 | **12.805630** | 17.948290 | **17.787714** |
| 2021 | 11.735381 | **11.684419** | 13.953779 | **13.886193** |

4개 연도 모두 MAE가 단변량보다 나빴다. RMSE는 2018년에만 공변량 모델이 소폭 좋았고 나머지 세 연도에서는 나빴다.

## 5. 예측 구간별 결과

| 구간 | JPY 공변량 MAE | 단변량 MAE | JPY 공변량 RMSE | 단변량 RMSE |
|---|---:|---:|---:|---:|
| D+1~D+5 | 7.294273 | **7.263431** | **9.740046** | 9.753166 |
| D+6~D+10 | 11.501653 | **11.396811** | 14.785383 | **14.691018** |
| D+11~D+20 | 14.703134 | **14.606352** | 18.476282 | **18.413869** |

세 구간 모두 MAE가 단변량보다 나빴다. D+1~D+5 RMSE만 공변량 모델이 소폭 좋았다.

## 6. 예측 구간

```text
q0.1~q0.9 포함률: 74.17%
평균 구간 폭: 35.73원
목표 포함률: 80%
```

목표 포함률에 미달했으므로 공변량 모델의 분위수도 확정적인 80% 구간으로 해석하지 않는다.

## 7. 판정

```text
passed_candidate_entry_criteria: false
next_action: drop_jpy_covariate_and_do_not_run_lora
```

- 단변량 Chronos보다 전체 MAE와 RMSE가 모두 나빴다.
- 기준일별 승리 횟수가 사전 기준에 미달했다.
- 연도별·예측 구간별로 반복적인 개선이 확인되지 않았다.
- JPY source date는 모두 USD 입력 날짜보다 과거였고 미래 JPY 값은 사용하지 않았다.

따라서 JPY/KRW lag1 공변량은 축소 앙상블 후보로 올리지 않으며 이 입력 구조에 LoRA를 적용하지 않는다. 이 결과를 보고 lag, context 또는 공변량 구조를 다시 선택하지 않는다.

## 8. 재현 파일

```text
설정
configs/covariate_validation.json

정렬 코드
src/experiments/jpy/prepare_covariates.py

smoke 및 Validation 코드
src/experiments/jpy/covariate_smoke.py
src/experiments/jpy/evaluate_covariate_validation.py

예측 결과
outputs/forecasts/experiments/jpy/usd_krw_chronos2_jpy_lag1_h20_ctx756_validation_2018_2021.csv

지표와 판정
outputs/metrics/experiments/jpy/usd_krw_chronos2_jpy_lag1_h20_ctx756_validation_2018_2021_summary.csv
outputs/metrics/experiments/jpy/usd_krw_chronos2_jpy_lag1_h20_ctx756_validation_2018_2021_by_origin.csv
outputs/metrics/experiments/jpy/usd_krw_chronos2_jpy_lag1_h20_ctx756_validation_2018_2021_by_year.csv
outputs/metrics/experiments/jpy/usd_krw_chronos2_jpy_lag1_h20_ctx756_validation_2018_2021_by_lead_segment.csv
outputs/metrics/experiments/jpy/usd_krw_chronos2_jpy_lag1_h20_ctx756_validation_2018_2021_decision.json
```
