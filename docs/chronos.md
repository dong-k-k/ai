# Chronos-2 모델 입출력 설계

본 프로젝트에서는 Amazon의 시계열 예측 모델인 `amazon/chronos-2`를 직접 사용한다. AutoGluon과 같은 별도 AutoML 프레임워크는 초기 구현 범위에서 제외하며, `Chronos2Pipeline`을 이용해 모델의 입력과 출력을 직접 제어한다.

## 현재 검증 결론

USD/KRW 단변량 20영업일 예측의 Zero-shot context 비교, LoRA 후보 선택, 고정 최종 Test를 완료했다. LoRA는 최종 Test에서 Zero-shot과 Random Walk를 개선하지 못했으므로 운영 기본 모델로 사용하지 않는다.

상세 설정, Validation 결과, 최종 Test 지표와 모델 사용 정책은 [USD/KRW 20영업일 Chronos-2 LoRA 평가 결과](results/usdkrw_h20_lora_evaluation.md)에 기록한다.

## 1. 모델이 기대하는 입력 형식

Chronos-2의 `predict()` 함수는 크게 세 가지 형태의 입력을 지원한다.

### 1.1 3차원 Tensor 또는 NumPy 배열

기본 입력 형태는 다음과 같다.

```text
(batch, n_variates, history_length)
```

각 차원의 의미는 다음과 같다.

* `batch`: 한 번에 처리할 시계열 묶음의 개수
* `n_variates`: 하나의 묶음 안에서 함께 예측할 타깃 변수의 개수
* `history_length`: 입력으로 제공하는 과거 관측값의 개수

단변량 시계열 32개가 각각 과거 값 100개를 가진 경우:

```python
inputs = torch.randn(32, 1, 100)
```

다변량 시계열 32개가 각각 3개의 변수와 과거 값 100개를 가진 경우:

```python
inputs = torch.randn(32, 3, 100)
```

`n_variates`가 1이면 단변량 예측을 수행한다. `n_variates`가 2 이상이면 같은 시계열 묶음 안의 변수 간 정보를 공유하는 다변량 예측을 수행한다.

본 프로젝트에서 USD/KRW 환율 시계열 하나만 입력하는 경우의 형태는 다음과 같다.

```python
inputs = torch.tensor(
    usdkrw_values,
    dtype=torch.float32,
).reshape(1, 1, -1)
```

```text
shape = (1, 1, history_length)
```

### 1.2 배열의 리스트

각 시계열을 Tensor 또는 NumPy 배열로 만든 뒤 리스트로 전달할 수도 있다.

```python
inputs = [
    torch.randn(100),
    torch.randn(150),
    torch.randn(120),
]
```

각 리스트 원소는 다음 두 형태 중 하나를 가질 수 있다.

```text
(history_length,)
```

단변량 입력을 의미한다.

```text
(n_variates, history_length)
```

다변량 입력을 의미한다.

리스트에 포함된 각 시계열의 `history_length`는 서로 달라도 된다. 길이가 다른 경우 Chronos-2가 필요한 만큼 왼쪽 패딩을 적용한다.

본 프로젝트에서 USD/KRW 시계열 하나만 사용하는 가장 단순한 입력은 다음과 같다.

```python
inputs = [
    np.array(usdkrw_values, dtype=np.float32)
]
```

초기 구현에서는 이 형태를 우선 사용한다.

### 1.3 공변량을 포함한 딕셔너리 리스트

보조 경제지표를 함께 입력할 경우 다음 구조를 사용한다.

```python
inputs = [
    {
        "target": usdkrw,
        "past_covariates": {
            "dxy": past_dxy,
            "vix": past_vix,
        },
        "future_covariates": {
            "holiday": future_holiday,
        },
    }
]
```

각 필드의 의미는 다음과 같다.

#### `target`

필수 값이며 실제 예측 대상이다.

단변량 타깃:

```text
(history_length,)
```

다변량 타깃:

```text
(n_variates, history_length)
```

#### `past_covariates`

선택 값이며 과거 시점에서 관측된 보조 변수이다.

```python
"past_covariates": {
    "dxy": past_dxy,
    "vix": past_vix,
}
```

각 공변량은 1차원 배열이어야 하며 길이는 `target`의 `history_length`와 같아야 한다.

```text
len(past_dxy) == history_length
len(past_vix) == history_length
```

#### `future_covariates`

