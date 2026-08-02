# FX Chronos

한국은행 ECOS의 USD/KRW 일별 매매기준율을 Amazon Chronos-2로 예측하고, Random Walk와 결합한 환율 경로를 평가하는 프로젝트입니다.

현재 서비스 후보는 USD/KRW의 향후 20·60·90개 실제 환율 관측값입니다. 최종 점 예측은 Chronos-2 Zero-shot과 Random Walk를 50:50으로 결합한 고정 `α=0.5` 축소 앙상블입니다.

## 구현 범위

| 영역 | 구현 내용 |
|---|---|
| 통화 | USD/KRW |
| 데이터 | 한국은행 ECOS 일별 원/미국달러 매매기준율 |
| 예측 기간 | 20·60·90개 실제 평일 관측 |
| 기준 모델 | Random Walk |
| 시계열 모델 | `amazon/chronos-2` Zero-shot |
| 최종 점 예측 | Random Walk와 Chronos-2의 고정 `α=0.5` 축소 앙상블 |
| 입력 길이 | 최근 756개 관측 |
| 실행 장치 | Apple Silicon MPS |
| 평가 | 시간순 Walk-forward, MAE, RMSE, 방향 정확도, 기준일별 성능 |
| 불확실성 출력 | Chronos q0.1·q0.5·q0.9 참고 시나리오 |
| 환위험 계산 | USD 지급·수취, 부분 헤지, 원화 금액과 손익 시나리오 |

## 데이터 정의

```text
데이터 제공처: 한국은행 ECOS Open API
통계표 코드: 731Y001
주기: D
항목 코드: 0000001
항목명: 원/미국달러(매매기준율)
단위: 원/미국달러
```

| 데이터 | 기간 | 행 수 | 파일 |
|---|---|---:|---|
| ECOS 처리 데이터 | 1964-05-04~2026-07-30 | 17,476 | `data/processed/ecos/usdkrw_19640504_20260730.csv` |
| 모델 입력 데이터 | 1964-05-04~2026-07-30 | 15,405 | `data/processed/usd_krw_model_weekdays_19640504_20260730.csv` |
| 제거 주말 감사 데이터 | 1964-05-09~2006-02-25 | 2,071 | `data/processed/audit/usd_krw_removed_weekends_19640504_20260730.csv` |

데이터 처리 정책은 다음과 같습니다.

- ECOS 원본 JSON과 처리 CSV를 분리해 보존합니다.
- ECOS가 반환한 토요일·일요일 관측은 원본과 처리 데이터에 유지합니다.
- 모델 입력에는 월요일~금요일 관측만 사용합니다.
- 제거한 주말 관측은 감사 CSV에 보존합니다.
- 관측이 없는 평일을 새로 만들지 않습니다.
- 전일값 채우기와 선형보간을 사용하지 않습니다.
- `1 step`은 다음 실제 평일 ECOS 관측을 의미합니다.

ECOS 매매기준율은 시장 종가, 실시간 환율 또는 은행 고객 적용환율과 동일하지 않습니다.

## 최종 예측 방식

Random Walk는 마지막 실제 관측값을 모든 미래 step에 유지합니다. Chronos-2는 최근 756개 USD/KRW 관측에서 미래 변화 경로를 생성합니다.

최종 점 예측은 다음과 같습니다.

```text
ensemble(h)
= last_observation
+ 0.5 × [chronos_median(h) - last_observation]
```

동일한 식을 가중치로 표현하면 다음과 같습니다.

```text
ensemble(h)
= 0.5 × Random Walk(h)
+ 0.5 × Chronos-2 median(h)
```

`α=0.5`는 2018~2021의 20영업일 Validation에서 선택됐으며 60·90영업일 평가에서는 다시 선택하지 않았습니다.

## 성능

### 기간별 Validation

| 예측 기간 | 기준일 | 예측 행 | 앙상블 MAE | Random Walk MAE | MAE 우수율 | 앙상블 RMSE | Random Walk RMSE | RMSE 우수율 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 48 | 960 | 12.104315 | 12.259792 | 1.268% | 15.834602 | 15.967171 | 0.830% |
| 60 | 46 | 2,760 | 19.842420 | 20.017355 | 0.874% | 26.451518 | 26.630793 | 0.673% |
| 90 | 44 | 3,960 | 25.141474 | 25.336490 | 0.770% | 33.007104 | 33.177991 | 0.515% |

`우수율`은 다음 식으로 계산합니다.

```text
100 × (Random Walk 오차 - 앙상블 오차) / Random Walk 오차
```

기간별 기준일 승리 횟수는 다음과 같습니다.

