# USD/KRW 20영업일 축소 앙상블 2026년 고정 평가

## 1. 평가 목적

2018~2021 Validation에서 선택한 축소 앙상블 α=0.5가 새로운 2026년 관측 구간에서도 Random Walk보다 안정적인지 확인했다. 2026년 결과를 보기 전에 설정, 기준일과 성공 조건을 `fx-chronos/configs/ensemble.json`에 고정했다.

이 평가는 2022~2025 최종 Test를 α 선택에 재사용하지 않았다. 2026년 결과를 이용해 α를 다시 선택하지 않는다.

## 2. 사전 고정 설정

```text
α: 0.5
Chronos-2 context length: 756
prediction length: 20
요청 기준일: 2026년 1월~7월 매월 1일
기준일 수: 7
예측 행 수: 140
```

사전 성공 조건:

1. 전체 MAE와 RMSE가 Random Walk보다 모두 낮아야 한다.
2. 기준일별 MAE와 RMSE가 각각 최소 4/7 기준일에서 Random Walk보다 낮아야 한다.
3. 조건을 통과해도 기준일이 7개뿐이므로 `provisional_due_to_small_sample`로만 판정한다.
4. 실패해도 2026년 결과를 보고 α를 다시 탐색하지 않는다.

## 3. 전체 결과

| 모델 | MAE | RMSE |
|---|---:|---:|
| Random Walk | 36.080714 | 42.368323 |
| 축소 앙상블 α=0.5 | 34.872399 | 41.523387 |
| Chronos-2 Zero-shot | 33.679461 | 40.763084 |

축소 앙상블의 Random Walk 대비 개선율:

```text
MAE: 3.348924%
RMSE: 1.994264%
```

축소 앙상블은 Random Walk보다 개선됐지만 순수 Chronos-2 Zero-shot보다는 MAE가 3.542%, RMSE가 1.865% 나빴다.

## 4. 기준일별 결과

| 요청 기준일 | RW 대비 MAE 개선 | RW 대비 RMSE 개선 | 판정 |
|---|---:|---:|---|
| 2026-01-01 | 9.762% | 8.919% | 둘 다 개선 |
| 2026-02-01 | 11.559% | 10.037% | 둘 다 개선 |
| 2026-03-01 | 2.489% | 2.531% | 둘 다 개선 |
| 2026-04-01 | 0.558% | 0.068% | 둘 다 개선 |
| 2026-05-01 | 2.251% | 2.199% | 둘 다 개선 |
| 2026-06-01 | 6.802% | 5.941% | 둘 다 개선 |
| 2026-07-01 | -1.203% | -1.348% | 둘 다 악화 |

기준일별 MAE와 RMSE 승리 횟수는 각각 6/7이다.

## 5. 데이터 품질

```text
요청 기준일: 7개
전체 행: 140
기준일별 행: 20
최초 목표일: 2026-01-02
최종 목표일: 2026-07-30
중복 행: 0
결측값: 0
```

## 6. 판정

사전 등록한 전체 지표 조건과 기준일 일관성 조건을 모두 통과했다.

```text
passed_pre_registered_criteria: true
status: provisional_due_to_small_sample
```

그러나 7개 월별 기준일은 강한 일반화 주장을 하기에는 부족하다. 따라서 다음처럼 해석한다.

- α=0.5 축소 앙상블이 신규 2026년 소표본에서도 Random Walk를 개선했다.
- Validation에서 확인한 개선 가능성이 2026년 1~7월에도 잠정적으로 재현됐다.
- 축소 앙상블이 항상 Random Walk보다 우수하다고 확정하지 않는다.
- 순수 Chronos-2가 이 구간에서는 더 우수했지만, 이를 근거로 α를 1에 가깝게 다시 조정하지 않는다.
- 2026년 추가 관측이 쌓이면 같은 고정 설정으로 평가 기준일을 늘릴 수 있다.

## 7. 재현 파일

```text
설정
fx-chronos/configs/ensemble.json

실행 코드
fx-chronos/src/evaluate_locked_ensemble_2026.py

예측 결과
fx-chronos/outputs/forecasts/ensemble/usd_krw_shrunk_ensemble_h20_ctx756_alpha0.5_2026_locked.csv

요약 지표
fx-chronos/outputs/metrics/ensemble/usd_krw_shrunk_ensemble_h20_ctx756_alpha0.5_2026_locked_summary.csv

판정 기록
fx-chronos/outputs/metrics/ensemble/usd_krw_shrunk_ensemble_h20_ctx756_alpha0.5_2026_locked_decision.json
```