선택 값이며 예측 시점에 미래 값까지 미리 알 수 있는 변수이다.

```python
"future_covariates": {
    "holiday": future_holiday,
}
```

각 배열의 길이는 `prediction_length`와 같아야 한다.

```text
len(future_holiday) == prediction_length
```

또한 `future_covariates`에 포함된 변수는 반드시 `past_covariates`에도 존재해야 한다.

```text
future_covariates의 키 ⊆ past_covariates의 키
```

예를 들어 휴일 여부의 미래 값을 사용하려면 과거 휴일 여부도 함께 제공해야 한다.

```python
inputs = [
    {
        "target": usdkrw,
        "past_covariates": {
            "dxy": past_dxy,
            "holiday": past_holiday,
        },
        "future_covariates": {
            "holiday": future_holiday,
        },
    }
]
```

여러 딕셔너리를 한 번에 전달할 경우 모든 딕셔너리는 동일한 구조를 가져야 한다.

* 동일한 `n_variates`
* 동일한 `past_covariates` 키
* 동일한 `future_covariates` 키

각 딕셔너리의 `history_length`는 서로 달라도 된다.

---

## 2. History Length와 Prediction Length 설정

### 2.1 History Length

`history_length`는 모델에 입력하는 과거 관측값의 개수이다.

예를 들어 USD/KRW 과거 영업일 데이터 504개를 입력하면 다음과 같다.

```text
history_length = 504
```

Chronos-2에서 `history_length`와 `context_length`는 구분해야 한다.

* `history_length`: 사용자가 실제로 입력한 과거 데이터 길이
* `context_length`: 모델이 추론 과정에서 참고하는 최대 과거 길이

Chronos-2의 최대 Context Length는 다음과 같다.

```text
최대 Context Length = 8192
```

과거 데이터를 500개 입력하면 모델은 최대 500개를 사용할 수 있다. 과거 데이터를 8192개보다 많이 입력하더라도 실제 추론에 사용하는 길이는 설정된 `context_length`에 의해 제한된다.

최대 길이인 8192개를 항상 사용하는 것이 가장 정확하다는 의미는 아니다. 환율 시장은 금리 체계, 정책 환경, 변동성 구조 등이 시간에 따라 달라질 수 있으므로 너무 오래된 데이터가 현재 예측에 불필요하거나 방해가 될 가능성도 있다.

따라서 본 프로젝트에서는 다음 History Length 후보를 실험한다.

```text
252개  ≈ 최근 1년
504개  ≈ 최근 2년
756개  ≈ 최근 3년
1260개 ≈ 최근 5년
```

예측 길이를 동일하게 고정한 뒤 각 History Length에 대한 백테스트 성능을 비교한다.

```text
History 252  → 동일한 미래 구간 예측
History 504  → 동일한 미래 구간 예측
History 756  → 동일한 미래 구간 예측
History 1260 → 동일한 미래 구간 예측
```

평가 지표로는 다음을 사용할 수 있다.

* MAE
* RMSE
* MASE
* 분위수 손실
* 환율 상승·하락 방향 정확도

최종 History Length는 모델의 최대 한도만 보고 정하는 것이 아니라, 반복 백테스트 결과가 가장 안정적인 값을 선택한다.

### 2.2 Prediction Length

`prediction_length`는 마지막 입력 시점 이후 몇 개의 미래 관측값을 생성할지를 의미한다.

```python
predictions = pipeline.predict(
    inputs=inputs,
    prediction_length=20,
)
```

일별 영업일 데이터에서 `prediction_length=20`은 달력 기준 20일이 아니라 미래 20개 영업일 관측값을 의미한다.

본 프로젝트에서는 다음 예측 길이를 우선 실험한다.

```text
5영업일  ≈ 약 1주
20영업일 ≈ 약 1개월
30영업일 ≈ 약 1.5개월
60영업일 ≈ 약 3개월 연구 대상
```

Chronos-2의 모델 기본 최대 Prediction Length는 다음과 같다.

```text
최대 Prediction Length = 1024
```

따라서 프로젝트에서 사용하는 5, 20, 30, 60영업일 예측은 모두 기본 모델 한도 안에 있다. 모델이 출력할 수 있다는 사실만으로 해당 horizon의 성능이 충분하다고 판단하지 않는다.