| 예측 기간 | MAE 승리 | RMSE 승리 |
|---:|---:|---:|
| 20 | 32/48 | 31/48 |
| 60 | 25/46 | 25/46 |
| 90 | 25/44 | 27/44 |

60영업일은 2018-01-01~2021-10-01의 요청 기준일을 사용했고 목표일은 2018-01-02~2021-12-28입니다. 90영업일은 2018-01-01~2021-08-01의 요청 기준일을 사용했고 목표일은 2018-01-02~2021-12-13입니다. 2022년 이후 목표값은 두 평가에 포함하지 않았습니다.

### 2026년 H20 고정 평가

2018~2021에서 선택한 `α=0.5`를 변경하지 않고 2026년 1~7월의 7개 월별 기준일과 140개 예측 행에 적용했습니다.

| 모델 | MAE | RMSE |
|---|---:|---:|
| α=0.5 앙상블 | 34.872399 | 41.523387 |
| Random Walk | 36.080714 | 42.368323 |

- MAE 우수율: 3.349%
- RMSE 우수율: 1.994%
- 기준일별 MAE 승리: 6/7
- 기준일별 RMSE 승리: 6/7
- 판정 상태: `provisional_due_to_small_sample`

![2026년 7월 USD/KRW 고정 앙상블](outputs/figures/ensemble/usd_krw_locked_hybrid_20260701.png)

## 분위수 시나리오

Chronos-2에서 다음 값을 추출합니다.

```text
q0.1: 하한 시나리오
q0.5: 중앙 시나리오
q0.9: 상한 시나리오
```

과거 평가에서 q0.1~q0.9 범위가 목표 포함률 80%를 안정적으로 달성하지 못했습니다. 따라서 서비스에서는 다음처럼 사용합니다.

- `하한·중앙·상한 참고 시나리오`로 표시합니다.
- `검증된 80% 신뢰구간`으로 표시하지 않습니다.
- 미래 환율이 해당 범위에 포함된다고 보장하지 않습니다.

## 환위험 계산

`src/hedging/`에는 예측 시나리오를 USD 계약의 원화 금액으로 변환하는 계산 모듈이 있습니다.

- 지급 또는 수취 구분
- 외화 계약 금액
- 결제 예정일
- 기준환율
- 헤지 금액 또는 헤지 비율
- 헤지 환율
- 시나리오별 원화 지급·수취액
- 기준환율 대비 손익
- 무헤지 대비 헤지 효과
- JSON·CSV 출력

현재 모듈은 계산 엔진입니다. 은행 스프레드, 선물환 가격, 옵션 프리미엄, 세금, 신용위험 및 금융상품 적합성 판단은 포함하지 않습니다.

## 프로젝트 구조

```text
fx-chronos/
├── AGENTS.MD
├── README.md
├── requirements.txt
├── configs/
│   ├── ensemble.json
│   ├── evaluation.json
│   ├── h60_ensemble_validation.json
│   ├── h90_ensemble_validation.json
│   ├── hedge_example.json
│   └── hedge_example_receipt.json
├── data/
│   ├── raw/ecos/
│   └── processed/
├── src/
│   ├── data/
│   │   ├── collect_ecos.py
│   │   └── preprocess.py
│   ├── models/
│   │   ├── baseline.py
│   │   └── zero_shot.py
│   ├── evaluation/
│   │   ├── backtest.py
│   │   ├── evaluate.py
│   │   ├── evaluate_shrunk_ensemble.py
│   │   ├── analyze_shrunk_ensemble.py
│   │   ├── evaluate_locked_ensemble_2026.py
│   │   ├── evaluate_h60_locked_ensemble.py
│   │   ├── evaluate_h90_locked_ensemble.py
│   │   └── plot_locked_hybrid_forecast.py
│   └── hedging/
├── outputs/
│   ├── forecasts/
│   │   ├── core/
│   │   └── ensemble/
│   ├── metrics/
│   │   ├── core/
│   │   └── ensemble/
│   ├── figures/
│   └── hedge_analysis/
├── tests/
├── docs/
└── archive/retired_20260802/
```

`archive/retired_20260802/`에는 현재 서비스 범위에서 사용하지 않는 외생변수, JPY, 로그수익률, LoRA, 예측구간 보정 및 구형 horizon 실험이 보존돼 있습니다. 활성 실행 경로에는 포함하지 않습니다.

## 실행 환경

검증 환경:

```text
OS: macOS
Architecture: arm64
Python: 3.14.6
PyTorch: 2.13.0
chronos-forecasting: 2.3.1
Device: MPS
```

고정 패키지 버전은 `requirements.txt`에 기록돼 있습니다.

```bash
cd fx-chronos
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 실행

### 테스트

프로젝트 디렉터리에서 실행합니다.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```

