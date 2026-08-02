# FX Chronos 재현성 기록

ECOS의 USD/KRW 일별 매매기준율을 수집하고, 평일 관측 시계열을 이용해 Random Walk와 Amazon Chronos-2를 시간순 Walk-forward 방식으로 비교하는 프로젝트다. 예측 결과는 향후 환위험 시나리오와 원화 손익 계산에 연결한다.

## 현재 결론

USD/KRW 20영업일 최종 Test(2022~2025)에서는 Random Walk가 Chronos-2 Zero-shot과 선택된 LoRA 후보보다 낮은 MAE와 RMSE를 기록했다. 현재 데이터 분할과 LoRA 설정에서는 일반화 가능한 성능 개선이 확인되지 않았다.

- Random Walk: 필수 기준 모델이며 현재 가장 안정적인 점 예측 기준
- Chronos-2 Zero-shot: 변화 경로와 참고용 분위수 시나리오를 생성하는 AI 후보
- Chronos-2 LoRA: 연구 결과로 보존하며 현재 운영 모델로 사용하지 않음

상세 수치와 해석은 [`results/usdkrw_h20_lora_evaluation.md`](results/usdkrw_h20_lora_evaluation.md)에 기록돼 있다.

## 검증된 환경

```text
OS: macOS, Apple Silicon arm64
Python: 3.14.6
NumPy: 2.5.1
pandas: 3.0.5
matplotlib: 3.11.1
PyTorch: 2.13.0
chronos-forecasting: 2.3.1
PEFT: 0.20.0
```

저장소 루트의 `.venv`는 Python 3.9.6이며 위 패키지가 설치된 실험 환경이 아니다. 프로젝트 명령에는 `fx-chronos/.venv`를 사용한다.

## 환경 구성

저장소 루트에서 다음과 같이 별도 가상환경을 만든다.

