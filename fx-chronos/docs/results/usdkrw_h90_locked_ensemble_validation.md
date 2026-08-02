# USD/KRW 90영업일 고정 축소 앙상블 Validation

## 목적과 고정 조건

20영업일에서 선택한 `α=0.5`를 변경하지 않고 90영업일에 적용해 Random Walk보다 전체 MAE와 RMSE가 조금이라도 낮은지 검증했다.

```text
앙상블 예측(h)
= 마지막 관측 환율
+ 0.5 × [Chronos-2 예측(h) - 마지막 관측 환율]

Validation 목표 기간: 2018-01-01~2021-12-31
월별 요청 기준일: 2018-01-01~2021-08-01
기준일: 44개
예측 길이: 90개 실제 평일 관측
전체 행: 3,960
context length: 756
alpha: 0.5
device: MPS
cross learning: false
2022~2025 최종 Test 사용: 없음
```

2021년 9~12월 요청 기준일은 90번째 목표 관측이 2022년으로 넘어가므로 제외했다. 최초 목표일은 2018-01-02, 최종 목표일은 2021-12-13이다. 입력 데이터와 H20 α 선택 기록의 SHA-256은 `configs/h90_ensemble_validation.json`에 고정했다.

사전 통과 조건은 Random Walk보다 전체 MAE와 RMSE가 모두 낮은 것이다. 기준일별 승리 횟수는 일관성 진단으로 보고하되 사용자 결정에 따라 단독 탈락 조건으로 사용하지 않았다.

## 결과

| 모델 | MAE(원) | RMSE(원) |
|---|---:|---:|
| 고정 α=0.5 축소 앙상블 | 25.141474 | 33.007104 |
| 순수 Chronos-2 | 24.989364 | 32.869268 |
| Random Walk | 25.336490 | 33.177991 |

앙상블은 Random Walk 대비 MAE 0.769704%, RMSE 0.515061% 우수했다. 기준일별 승리는 MAE 25/44, RMSE 27/44이며 방향 정확도는 0.627525다.

순수 Chronos-2 수치가 앙상블보다 낮지만 순수 모델을 운영 후보로 다시 선택하거나 H90 결과로 α를 확대하지 않는다. 최종 판정 대상은 기존 축소 정책을 그대로 이전한 α=0.5 앙상블이다.

## 품질 검사와 판정

```text
중복 행: 0
결측값: 0
Validation 기간 밖 목표일: 0
기준일별 forecast step: 90
alpha 값: 0.5만 존재
날짜 정렬: 통과
passed_h90_service_candidate_criteria: true
next_action: include_h90_service_candidate
```

따라서 90영업일 고정 축소 앙상블을 서비스 예측 기간에 포함한다. Random Walk 대비 성능은 소폭 우수하며 개선 폭이 1% 미만이라는 수치도 함께 보고한다.

## 산출물

```text
configs/h90_ensemble_validation.json
src/evaluation/evaluate_h90_locked_ensemble.py
outputs/forecasts/ensemble/usd_krw_shrunk_ensemble_h90_ctx756_alpha0.5_validation_2018_2021.csv
outputs/metrics/ensemble/usd_krw_shrunk_ensemble_h90_ctx756_alpha0.5_validation_2018_2021_summary.csv
outputs/metrics/ensemble/usd_krw_shrunk_ensemble_h90_ctx756_alpha0.5_validation_2018_2021_by_origin.csv
outputs/metrics/ensemble/usd_krw_shrunk_ensemble_h90_ctx756_alpha0.5_validation_2018_2021_by_lead.csv
outputs/metrics/ensemble/usd_krw_shrunk_ensemble_h90_ctx756_alpha0.5_validation_2018_2021_decision.json
```
