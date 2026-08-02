# 🏦 Financial Product RAG — 기업 환헤지 금융상품 추천 API

> 기업의 수출입 계약·리스크·헤지 전략 정보를 입력받아, **자격조건 검증 → 적합도 점수화 → 공식 출처 연결**을 거쳐 기업 조건에 부합하는 금융상품 후보 카드를 생성하는 규칙 기반 추천 API입니다.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063)
![Tests](https://img.shields.io/badge/tests-95%20passed-brightgreen)
![No LLM Required](https://img.shields.io/badge/LLM-not%20required-informational)
![No DB Required](https://img.shields.io/badge/DB-not%20required-informational)

| 항목           | 내용                                                              |
| -------------- | ----------------------------------------------------------------- |
| 추천 대상 상품 | 27개 등록 상품·서비스 중 16개 (전략 유형이 있는 핵심 금융상품)    |
| 공식 출처      | 25건 (KB국민은행 공식 웹·약관·업로드 PDF 2건, K-SURE 공식 페이지) |
| 자동 채점 규칙 | 16건 (`StrategyType` ↔ 상품 매칭 규칙)                            |
| 검증된 테스트  | 95개 전부 통과 (`pytest -v`, 이 문서 작성 시점 실행 결과)         |
| LLM 필요 여부  | 불필요 — 규칙·점수 기반으로 100% 결정적(deterministic) 동작       |
| 데이터베이스   | 없음 — 검증된 정적 JSON/JSONL 파일만 사용                         |

---

## 1. 문제의식과 개발 배경

수출입 중소·중견기업이 환율 변동 위험(환리스크)에 대응하려 해도, 실제로는 다음과 같은 장벽에 부딪힙니다.

- 선물환·통화옵션·구조화 상품·K-SURE 환변동보험 등 **상품 종류가 많고 조건이 제각각**이라 비전문가가 스스로 비교하기 어렵습니다.
- 장외파생상품은 실수요 확인·투자자정보 확인·거래한도 설정 등 **절차상 자격조건**이 있는데, 이를 모르고 접근하면 시간을 낭비합니다.
- 생성형 AI 기반 금융상품 안내는 **근거 없이 그럴듯한 답을 만들어내는(hallucination) 위험**이 있고, "가입 가능"처럼 단정적인 표현을 잘못 쓰면 실제 심사 결과와 어긋날 수 있습니다.

이 프로젝트는 이 문제를 **LLM이 아니라 구조화된 규칙 엔진과 검증된 데이터**로 풉니다. 모든 후보 상품은 공식 출처(KB 공식 웹·약관·업로드 PDF, K-SURE 공식 페이지)로 뒷받침되고, 자격 판정과 적합도 점수는 재현 가능한 규칙으로 계산되며, "가입 가능"·"승인 가능" 같은 확정적 표현은 코드 차원에서 차단됩니다.

## 2. 전체 서비스에서의 역할

이 프로젝트는 사용자 입력부터 카드 반환까지 이어지는 서비스 파이프라인에서, **외부 전략 생성 XAI가 결정한 전략을 입력받아 그 전략을 실제로 실행할 수 있는 금융상품 후보를 검증하고, 근거가 포함된 카드로 반환하는** 마지막 단계를 담당하도록 설계되었습니다.

```
사용자 입력
   ↓
dongkk-server
   ↓
fx-chronos
환율 예측·시나리오 분석
   ↓
전략 생성 XAI
목표 헤지비율·전략 유형·배분비율 생성
   ↓
financial-product-rag ── 이 프로젝트
상품 후보·자격 상태·적합도·공식 근거 생성
   ↓
dongkk-server → frontend
```

이 프로젝트는 외부 전략 생성 XAI가 결정한 전략을 입력받아, 해당 전략을 실제로 실행할 수 있는 금융상품 후보를 검증하고 근거가 포함된 카드로 반환합니다.

- **어떤 전략을 쓸지는 결정하지 않습니다.** `POST /recommend`는 전략 생성 XAI가 이미 확정한 `strategyContext`(전략 유형·배분 비율·목표 헤지비율)를 입력으로 받습니다 — 전략 자체를 만들어내지 않습니다.
- **RAG 검색은 상품 순위·자격 판정에 관여하지 않습니다.** TF-IDF 기반 `/search`는 운영자·개발자용 디버깅 도구일 뿐이며, 실제 추천 카드 생성 파이프라인은 이 검색을 호출하지 않습니다(`app/main.py` 주석 및 `app/recommender.py` 참고).
- 이 저장소 단독으로도 완전히 동작하며(외부 서비스 호출 없이 정적 데이터만으로 응답), 파이프라인의 다른 컴포넌트가 이 API를 호출하는 형태로 연동하도록 설계돼 있습니다.

## 3. 핵심 차별점

### ✅ 구조화된 기업·계약·전략 정보를 활용한 상품 추천

요청은 자유 텍스트 질문이 아니라 `companyProfile`(거래방향·통화·결제조건 등) · `contracts[]`(계약별 금액·통화·결제일) · `riskContext`(위험등급·성향) · `strategyContext`(전략 유형·배분비율·목표 헤지비율)로 구성된 **구조화된 Pydantic 모델**입니다. 정의되지 않은 필드는 `extra="forbid"`로 조용히 무시하지 않고 즉시 422로 거부합니다.

### ✅ 단순 유사도 검색이 아닌 자격조건 필터링 + 적합도 점수화

상품 추천은 두 단계로 이뤄집니다.

1. **하드 자격 판정**(`app/eligibility.py`): 거래방향·통화·결제조건·기간 조건 등 관찰 가능한 사실과 대조해 `NOT_RECOMMENDED`(하드 차단)를 먼저 걸러냅니다.
2. **적합도 점수화(fitScore, 0~100)**(`app/recommender.py`): 전략 유형 일치(최대 40점), 우선순위, 배분 비율, 거래방향·통화 일치, 결제조건, 기간, 위험등급·위험성향 부합 등 **문서화된 가중치**(`app/scoring_config.py`)로 계산합니다. 유사도 검색 점수는 fitScore 계산에 전혀 관여하지 않습니다.

### ✅ 공식 출처 기반 추천 근거

모든 상품에는 `source_ids`가 연결되어 있고, 응답의 `evidenceMap`에 출처 제목·제공기관·근거 유형·확인일이 함께 반환됩니다. 25건의 출처 중 2건은 사용자가 직접 업로드한 KB 공식 PDF 원문(`sources/` 디렉터리)이며, 나머지는 KB·K-SURE 공식 웹페이지·약관입니다. "자격 충족"·"가입 가능"·"승인 가능" 같은 확정적 표현은 카드 생성 단계에서 금칙어로 걸러냅니다(`app/card_builder.py`의 `_BANNED_PHRASES`).

### ✅ 4단계 상태 구분 — `RECOMMENDED` / `CONDITIONAL` / `RM_REVIEW_REQUIRED` / `NOT_RECOMMENDED`

이 API는 가입 자격을 최종 판정하지 않습니다. "현재 보유한 정보로 판단한 추천 적합도"를 4단계로 구분해, 확인이 더 필요한 경우와 완전히 부적합한 경우를 명확히 나눕니다(7절 참고).

### ✅ 다중 계약 및 `거래방향 × 통화` 노출 그룹 지원

분할 결제(계약 1건에 결제 회차 여러 건)와 수출입 겸업 기업의 혼합 계약(예: USD 수출 + JPY 수입)을 지원합니다. `contracts[]`는 `(tradeDirection, currency)` 기준 **노출 그룹**으로 자동 분리되어, 그룹마다 독립적으로 원화 노출액·목표 헤지금액·추천 헤지금액을 계산합니다(9절).

### ✅ 미검증 상품명·가입 불가 조건에 대한 안전장치

`requestedProductNames`로 들어온 상품명은 `review_queue.json`(15건)과 대조해, 종료되었거나(`KB ONE TRADE`, 2022년 서비스 종료) 표준 상품으로 확인되지 않은 명칭은 임의로 카드를 만들지 않고 명시적으로 거부 사유를 안내합니다(`app/verification.py`).

## 4. 처리 흐름

```
POST /recommend
   │
   ▼
① Pydantic 요청 검증 (extra="forbid" — 정의되지 않은 필드 422)
   │
   ▼
② exposureGroupId 교차 검증 (존재하지 않거나 누락된 그룹 ID → 구조화된 422)
   │
   ▼
③ requestedProductNames 검증 (review_queue.json 대조, 미검증 명칭 차단)
   │
   ▼
④ 노출 그룹 분리 (contracts를 tradeDirection×currency로 그룹화)
   │
   ▼
⑤ 그룹별 후보 생성 + 하드 자격 판정 (app/eligibility.py)
   │
   ▼
⑥ 적합도 점수화 및 정렬 (priority → fitScore → allocationRatio → 상품명)
   │
   ▼
⑦ 카드 생성 (공식 근거 연결, 원화 노출액·헤지금액 계산, 금칙어 필터링)
   │
   ▼
RecommendResponse (cards[] + excludedProducts[] + evidenceMap + notices)
```

## 5. 기술 스택

| 구분                   | 사용 기술                                                                |
| ---------------------- | ------------------------------------------------------------------------ |
| 웹 프레임워크          | FastAPI 0.116 + Uvicorn                                                  |
| 데이터 검증            | Pydantic v2 (엄격한 스키마, camelCase ↔ snake_case 자동 변환)            |
| 보조 검색(디버깅 전용) | scikit-learn TF-IDF (`/search`, 추천 로직과 완전히 분리)                 |
| 테스트                 | pytest                                                                   |
| 데이터 저장            | 정적 JSON/JSONL 파일 (데이터베이스 없음)                                 |
| LLM                    | 사용하지 않음 — `LLM_*` 환경변수를 비워도 모든 핵심 기능이 동일하게 동작 |

## 6. 데이터 구성 (실제 검증된 수치)

`scripts/validate_data.py`로 기동 시점마다 무결성을 검증합니다(중복 ID, 참조 무결성, enum 값 유효성 등).

| 데이터 파일                      | 내용                            | 건수                                                                          |
| -------------------------------- | ------------------------------- | ----------------------------------------------------------------------------- |
| `data/product_master.json`       | 전체 등록 상품·서비스           | 27건 (전략 유형이 있어 카드 후보가 되는 상품 16건 + 실행 채널·보조 상품 11건) |
| `data/source_registry.json`      | 공식 출처                       | 25건                                                                          |
| `data/recommendation_rules.json` | `StrategyType` ↔ 상품 매칭 규칙 | 16건                                                                          |
| `data/knowledge_articles.json`   | 절차·리스크 안내 지식문서       | 6건                                                                           |
| `data/rag_documents.jsonl`       | `/search` 디버깅용 문서 인덱스  | 33건                                                                          |
| `data/review_queue.json`         | 미검증·종료·자동추천 금지 명칭  | 15건                                                                          |
| `sources/*.pdf`                  | 사용자 업로드 KB 공식 PDF 원문  | 2건                                                                           |

## 7. 디렉터리 구조

```
financial-product-rag/
├── app/
│   ├── main.py                  # FastAPI 앱, 엔드포인트 정의
│   ├── models.py                # 요청·응답 Pydantic 모델, enum 정의
│   ├── services/
│   │   └── recommendation_service.py  # 파이프라인 오케스트레이션
│   ├── recommender.py           # 후보 생성 + fitScore 계산
│   ├── scoring_config.py        # fitScore 가중치 상수
│   ├── eligibility.py           # 하드 자격 판정 규칙
│   ├── exposure.py              # 노출 그룹(방향×통화) 분리·검증
│   ├── valuation.py             # 원화 노출액·헤지금액 계산
│   ├── card_builder.py          # 카드 문구 생성, 금칙어 필터링
│   ├── verification.py          # 상품명 검증, review_queue 대조
│   ├── evidence_retriever.py    # 공식 근거·관련 가이드 연결, TF-IDF 검색
│   └── store.py                 # 정적 데이터 로딩(캐시)
├── data/                        # 상품·출처·규칙·검증 데이터(JSON/JSONL)
├── sources/                     # 업로드된 공식 PDF 원문
├── scripts/validate_data.py     # 데이터 무결성 검증 스크립트
├── tests/                       # pytest 테스트 스위트(95개)
└── requirements.txt
```

## 8. 설치 및 실행

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/validate_data.py   # 데이터 무결성 확인
pytest -v                          # 테스트 실행
uvicorn app.main:app --reload      # http://127.0.0.1:8000
```

`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`(`.env.example` 참고) 환경변수는 설정하지 않아도 모든 핵심 기능(`/recommend`, `/search`, `/sources/{id}`, `/products/{id}`)이 동일하게 동작합니다.

## 9. API

### `GET /health`

서비스 상태 확인.

```bash
curl http://127.0.0.1:8000/health
```

```json
{ "status": "ok" }
```

### `POST /recommend`

기업·계약·리스크·전략 정보를 받아 추천 카드를 생성합니다.

| 필드                            | 필수 여부               | 설명                                                             |
| ------------------------------- | ----------------------- | ---------------------------------------------------------------- |
| `companyProfile.tradeDirection` | 필수                    | `EXPORT` / `IMPORT` / `BOTH`                                     |
| `contracts[]`                   | 필수(최소 1건)          | 계약별 거래방향·금액·통화·결제일                                 |
| `riskContext`                   | 선택                    | 위험등급(`riskLevel`)·위험성향(`riskPreference`) 등              |
| `strategyContext`               | 선택(생략 시 카드 없음) | 전략 유형·배분비율·목표 헤지비율 — **이미 결정된 전략**을 받는다 |
| `options.maxCards`              | 선택(기본 3)            | 반환할 최대 카드 수(1~10)                                        |

**노출 그룹 ID가 존재하지 않거나(다중 그룹에서) 누락되면** 구조화된 422를 반환합니다(9절 참고). Pydantic 검증 실패(잘못된 enum, 범위를 벗어난 값, 정의되지 않은 필드 등)도 422입니다.

## 10. 요청·응답 예시 (실제 실행 결과)

### 요청

```json
POST /recommend
{
  "companyProfile": {
    "tradeDirection": "EXPORT",
    "industry": "MANUFACTURING",
    "mainCountries": ["US"],
    "currencies": ["USD"],
    "paymentTerms": ["T/T"],
    "currentlyHedging": false
  },
  "contracts": [
    {
      "tradeDirection": "EXPORT",
      "foreignAmount": 200000,
      "currency": "USD",
      "settlementDate": "2026-10-31",
      "baseRate": 1350
    }
  ],
  "riskContext": { "riskLevel": "HIGH", "riskPreference": "CERTAINTY" },
  "strategyContext": {
    "groupTargets": [{ "targetHedgeRatio": 0.5 }],
    "strategies": [
      { "strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 0.6, "priority": 1 },
      { "strategyType": "FORWARD", "allocationRatio": 0.4, "priority": 2 }
    ]
  },
  "options": { "maxCards": 2 }
}
```

### 응답 (200 OK, 실제 실행 결과 — 카드 핵심 필드만 발췌)

```json
{
  "recommendationVersion": "2.4",
  "cards": [
    {
      "rank": 1,
      "productId": "KSURE-FX-001",
      "productName": "K-SURE 환변동보험(선물환 방식·일반형)",
      "provider": "K-SURE(한국무역보험공사)",
      "strategyTypes": ["FX_INSURANCE_GENERAL"],
      "allocationRatio": 0.6,
      "fitScore": 94,
      "eligibilityStatus": "CONDITIONAL",
      "eligibilityLabel": "조건 확인 필요",
      "exposureGroupId": "EXPORT-USD",
      "groupExposureKrw": 270000000.0,
      "targetHedgeRatio": 0.5,
      "groupTargetHedgeAmountKrw": 135000000.0,
      "recommendedHedgeAmountKrw": 81000000.0,
      "sourceIds": [
        "SRC-019",
        "SRC-020",
        "SRC-022",
        "SRC-023",
        "SRC-024",
        "SRC-025",
        "SRC-017",
        "SRC-018",
        "SRC-021"
      ]
    },
    {
      "rank": 2,
      "productId": "FX-HEDGE-001",
      "productName": "인터넷 선물환 거래",
      "provider": "KB국민은행",
      "strategyTypes": ["FORWARD"],
      "allocationRatio": 0.4,
      "fitScore": 92,
      "eligibilityStatus": "RM_REVIEW_REQUIRED",
      "eligibilityLabel": "직원 확인 필요",
      "exposureGroupId": "EXPORT-USD",
      "groupExposureKrw": 270000000.0,
      "recommendedHedgeAmountKrw": 54000000.0,
      "sourceIds": ["SRC-002", "SRC-003", "SRC-004", "SRC-017", "SRC-018"]
    }
  ],
  "excludedProducts": [],
  "notices": [
    "적합도는 입력된 기업 및 계약 정보를 기준으로 산정한 참고 결과입니다.",
    "실제 가입·거래 가능 여부는 각 기관의 심사와 영업점 확인 후 결정됩니다."
  ]
}
```

`groupExposureKrw`(270,000,000원)는 `foreignAmount(200,000) × baseRate(1350)`, `groupTargetHedgeAmountKrw`(135,000,000원)는 `groupExposureKrw × targetHedgeRatio(0.5)`, `recommendedHedgeAmountKrw`는 여기에 각 상품의 `allocationRatio`를 곱해 계산됩니다(81,000,000 = 135,000,000 × 0.6).

## 11. `StrategyType` 목록

`app/models.py`에 정의된 15개 값입니다. `INTERNAL_MATCHING_NETTING`은 가입형 상품이 아니라 기업 자체 내부 관리기법이라 연결된 상품이 없고, 카드 대신 안내 메시지로 처리됩니다.

| StrategyType                | 연결 상품(예시)                         |
| --------------------------- | --------------------------------------- |
| `FORWARD`                   | 인터넷 선물환 거래                      |
| `MAR`                       | MAR 거래                                |
| `FX_OPTION`                 | 통화옵션(콜옵션·풋옵션)                 |
| `RANGE_FORWARD`             | Range Forward                           |
| `ENHANCED_FORWARD`          | Enhanced Forward                        |
| `PARTICIPATING_FORWARD`     | Participating Forward                   |
| `SEAGULL_FORWARD`           | Seagull Forward                         |
| `FX_SWAP`                   | 외환스왑 거래                           |
| `FX_INSURANCE_GENERAL`      | K-SURE 환변동보험(선물환 방식·일반형)   |
| `FX_INSURANCE_OPTION`       | K-SURE 환변동보험(옵션형)               |
| `FOREIGN_CURRENCY_DEPOSIT`  | 외화정기예금, KB WISE 외화정기예금      |
| `IMPORT_PAYMENT_DEFERRAL`   | KB Payment Usance                       |
| `EXPORT_RECEIVABLE_FINANCE` | 수출환어음매입(추심)                    |
| `EXPORT_WORKING_CAPITAL`    | KB 수출기업 우대대출, 무역금융          |
| `INTERNAL_MATCHING_NETTING` | (연결 상품 없음 — 안내 메시지로만 처리) |

## 12. `eligibilityStatus` 4단계

| 상태                 | 의미                                                          | 정상/오류             | 카드 포함 여부              |
| -------------------- | ------------------------------------------------------------- | --------------------- | --------------------------- |
| `RECOMMENDED`        | 관찰 가능한 자격 조건을 모두 충족                             | 정상 결과             | `cards[]`에 포함            |
| `CONDITIONAL`        | 확인이 필요한 항목이 있으나 하드 차단 사유는 없음             | 정상 결과 (오류 아님) | `cards[]`에 포함            |
| `RM_REVIEW_REQUIRED` | 장외파생상품 등 절차상 항상 직원 확인이 필요                  | 정상 결과 (오류 아님) | `cards[]`에 포함            |
| `NOT_RECOMMENDED`    | 거래방향·통화·기간 등 관찰 가능한 조건을 명백히 충족하지 못함 | 정상 결과             | `excludedProducts[]`로 이동 |

## 13. 테스트

```bash
pytest -v
```

**95개 테스트 전부 통과**(이 문서 작성 시점에 직접 실행해 확인)합니다.

| 테스트 파일                                   | 개수 | 검증 내용                                               |
| --------------------------------------------- | ---- | ------------------------------------------------------- |
| `tests/test_api.py`                           | 19   | 엔드포인트 정상/오류 응답, 422 케이스, extra field 거부 |
| `tests/test_card_schema.py`                   | 10   | 카드 필수 필드, 금칙어 미포함, source_id 존재           |
| `tests/test_data_integrity.py`                | 11   | 데이터 ID 중복·참조 무결성, enum 유효성                 |
| `tests/test_scenarios.py`                     | 22   | 실제 추천 시나리오(수출/수입, 자격 판정, 결정성)        |
| `tests/test_v22_refinements.py`               | 15   | 정렬 우선순위, 노출 그룹 교차 오염 방지                 |
| `tests/test_v23_multi_currency.py`            | 10   | 다중 통화 원화 환산, 그룹별 배분비율 검증               |
| `tests/test_v24_exposure_group_validation.py` | 8    | exposureGroupId 구조화 422                              |

## 14. 현재 제약사항과 향후 확장 방향

**현재 하지 않는 것 (의도적 설계)**

- 전략 유형·배분비율·목표 헤지비율을 스스로 결정하지 않습니다 — 이미 결정된 전략을 입력으로 받습니다.
- 실시간 환율이나 환율 예측을 자체 계산하지 않습니다 — `baseRate`/`exposureKrw`는 호출 측이 제공해야 합니다.
- LLM 기반 자유 응답 생성을 하지 않습니다 — 모든 문구는 검증된 데이터의 필드를 그대로 쓰거나 짧게 자른 것입니다.
- 가입 자격을 최종 확정하지 않습니다 — `CONDITIONAL`/`RM_REVIEW_REQUIRED`로 유보하고 절대 "승인 확정"류 표현을 만들지 않습니다.

**향후 확장 방향**

- 실제 백엔드(기업 정보 저장·전략 결정 서비스)와의 연동
- 지원 금융기관·상품 범위 확대
- 상품 조건·출처 최신성에 대한 정기 점검 자동화
- 카드 후보가 아닌 11개 보조 상품(실행 플랫폼·부가 금융상품)의 별도 노출 방식 설계

---

> ⚠️ **이용 안내**: 이 API가 반환하는 추천 결과는 입력된 기업·계약 정보를 기준으로 산정한 **참고용 적합도**입니다. 실제 상품 가입·거래 가능 여부, 적용 조건, 한도는 각 금융기관의 심사와 영업점 직원 확인을 거쳐 최종 결정됩니다.