예측 길이는 모델이 자동으로 최적값을 정하는 항목이 아니라, 서비스가 제공하려는 예측 기간에 따라 결정한다. 예측 기간이 길어질수록 불확실성과 오차가 증가하므로 각 예측 길이를 별도로 백테스트해야 한다.

초기 실험 설정은 다음과 같다.

```text
데이터 빈도
- 일별 영업일 데이터

Prediction Length
- 서비스 후보: 5, 20, 30영업일
- 연구 대상: 60영업일
- 보류: 90, 120, 180, 252영업일

History Length 후보
- 252
- 504
- 756
- 1260

모델 한도
- 최대 Context Length: 8192
- 최대 Prediction Length: 1024
```

---

## 3. 예측값의 출력 형태

Chronos-2의 `predict()` 반환형은 다음과 같다.

```python
list[torch.Tensor]
```

입력에 포함된 각 타깃 시계열마다 하나의 Tensor가 리스트에 들어간다.

각 Tensor의 형태는 다음과 같다.

```text
(n_variates, n_quantiles, prediction_length)
```

각 축의 의미는 다음과 같다.

* `n_variates`: 예측 대상 타깃 변수의 개수
* `n_quantiles`: 모델이 출력하는 분위수의 개수
* `prediction_length`: 예측한 미래 시점의 개수

USD/KRW 단변량 시계열 하나를 미래 20영업일 동안 예측하고 모델이 9개의 분위수를 출력한다면 결과는 다음과 같다.

```text
list
└── torch.Tensor
    shape = (1, 9, 20)
```

실제 반환값은 다음과 같이 확인할 수 있다.

```python
predictions = pipeline.predict(
    inputs=[usdkrw],
    prediction_length=20,
)

print(type(predictions))
print(len(predictions))
print(predictions[0].shape)
```

예상 결과:

```text
<class 'list'>
1
torch.Size([1, 9, 20])
```

### 3.1 Chronos-2의 기본 출력은 분위수 예측

Chronos-2의 `predict()` 결과는 미래 샘플 경로가 아니라 분위수 예측이다.

기본 분위수는 모델 설정에 따라 다음과 같은 값으로 구성될 수 있다.

```text
0.1
0.2
0.3
0.4
0.5
0.6
0.7
0.8
0.9
```

각 분위수는 미래 환율 분포에서 해당 위치의 값을 의미한다.

```text
0.1 분위수
- 실제 미래 환율이 이 값보다 낮을 가능성이 약 10%인 하단 예측

0.5 분위수
- 예측 분포의 중앙값
- 프로젝트의 대표 포인트 예측값으로 사용 가능

0.9 분위수
- 실제 미래 환율이 이 값보다 낮을 가능성이 약 90%인 상단 예측
```

따라서 다음과 같은 예측 구간을 구성할 수 있다.

```text
하한 = 0.1 분위수
중앙 예측 = 0.5 분위수
상한 = 0.9 분위수
```

`0.1~0.9` 구간은 중앙 80% 예측 구간으로 해석할 수 있다.

### 3.2 평균과 샘플 출력 여부

`predict()` 함수가 직접 반환하는 값은 다음과 같다.

| 출력 종류    | 제공 여부                     |
| -------- | ------------------------- |
| 분위수 예측   | 제공                        |
| 중앙값      | 0.5 분위수로 제공               |
| 산술평균 예측  | `predict()`에서 별도로 제공하지 않음 |
| 미래 샘플 경로 | 기본 `predict()`에서 제공하지 않음  |
| 예측 구간    | 분위수 조합으로 생성 가능            |

따라서 프로젝트의 기본 출력은 다음 형태로 구성한다.

```text
예측 날짜
0.1 분위수 하한
0.5 분위수 중앙 예측
0.9 분위수 상한
```

예시:

```text
날짜         하한(q0.1)   중앙값(q0.5)   상한(q0.9)
2026-08-03   1378.4       1391.2          1405.8
2026-08-04   1375.1       1393.8          1412.4
```

특정 분위수를 꺼낼 때는 모델의 실제 분위수 순서를 확인한 뒤 사용해야 한다.

```python
forecast = predictions[0]

quantile_levels = [
    0.1, 0.2, 0.3, 0.4, 0.5,
    0.6, 0.7, 0.8, 0.9,
]

q10_index = quantile_levels.index(0.1)
q50_index = quantile_levels.index(0.5)
q90_index = quantile_levels.index(0.9)

q10 = forecast[0, q10_index, :]
q50 = forecast[0, q50_index, :]
q90 = forecast[0, q90_index, :]
```

