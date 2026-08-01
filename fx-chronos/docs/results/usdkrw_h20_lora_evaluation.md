# USD/KRW 20영업일 Chronos-2 LoRA 평가 결과

## 1. 목적

USD/KRW 단변량 시계열에서 Amazon Chronos-2 Zero-shot, LoRA 파인튜닝, Random Walk를 비교했다. 설정 선택에는 Validation만 사용하고, 선택된 LoRA 후보는 고정된 최종 Test에서 한 번만 평가했다.

이 문서는 실험 결과 기록이며 특정 금융상품이나 환헤지 비율을 추천하지 않는다.

## 2. 데이터 분할

```text
개발·학습 이력: 2017년까지
Validation: 2018~2021년
최종 Test: 2022~2025년
Prediction length: 20개 실제 환율 관측일
```

월별 Walk-forward 기준일은 다음과 같이 배정했다.

| 구간 | 기준일 수 | 용도 |
| --- | ---: | --- |
| 개발·학습 이력 | 251 | 학습 데이터와 개발 진단 |
| Validation | 48 | context와 LoRA 후보 선택 |
| 최종 Test | 48 | 고정 후보의 최종 1회 평가 |
| 제외 | 1 | 목표 날짜가 분할 경계를 넘는 `2017-12-01` |

## 3. 실행 환경

```text
Model: amazon/chronos-2
chronos-forecasting: 2.3.1
Python: 3.14.6
PyTorch: 2.13.0
PEFT: 0.20.0
Training device: Apple Silicon MPS
LoRA rank: 8
LoRA alpha: 16
Batch size: 4
Seed: 42
```

MPS는 Codex 기본 샌드박스 안에서는 보이지 않았지만 같은 가상환경을 장치 접근이 허용된 실행 환경에서 사용했을 때 정상 동작했다. 100-step 벤치마크에서 MPS는 CPU보다 약 2.14배 빨랐다.

## 4. Zero-shot context 선택

Validation에서 `252`, `504`, `756`, `1260`, `8192`를 비교했다.

| Context | MAE | RMSE | Random Walk 대비 MAE | Random Walk 대비 RMSE |
| ---: | ---: | ---: | ---: | ---: |
| 252 | 12.6977 | 16.7105 | -3.572% | -4.655% |
| 504 | 12.0521 | 15.8206 | +1.694% | +0.918% |
| 756 | 11.9682 | 15.7249 | +2.378% | +1.517% |
| 1260 | 11.9630 | 15.7144 | +2.421% | +1.583% |
| 8192 | 12.8177 | 16.6270 | -4.551% | -4.132% |

`756`과 `1260`의 전체 MAE·RMSE 차이가 0.1% 미만이었고 `756`이 더 짧으면서 예측구간 포함률과 기준일별 RMSE 승률이 조금 더 좋아 `context_length=756`을 선택했다.

## 5. LoRA 후보 선택

Validation에서 다음 후보를 사전 계획 순서대로 비교했다.

| Learning rate | Steps | MAE | RMSE | Zero-shot 대비 MAE | Zero-shot 대비 RMSE |
| ---: | ---: | ---: | ---: | ---: | ---: |
| `1e-5` | 100 | 11.9708 | 15.7268 | -0.022% | -0.012% |
| `3e-5` | 100 | 11.9795 | 15.7350 | -0.094% | -0.064% |
| `1e-5` | 300 | 11.9608 | 15.7177 | +0.062% | +0.046% |

Validation에서 점 예측 지표가 가장 좋았던 다음 후보를 최종 Test 전에 고정했다.

```text
context_length=756
learning_rate=1e-5
num_steps=300
batch_size=4
seed=42
```

Zero-shot 대비 개선 폭은 MAE 0.062%, RMSE 0.046%에 불과했으므로 Validation 단계에서도 유의미한 우위라고 주장하지 않았다.

## 6. 최종 Test 결과

고정 후보를 2022~2025의 48개 월별 기준일, 총 960개 예측 행에서 한 번 평가했다.

| 모델 | MAE | RMSE |
| --- | ---: | ---: |
| LoRA | 21.3323 | 29.3673 |
| Zero-shot, context 756 | 21.3173 | 29.3309 |
| Random Walk | 20.7573 | 28.4835 |

LoRA 비교 결과는 다음과 같다.

| 비교 대상 | MAE 개선율 | RMSE 개선율 |
| --- | ---: | ---: |
| Zero-shot | -0.070% | -0.124% |
| Random Walk | -2.770% | -3.103% |

확률 예측 결과도 목표에 미달했다.

| 모델 | 평균 Pinball Loss | 80% 구간 포함률 | 평균 구간 폭 |
| --- | ---: | ---: | ---: |
| LoRA | 7.1843 | 67.60% | 51.16원 |
| Zero-shot | 7.1473 | 69.48% | 52.80원 |

LoRA의 기준일별 Zero-shot 대비 승률은 MAE 50.0%, RMSE 52.08%로 일관된 우위를 보여주지 못했다.

## 7. 판정

선택된 LoRA 후보는 최종 Test 성공 조건을 충족하지 못했다.

- LoRA가 Zero-shot보다 MAE와 RMSE 모두 나빴다.
- LoRA가 Random Walk보다 MAE와 RMSE 모두 나빴다.
- 예측구간 포함률이 명목 수준 80%에 미달했다.
- Validation의 매우 작은 개선이 독립된 최종 Test에서 재현되지 않았다.

따라서 현재 모델 사용 정책은 다음과 같다.

```text
필수 운영 기준 모델: Random Walk
Chronos-2 Zero-shot: 연구용 확률 예측 경로
Chronos-2 LoRA: 최종 Test 실패, 운영 기본 모델로 사용하지 않음
```

최종 Test 결과를 이용해 context, learning rate 또는 step을 다시 선택하지 않는다. 외생변수 실험을 진행하려면 기존 최종 Test에 반복 적합하지 않도록 새로운 검증 설계를 먼저 확정한다.

## 8. 근거 산출물

- 설정: `fx-chronos/configs/finetuning.json`
- context 비교: `fx-chronos/outputs/metrics/usd_krw_zero_shot_validation_context_comparison.csv`
- 선택 후보 Validation: `fx-chronos/outputs/metrics/chronos2_lora_h20_ctx756_lr1e-5_steps300_seed42_validation_summary.csv`
- 최종 Test 요약: `fx-chronos/outputs/metrics/chronos2_lora_h20_ctx756_lr1e-5_steps300_seed42_final_test_2022_2025_summary.csv`
- 최종 Test 기준일별 결과: `fx-chronos/outputs/metrics/chronos2_lora_h20_ctx756_lr1e-5_steps300_seed42_final_test_2022_2025_by_origin.csv`
- 최종 Test lead-step별 결과: `fx-chronos/outputs/metrics/chronos2_lora_h20_ctx756_lr1e-5_steps300_seed42_final_test_2022_2025_by_lead.csv`

