# USD/KRW 20영업일 고정 구간 보정 2026년 평가

## 1. 목적

2018~2019 보정 구간에서 계산한 고정 보정값 3.008544921875원을 변경하지 않고 2026년 1~7월의 월별 기준일 7개에 적용했다.

```text
보정 하한 = Chronos q0.1 - 3.008544921875원
보정 중앙 = Chronos q0.5 유지
보정 상한 = Chronos q0.9 + 3.008544921875원
```

2026년 결과를 보고 보정값이나 방법을 다시 선택하지 않는다.

## 2. 평가 성격

보정값은 2018~2019만 사용해 계산했으며 2026년 관측치는 보정값 산정에 사용하지 않았다. 따라서 보정 구간 밖의 평가다.

다만 2026년 실제값은 이전 점 예측 평가와 시각화에서 이미 확인했다. 그러므로 완전히 미관측인 pristine test라고 표현하지 않는다.

## 3. 사전 고정 조건

```text
목표 포함률: 80%
요청 기준일: 2026년 1월~7월 매월 1일
기준일: 7개
기준일별 행: 20
전체 행: 140
보정값: 3.008544921875원
성공 조건: 전체 보정 포함률이 80% 이상
```

기준일별·lead별 결과는 모두 보고하지만 각각의 표본이 작으므로 추가 합격 조건이나 보정값 선택에 사용하지 않았다.

## 4. 전체 결과

| 항목 | 보정 전 | 보정 후 | 변화 |
|---|---:|---:|---:|
| 포함률 | 54.2857% | 57.8571% | +3.5714%p |
| 평균 구간 폭 | 61.9240원 | 67.9411원 | +6.0171원 |

평균 폭은 9.72% 증가했지만 포함률은 목표 80%에 크게 미달했다.

보정 후 이탈 방향:

```text
하한 아래 이탈: 22.8571%
상한 위 이탈: 19.2857%
```

양쪽 방향 모두 이탈이 컸으므로 단순히 한 방향으로만 치우친 문제는 아니다.

## 5. 기준일별 결과

| 요청 기준일 | 보정 전 포함률 | 보정 후 포함률 | 목표 달성 |
|---|---:|---:|---|
| 2026-01-01 | 85% | 95% | 달성 |
| 2026-02-01 | 75% | 80% | 달성 |
| 2026-03-01 | 0% | 5% | 미달 |
| 2026-04-01 | 20% | 20% | 미달 |
| 2026-05-01 | 90% | 95% | 달성 |
| 2026-06-01 | 85% | 85% | 달성 |
| 2026-07-01 | 25% | 25% | 미달 |

7개 기준일 중 4개는 80% 이상이었지만, 3월·4월·7월 기준일의 포함률이 매우 낮아 전체 포함률이 57.86%에 그쳤다.

## 6. Lead별 결과 요약

20개 lead 중 목표 80% 이상을 기록한 lead는 D+1 한 개뿐이었다. 각 lead에는 기준일 7개의 관측만 있으므로 개별 비율의 변동성이 매우 크다.

```text
D+1 보정 포함률: 85.71%
나머지 lead 보정 포함률: 42.86%~71.43%
```

이 결과를 이용해 lead별 보정값을 새로 선택하지 않는다.

## 7. 판정

```text
passed_pre_registered_rule: false
status: out_of_calibration_rule_not_met_do_not_retune
interval_correction_was_reselected: false
point_forecast_changed: false
```

현재 결론:

- 3.0085원의 고정 대칭 보정은 2026년 전체 포함률을 목표 80%까지 높이지 못했다.
- 내부 평가에서 82.71%를 기록했던 개선은 2026년 소표본에서 재현되지 않았다.
- 전역 고정 폭 확장만으로 시장 국면 변화와 큰 수준 오차를 안정적으로 포착하지 못했다.
- 보정된 구간을 환위험 분석의 기본 구간이나 검증된 80% 구간으로 사용하지 않는다.
- 원래 Chronos 분위수와 보정 구간 모두 참고용 위험 시나리오로만 유지한다.
- 2026년 결과를 보고 보정값을 확대하거나 기간별 값을 새로 선택하지 않는다.

## 8. 재현 파일

```text
고정 설정
fx-chronos/configs/interval_calibration.json

실행 코드
fx-chronos/src/evaluate_locked_interval_2026.py

보정 예측
fx-chronos/outputs/forecasts/usd_krw_chronos2_h20_ctx756_interval_correction3.0085_2026_locked.csv

요약 지표
fx-chronos/outputs/metrics/usd_krw_chronos2_h20_ctx756_interval_correction3.0085_2026_locked_summary.csv

기준일별 지표
fx-chronos/outputs/metrics/usd_krw_chronos2_h20_ctx756_interval_correction3.0085_2026_locked_by_origin.csv

lead별 지표
fx-chronos/outputs/metrics/usd_krw_chronos2_h20_ctx756_interval_correction3.0085_2026_locked_by_lead.csv

판정 기록
fx-chronos/outputs/metrics/usd_krw_chronos2_h20_ctx756_interval_correction3.0085_2026_locked_decision.json
```
