# USD/KRW 20영업일 로그수익률 Chronos-2 Validation

## 평가 설정

```text
Target input: log(USD/KRW_t / USD/KRW_t-1)
Level reconstruction: S_origin × exp(cumulative predicted q0.5 log returns)
Validation: 2018~2021
기준일: 월별 48개
예측 행: 960
Context length: 756 log returns
Prediction length: 20
Device: MPS
```

2022~2025 최종 Test는 읽거나 설정 선택에 사용하지 않았다. Chronos-2의 시점별 주변 로그수익률 분위수를 단순 누적한 값은 올바른 환율 경로 분위수라고 보장할 수 없으므로 이번 실험에서는 중앙 예측만 평가했다.

## 사전 진입 조건

결과 확인 전에 `configs/log_return_validation.json`에 다음 조건을 고정했다.

1. 기존 수준값 Chronos보다 전체 MAE와 RMSE가 모두 낮아야 한다.
2. Random Walk보다 전체 MAE와 RMSE가 모두 낮아야 한다.
3. 48개 기준일 중 MAE와 RMSE를 각각 최소 25회 수준값 Chronos보다 개선해야 한다.
4. 모든 실제 예측 기준일이 기존 Validation과 일치해야 한다.

## 전체 결과

| 모델 | MAE | RMSE | 방향 정확도 |
|---|---:|---:|---:|
| 로그수익률 Chronos | 12.329340 | 16.059776 | 50.00% |
| 수준값 Chronos | **11.968236** | **15.724912** | **63.65%** |
| Random Walk | 12.259792 | 15.967171 | 1.25% |

로그수익률 모델은 수준값 Chronos보다 MAE 3.017%, RMSE 2.130% 악화됐고 Random Walk보다도 MAE 0.567%, RMSE 0.580% 악화됐다.

수준값 Chronos 대비 기준일 승리 횟수:

```text
MAE: 17/48
RMSE: 17/48
사전 기준: 각각 최소 25/48
```

## 연도별 MAE

| 연도 | 로그수익률 Chronos | 수준값 Chronos | Random Walk |
|---:|---:|---:|---:|
| 2018 | 9.060321 | **8.920143** | 9.181250 |
| 2019 | 15.085349 | **14.462754** | 14.590833 |
| 2020 | **12.636587** | 12.805630 | 13.186250 |
| 2021 | 12.535103 | **11.684419** | 12.080833 |

2020년에만 수준값 Chronos와 Random Walk를 모두 개선했다. 2018년에는 Random Walk보다 좋았지만 수준값 Chronos보다 나빴고, 2019년과 2021년에는 두 비교 모델보다 모두 나빴다.

## 예측 구간별 결과

| 구간 | 로그수익률 MAE | 수준값 MAE | 로그수익률 RMSE | 수준값 RMSE |
|---|---:|---:|---:|---:|
| D+1~D+5 | 7.370595 | **7.263431** | 9.886946 | **9.753166** |
| D+6~D+10 | 11.754209 | **11.396811** | 15.101362 | **14.691018** |
| D+11~D+20 | 15.096278 | **14.606352** | 18.786468 | **18.413869** |

세 구간 모두 MAE와 RMSE가 수준값 Chronos보다 나빴다.

## 판정

```text
passed_candidate_entry_criteria: false
next_action: drop_log_return_target_candidate
```

로그수익률 변환·예측·수준 복원 파이프라인 자체는 정상 동작했지만 성능 진입 조건을 하나도 통과하지 못했다. 따라서 이 후보를 추가 Validation, 최종 Test, LoRA 또는 앙상블 입력으로 넘기지 않는다.

## 재현 파일

```text
configs/log_return_validation.json
src/experiments/log_return/log_return_smoke.py
src/experiments/log_return/evaluate_log_return_validation.py
tests/test_log_return_smoke.py
tests/test_evaluate_log_return_validation.py
outputs/forecasts/experiments/log_return/usd_krw_chronos2_log_return_h20_ctx756_validation_2018_2021.csv
outputs/metrics/experiments/log_return/usd_krw_chronos2_log_return_h20_ctx756_validation_2018_2021_summary.csv
outputs/metrics/experiments/log_return/usd_krw_chronos2_log_return_h20_ctx756_validation_2018_2021_by_origin.csv
outputs/metrics/experiments/log_return/usd_krw_chronos2_log_return_h20_ctx756_validation_2018_2021_by_year.csv
outputs/metrics/experiments/log_return/usd_krw_chronos2_log_return_h20_ctx756_validation_2018_2021_by_lead_segment.csv
outputs/metrics/experiments/log_return/usd_krw_chronos2_log_return_h20_ctx756_validation_2018_2021_decision.json
```