현재 활성 테스트는 27개입니다.

### ECOS 수집

ECOS API 호출에는 `ECOS_API_KEY` 환경변수가 필요합니다. 실제 키를 코드, 설정, 로그 또는 저장소에 기록하지 않습니다.

```bash
ECOS_API_KEY="실제 키" .venv/bin/python -m src.data.collect_ecos
```

수집기는 ECOS 통계표·항목·단위·날짜·숫자값과 페이지 수를 검증하고 원본 JSON 및 처리 CSV를 분리합니다. 기존 결과 파일은 자동으로 덮어쓰지 않습니다.

### 전처리

```bash
.venv/bin/python -m src.data.preprocess
```

### 앙상블 평가

```bash
.venv/bin/python -m src.evaluation.evaluate_h60_locked_ensemble
.venv/bin/python -m src.evaluation.evaluate_h90_locked_ensemble
```

두 평가는 MPS를 요구하며 입력 데이터와 H20 α 선택 파일의 SHA-256을 실행 전에 확인합니다. 기존 산출물이 있으면 덮어쓰지 않고 중단합니다.

### 환위험 계산 예시

```bash
.venv/bin/python -m src.hedging.run_hedge_analysis \
  --config configs/hedge_example.json
```

예시 출력이 이미 있으면 덮어쓰지 않고 중단합니다.

## FastAPI 내부 API

FastAPI는 기존 `analyze_fx_exposure()` 계산을 HTTP로 제공합니다. API 라우터는 환위험 계산식을 다시 구현하지 않으며 메모리에 준비된 예측 시나리오와 기존 도메인 함수를 연결합니다.

```http
POST /internal/hedge-analysis
Content-Type: application/json
```

로컬 실행:

```bash
.venv/bin/uvicorn src.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1
```

요청 예시:

```bash
curl -X POST http://127.0.0.1:8000/internal/hedge-analysis \
  -H 'Content-Type: application/json' \
  -d '{
    "currency_pair": "USD/KRW",
    "side": "PAYABLE",
    "foreign_amount": 1000000,
    "settlement_date": "2026-10-30",
    "reference_rate": 1548.4,
    "hedged_amount": 500000,
    "hedge_rate": 1548.4
  }'
```

응답은 기존 `HedgeAnalysisResult` 전체 구조를 보존합니다.

```json
{
  "currency_pair": "USD/KRW",
  "side": "payment",
  "settlement_date": "2026-10-30",
  "foreign_amount": 1000000.0,
  "hedged_amount": 500000.0,
  "unhedged_amount": 500000.0,
  "hedge_ratio": 0.5,
  "risk_direction": "환율 상승 시 원화 지급액 증가로 불리",
  "forecast_model_name": "amazon/chronos-2 + Random Walk fixed alpha=0.5 H90",
  "scenario_source": "shrunk_ensemble",
  "scenarios": [
    {
      "scenario_name": "point",
      "fx_rate": 1451.8048,
      "hedged_krw_amount": 774200000.0,
      "unhedged_krw_amount": 725902380.0,
      "total_krw_amount": 1500102380.0,
      "fully_unhedged_krw_amount": 1451804760.0,
      "reference_krw_amount": 1548400000.0,
      "favorable_pnl_vs_reference_krw": 48297620.0,
      "hedge_effect_vs_unhedged_krw": -48297620.0
    }
  ],
  "warnings": ["Chronos 분위수는 참고용 시나리오입니다."]
}
```

위 값은 2026-08-03 로컬 실행에서 현재 처리 데이터와 모델 캐시로 확인한 응답 예시입니다. 데이터 스냅샷이나 모델 환경이 달라지면 예측값과 원화 금액도 달라집니다.

API의 `side` 입력은 다음 두 값만 허용합니다.

```text
PAYABLE   → 기존 ExposureSide.PAYMENT
RECEIVABLE → 기존 ExposureSide.RECEIPT
```

서버 시작 시 Chronos-2를 한 번 로딩하고 동일한 최근 756개 관측에서 H20·H60·H90을 각각 생성합니다. 각 경로에 고정 `α=0.5` 앙상블을 적용한 뒤 하나의 메모리 스냅샷으로 보관합니다. 요청은 결제일을 포함하는 가장 짧은 horizon을 H20, H60, H90 순으로 선택합니다.

매일 `03:00 Asia/Seoul`에 새 모델과 예측 스냅샷을 준비합니다. 전체 생성이 성공한 뒤에만 메모리 참조를 교체하고 실패하면 기존 정상 스냅샷을 유지하며 로그를 남깁니다. 로컬 데이터 파일이 갱신되지 않았다면 같은 입력을 다시 예측합니다. ECOS 자동 수집은 이 스케줄에 포함되지 않습니다.