```bash
cd fx-chronos
python3.14 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

설치 확인:

```bash
.venv/bin/python --version
.venv/bin/python -m pip check
.venv/bin/python -m pip show torch chronos-forecasting peft
```

`amazon/chronos-2` 모델은 첫 예측 실행 시 내려받을 수 있으므로 네트워크와 저장 공간이 필요하다. MPS는 제한된 샌드박스에서 보이지 않을 수 있다. 현재 Mac에서는 샌드박스 밖에서 MPS 텐서 생성이 확인됐으며, 실패하면 CPU를 사용한다.

## 환경변수

ECOS 수집에 다음 환경변수가 필요하다.

```text
ECOS_API_KEY
```

실제 키는 저장소, 명령 출력, 로그에 기록하지 않는다. `collect_ecos.py`는 실행 환경 또는 상위 경로의 기존 환경 설정에서 키를 읽으며, 출력 URL에서는 키를 가린다.

## 데이터 정책

- ECOS 원본 응답은 `data/raw/ecos/`에 그대로 보존한다.
- 가공된 ECOS CSV는 `data/processed/ecos/`에 저장한다.
- 모델 입력은 월요일~금요일의 실제 관측 행만 사용한다.
- 주말 관측은 삭제하지 않고 감사 CSV로 분리한다.
- 존재하지 않는 공휴일·평일 행을 새로 만들지 않는다.
- 전일값 채우기와 선형보간을 하지 않는다.
- 모델의 1 step은 다음 실제 평일 환율 관측 시점이다.

현재 주요 입력 파일:

```text
data/processed/ecos/usdkrw_19640504_20260730.csv
data/processed/usd_krw_model_weekdays_19640504_20260730.csv
data/processed/audit/usd_krw_removed_weekends_19640504_20260730.csv
```

## 실행 위치와 기본 흐름

아래 명령은 모두 `fx-chronos/`에서 실행한다.

### 1. ECOS 수집

```bash
.venv/bin/python -m src.data.collect_ecos
```

API 요청 전 가려진 URL과 조회 기간을 확인한다. 기존 원본 JSON은 덮어쓰지 않는다.

### 2. 모델용 데이터 생성

```bash
.venv/bin/python -m src.data.preprocess
```

평일 모델 시계열과 제거된 주말 관측 감사 파일을 분리한다.

### 3. 기본 예측과 기준 모델

```bash
.venv/bin/python -m src.models.zero_shot
.venv/bin/python -m src.models.baseline
```

Zero-shot은 모델 로딩 또는 다운로드가 발생할 수 있다. 출력 파일이 이미 존재하는 경우 덮어쓰기 정책을 먼저 확인한다.

### 4. 월별 Walk-forward와 평가

```bash
.venv/bin/python -m src.evaluation.backtest
.venv/bin/python -m src.evaluation.evaluate
.venv/bin/python -m src.evaluation.split_backtest
.venv/bin/python -m src.evaluation.evaluate_validation
```

주요 산출물:

```text
outputs/forecasts/core/usd_krw_walk_forward_h20_monthly_1997_2025.csv
outputs/metrics/core/usd_krw_walk_forward_h20_monthly_1997_2025_split_manifest.csv
outputs/metrics/core/usd_krw_walk_forward_h20_monthly_validation_2018_2021_summary.csv
```

일부 명령은 기존 파일 덮어쓰기를 의도적으로 거부한다. 재현을 위해 기존 결과를 삭제하지 말고, 새 출력 경로나 별도 작업 복사본을 사용한다.

### 5. 기록된 LoRA 실험

LoRA 설정은 `configs/finetuning.json`, 평가 분할은 `configs/evaluation.json`에서 확인한다. 선택된 후보는 다음과 같다.

```text
chronos2_lora_h20_ctx756_lr1e-5_steps300_seed42
```

관련 실행 파일:

```text
src/models/prepare_finetuning.py
src/models/benchmark_lora_devices.py
src/evaluation/compare_zero_shot_contexts.py
src/models/finetune_lora_candidate.py
src/evaluation/evaluate_final_test.py
```

`evaluate_final_test.py`는 이미 한 차례 평가한 2022~2025 최종 Test용이다. 현재 결과를 개선하기 위한 설정 선택이나 반복 실행에 사용하지 않는다. 새 하이브리드 설정은 개발·Validation 구간에서만 선택하고, 고정 후 가능한 경우 2026년 신규 관측치로 평가한다.

## 결과 추적 관계

```text
ECOS 원본 JSON
→ preprocess.py
→ 평일 모델 시계열 + 주말 감사 CSV
→ backtest.py
→ 월별 h20 예측 CSV
→ split_backtest.py
→ 고정 분할 명세
→ evaluate_validation.py / LoRA 후보 평가
→ outputs/metrics의 summary, by_origin, by_lead
```

핵심 설정과 결과를 함께 확인한다.

- 평가 정의와 고정 분할: `configs/evaluation.json`
- LoRA 후보·seed·MPS·최종 결과: `configs/finetuning.json`
- 상세 결론: `docs/results/usdkrw_h20_lora_evaluation.md`

## 현재 재현성 한계

- 입력 파일명에 수집 종료일이 포함돼 있어 새 ECOS 스냅샷을 사용할 때 관련 경로를 명시적으로 갱신해야 한다.
- 여러 스크립트의 입력·출력 경로가 파일 상수로 고정돼 있다.
- 모델 가중치는 저장소에 포함되지 않으며 첫 실행 시 외부 다운로드가 필요할 수 있다.
- 2022~2025 최종 Test는 이미 관찰했으므로 새로운 설정 선택에 사용할 수 없다.
- 동일한 Apple Silicon 환경에서도 MPS 사용 가능 여부와 성능을 실행 환경별로 확인해야 한다.

## 다음 개발 단계

기존 Validation 예측 CSV를 이용해 다음 단일 축소 계수를 비교한다.

```text
α ∈ {0.0, 0.1, 0.2, 0.3, 0.5}
```

기존 최종 Test를 보지 않고 Validation에서만 α를 선택한다. 최적 α가 0이면 Random Walk만 사용하는 것이 현재 가장 안정적이라는 유효한 결과로 기록한다.
