# USD/KRW 60영업일 고정 축소 앙상블 Validation

## 목적

20영업일 Validation에서 선택한 `α=0.5`를 다시 선택하지 않고 60영업일 예측에 그대로 적용해 Random Walk보다 안정적으로 개선되는지 확인했다. 순수 Chronos-2는 앙상블 변화 경로를 생성하는 구성 요소이며 최종 판정 대상은 축소 앙상블이다.

```text
앙상블 예측(h)
= 마지막 관측 환율
+ 0.5 × [Chronos-2 예측(h) - 마지막 관측 환율]
```

## 고정 조건

```text
통화: USD/KRW
Validation 목표 기간: 2018-01-01~2021-12-31
월별 요청 기준일: 2018-01-01~2021-10-01
기준일: 46개
예측 길이: 60개 실제 평일 관측
전체 행: 2,760
context length: 756
alpha: 0.5
device: MPS
cross learning: false
2022~2025 최종 Test 사용: 없음
```

2021년 11월과 12월 요청 기준일은 60번째 목표 관측이 2022년 최종 Test 구간으로 넘어가므로 제외했다. 최초 목표일은 2018-01-02, 최종 목표일은 2021-12-28이다.

입력 데이터와 H20 α 선택 기록의 경로 및 SHA-256은 `configs/h60_ensemble_validation.json`에 고정했다. H60 결과를 보고 α를 다시 선택하지 않는다.

## 사전 통과 조건

다음 조건을 모두 만족해야 한다.

1. Random Walk보다 전체 MAE가 낮다.
2. Random Walk보다 전체 RMSE가 낮다.
3. 기준일별 MAE 승리가 최소 24/46이다.
4. 기준일별 RMSE 승리가 최소 24/46이다.

## 결과

| 모델 | MAE(원) | RMSE(원) |
|---|---:|---:|
| 고정 α=0.5 축소 앙상블 | 19.842420 | 26.451518 |
| 순수 Chronos-2 | 19.700573 | 26.299360 |
| Random Walk | 20.017355 | 26.630793 |

앙상블은 Random Walk 대비 MAE 0.873917%, RMSE 0.673184% 개선됐다. 기준일별 승리는 MAE 25/46, RMSE 25/46으로 사전 기준을 통과했다. 방향 정확도는 0.624638이다.

순수 Chronos-2가 앙상블보다 MAE 0.720017%, RMSE 0.578563% 좋았지만, 순수 모델을 다시 운영 후보로 선택하거나 α를 H60에 맞춰 확대하지 않는다. 이번 검증은 H20에서 고정된 축소 정책의 H60 이전 가능성을 평가한 것이다.

## 품질 검사와 판정

```text
중복 행: 0
결측값: 0
Validation 기간 밖 목표일: 0
기준일별 forecast step: 60
alpha 값: 0.5만 존재
날짜 정렬: 통과
passed_h60_service_candidate_criteria: true
next_action: retain_h60_ensemble_candidate
```

따라서 고정 α=0.5 축소 앙상블을 USD/KRW 60영업일 서비스 후보로 유지한다. 개선 폭은 1% 미만이므로 Random Walk보다 큰 우위가 확정됐다고 과장하지 않으며, 아직 운영 기본값으로 확정한 것은 아니다.

## 산출물

```text
configs/h60_ensemble_validation.json
src/evaluation/evaluate_h60_locked_ensemble.py
outputs/forecasts/ensemble/usd_krw_shrunk_ensemble_h60_ctx756_alpha0.5_validation_2018_2021.csv
outputs/metrics/ensemble/usd_krw_shrunk_ensemble_h60_ctx756_alpha0.5_validation_2018_2021_summary.csv
outputs/metrics/ensemble/usd_krw_shrunk_ensemble_h60_ctx756_alpha0.5_validation_2018_2021_by_origin.csv
outputs/metrics/ensemble/usd_krw_shrunk_ensemble_h60_ctx756_alpha0.5_validation_2018_2021_by_lead.csv
outputs/metrics/ensemble/usd_krw_shrunk_ensemble_h60_ctx756_alpha0.5_validation_2018_2021_decision.json
```