---

## 4. 본 프로젝트의 단변량·다변량 결정

### 4.1 초기 모델: 단변량 예측

초기 구현에서는 USD/KRW 환율 종가만을 입력하고 미래 USD/KRW 환율을 예측한다.

```text
입력
- 과거 USD/KRW 종가

출력
- 미래 USD/KRW 종가
```

예측 대상 타깃이 하나이므로 단변량 시계열 예측에 해당한다.

```text
n_variates = 1
```

입력 예시는 다음과 같다.

```python
usdkrw = np.array(
    usdkrw_values,
    dtype=np.float32,
)

inputs = [usdkrw]
```

또는 3차원 형태로 다음과 같이 입력할 수 있다.

```python
inputs = torch.tensor(
    usdkrw_values,
    dtype=torch.float32,
).reshape(1, 1, -1)
```

초기 모델 구조는 다음과 같다.

```text
과거 USD/KRW 종가
        ↓
Chronos-2 단변량 예측
        ↓
미래 USD/KRW 분위수 예측
```

### 4.2 경제지표 추가 모델: 공변량 기반 단일 타깃 예측

이후 DXY, VIX, 금리, 유가 등을 추가하더라도 예측 대상이 USD/KRW 하나라면 타깃 기준으로는 단일 타깃 예측이다.

```text
예측 대상
- USD/KRW

보조 입력
- DXY
- VIX
- 한국 기준금리
- 미국 기준금리
- 국제유가
- KOSPI
```

이는 여러 타깃을 동시에 예측하는 다변량 타깃 예측이라기보다 다음과 같이 표현하는 것이 정확하다.

```text
공변량을 사용하는 단일 타깃 시계열 예측
```

입력 예시는 다음과 같다.

```python
inputs = [
    {
        "target": usdkrw,
        "past_covariates": {
            "dxy": dxy,
            "vix": vix,
            "kr_rate": kr_rate,
            "us_rate": us_rate,
        },
    }
]
```

DXY와 VIX의 미래 값을 현재 시점에 알 수 없다면 `future_covariates`가 아니라 `past_covariates`로만 전달해야 한다.

미래 공변량으로 사용할 수 있는 변수는 예측 시점에 미래 값이 확정된 변수이다.

```text
사용 가능한 미래 공변량 예시
- 요일
- 월말 여부
- 분기 말 여부
- 공휴일 여부
- 예정된 FOMC 회의일
- 예정된 한국은행 금융통화위원회 회의일
```

### 4.3 다변량 예측에 해당하는 경우

다음과 같이 여러 환율을 모두 예측 대상으로 지정할 경우 다변량 예측이 된다.

```text
예측 대상
- USD/KRW
- JPY/KRW
- EUR/KRW
```

입력 형태는 다음과 같다.

```text
(n_variates, history_length)
```

예:

```python
targets = np.stack([
    usdkrw,
    jpykrw,
    eurkrw,
])

inputs = [targets]
```

```text
shape = (3, history_length)
```

이 경우 `n_variates=3`이며 Chronos-2가 세 타깃의 정보를 공유하여 함께 예측한다.

현재 프로젝트의 초기 범위에서는 여러 환율을 동시에 예측할 필요가 없으므로 다변량 타깃 예측은 사용하지 않는다.

---

## 5. 프로젝트 최종 결정

현재 단계의 Chronos-2 모델 설정은 다음과 같다.

```text
모델
- amazon/chronos-2
- Chronos2Pipeline 직접 사용

데이터 빈도
- 일별 영업일 데이터

예측 대상
- USD/KRW 매매기준율

초기 모델 유형
- 단변량 시계열 예측

초기 입력 형태
- NumPy 1차원 배열을 담은 리스트
- [np.ndarray(history_length,)]

초기 Prediction Length
- 5영업일
- 20영업일
- 30영업일

추가 Prediction Length 실험
- 60영업일

보류
- 90영업일
- 120영업일
- 180영업일
- 252영업일

History Length 후보
- 252
- 504
- 756
- 1260

모델 한도
- 최대 Context Length: 8192
- 최대 Prediction Length: 1024

모델 출력
- list[torch.Tensor]
- 각 Tensor shape:
  (n_variates, n_quantiles, prediction_length)

프로젝트 주요 출력
- 0.1 분위수 하한
- 0.5 분위수 중앙 예측
- 0.9 분위수 상한

추후 확장
- DXY, VIX, 금리 등을 past_covariates로 추가
- 단변량 기본 모델과 공변량 모델의 백테스트 성능 비교
```