미래 날짜는 월요일~금요일 기준 임시 날짜입니다. 한국 공휴일을 별도로 제외하지 않으며 결제일이 메모리 예측 날짜 또는 90개 관측 범위에 없으면 422를 반환합니다. 가까운 날짜로 자동 이동하지 않습니다.

현재 상태 확인 API(`/health`, `/ready`)는 제공하지 않습니다. 초기 MVP는 프로세스 내부 스케줄러 중복을 막기 위해 Uvicorn worker를 1개로 실행합니다.

프론트의 환율 예측 그래프에는 H90 메모리 경로 전체를 제공합니다.

```http
GET /internal/fx-forecast
```

요청 파라미터와 본문은 없습니다. 응답의 `forecast` 배열은 미래 예측 90개이며 각 행은 `date`, 앙상블 `point`, Chronos `lower`, `median`, `upper`를 포함합니다. 과거 실제 환율은 반환하지 않습니다.

## Docker

빌드:

```bash
docker build -t fx-chronos-api .
```

실행:

```bash
docker run --rm \
  -p 8000:8000 \
  -v fx-chronos-hf-cache:/opt/huggingface-cache \
  fx-chronos-api
```

Docker 이미지는 Python 3.14와 CPU PyTorch를 사용하며 Uvicorn worker 1개로 실행합니다. Hugging Face 캐시 볼륨을 유지하면 컨테이너를 다시 만들 때 모델 파일을 재사용할 수 있습니다. 소스·설정·처리 데이터는 이미지에 포함하고 `.venv`, Git 메타데이터, 원본 데이터, 백테스트 출력, 테스트, 문서와 아카이브는 제외합니다.

AWS 배포, 내부 인증, 상태 확인 API, 백엔드·프론트엔드 연동은 현재 범위에 포함되지 않습니다.

## 주요 산출물

| 내용 | 경로 |
|---|---|
| H20 Validation 예측 | `outputs/forecasts/ensemble/usd_krw_shrunk_ensemble_h20_ctx756_validation_2018_2021.csv` |
| H20 2026 고정 예측 | `outputs/forecasts/ensemble/usd_krw_shrunk_ensemble_h20_ctx756_alpha0.5_2026_locked.csv` |
| H60 Validation 예측 | `outputs/forecasts/ensemble/usd_krw_shrunk_ensemble_h60_ctx756_alpha0.5_validation_2018_2021.csv` |
| H90 Validation 예측 | `outputs/forecasts/ensemble/usd_krw_shrunk_ensemble_h90_ctx756_alpha0.5_validation_2018_2021.csv` |
| H20 결과 문서 | `docs/results/usdkrw_h20_shrunk_ensemble_validation.md` |
| H60 결과 문서 | `docs/results/usdkrw_h60_locked_ensemble_validation.md` |
| H90 결과 문서 | `docs/results/usdkrw_h90_locked_ensemble_validation.md` |

## 현재 상태

구현 완료:

- USD/KRW ECOS 수집과 원본 보존
- 주말 감사 분리와 무보간 모델 데이터
- Chronos-2 Zero-shot 및 Random Walk
- 고정 `α=0.5` 축소 앙상블
- 20·60·90영업일 Walk-forward 평가
- 분위수 참고 시나리오
- USD 지급·수취 환위험 계산 모듈
- 최신 H20·H60·H90 예측을 메모리에 보관하는 FastAPI 내부 API

별도 연결 대상:

- 웹 또는 앱 사용자 인터페이스
- 실제 기업 계약과 금융상품 조건을 이용한 환헤지 전략 검증

## 결과 문서

- [H20 축소 앙상블 Validation](docs/results/usdkrw_h20_shrunk_ensemble_validation.md)
- [H20 2026 고정 평가](docs/results/usdkrw_h20_shrunk_ensemble_2026_locked.md)
- [H60 고정 앙상블 Validation](docs/results/usdkrw_h60_locked_ensemble_validation.md)
- [H90 고정 앙상블 Validation](docs/results/usdkrw_h90_locked_ensemble_validation.md)
- [환위험 계산 예시](docs/results/usdkrw_hedge_analysis_examples.md)
- [ECOS 데이터 정의](docs/ecos-static.md)
- [Chronos-2 기술 정리](docs/chronos.md)
- [재현성 기록](docs/reproducibility.md)

## 해석 범위

예측값은 미래 환율을 보장하지 않습니다. 이 프로젝트는 환율 경로와 원화 금액 시나리오를 제공하는 분석 도구이며 특정 금융상품 가입이나 헤지 비율을 자동 결정하지 않습니다.