### 5.1 축소 앙상블 Validation 결과

Random Walk를 기준 경로로 두고 Chronos-2 Zero-shot 변화량을 축소 반영하는 단일 α 실험을 수행했다. Validation 2018~2021의 제한된 후보에서는 α=0.5가 선택됐고 Random Walk 대비 MAE 1.268%, RMSE 0.830% 개선됐다.

다만 2019년 RMSE가 소폭 악화됐고 α=0.5가 후보 상한이므로 운영 기본값이나 전역 최적값으로 확정하지 않는다. α=0.5를 신규 평가용 고정 연구 후보로 보존하며 현재 결과만으로 기간별 α를 추가 선택하지 않는다.

상세 결과는 `docs/results/usdkrw_h20_shrunk_ensemble_validation.md`에 기록한다.

### 5.2 2026년 고정 설정 평가

Validation에서 선택한 α=0.5를 변경하지 않고 2026년 1~7월의 월별 기준일 7개에서 평가했다. 축소 앙상블은 Random Walk 대비 MAE 3.349%, RMSE 1.994% 개선했고, 기준일별 MAE와 RMSE에서 각각 6/7회 우수해 사전 등록 조건을 통과했다.

다만 기준일이 7개뿐이므로 결과는 `provisional_due_to_small_sample`로 판정한다. 순수 Chronos-2 Zero-shot이 이 구간에서 앙상블보다 우수했더라도 2026년 결과를 이용해 α를 다시 선택하지 않는다.

상세 결과는 `docs/results/usdkrw_h20_shrunk_ensemble_2026_locked.md`에 기록한다.

### 5.3 환위험 계산 엔진

공통 `ForecastScenario`를 입력받아 지급·수취 계약의 시나리오별 원화 금액, 현재 기준환율 대비 손익과 완전 무헤지 대비 헤지 효과를 계산하는 엔진을 구현했다. 예측 모델은 계산 함수와 분리하며 지급·수취 가상 계약의 JSON·CSV 내보내기와 손익 부호 대칭성을 검증했다.

은행 스프레드, 수수료, 세금, 실제 금융상품 조건은 포함하지 않으며 특정 상품이나 최적 헤지 비율을 추천하지 않는다.

상세 계산 정의와 예시는 `docs/results/usdkrw_hedge_analysis_examples.md`에 기록한다.

### 5.4 예측구간 내부 보정

Chronos-2 context 756의 q0.1~q0.9 Validation 포함률은 73.65%로 목표 80%를 과소포착했다. 2018~2019를 보정 구간, 2020~2021을 내부 평가 구간으로 고정하고 전역 대칭 additive conformal widening을 적용했다.

상·하단을 각각 3.0085원 확장하자 내부 평가 포함률은 74.79%에서 82.71%로 증가했고 평균 폭은 16.39% 넓어졌다. 전체 내부 기준은 통과했지만 2020년 포함률은 76.25%에 그쳤으므로 모든 시장 국면에서 보정됐다고 주장하지 않는다.

context 756은 전체 Validation을 보고 선택했으므로 이 결과는 완전한 미관측 Test가 아니다. 현재 환위험 출력의 기본 구간으로 교체하지 않고 고정 보정값의 신규 평가 전까지 연구 후보로 보존한다.

상세 결과는 `docs/results/usdkrw_h20_interval_calibration_internal.md`에 기록한다.

### 5.5 고정 구간 보정의 2026년 평가

2018~2019에서 계산한 보정값 3.0085원을 변경하지 않고 2026년 1~7월 기준일 7개에 적용했다. 포함률은 54.29%에서 57.86%로만 증가해 사전 목표 80%에 크게 미달했다. 평균 구간 폭은 9.72% 증가했다.

내부 평가에서 확인한 82.71% 포함률은 2026년 소표본에서 재현되지 않았다. 따라서 보정 구간을 기본 80% 구간으로 채택하지 않고 원래 Chronos 분위수와 함께 참고용 위험 시나리오로만 유지한다. 이 결과를 보고 보정값이나 lead별 값을 다시 선택하지 않는다.

상세 결과는 `docs/results/usdkrw_h20_interval_calibration_2026_locked.md`에 기록한다.
