# KB & K-SURE FX 추천 카드 API (v2.4)

기업의 수출입·계약·리스크·전략 정보를 입력받아, 프론트엔드의 "추천 금융상품"
카드 영역에 바로 렌더링할 수 있는 **구조화된 카드 데이터**를 생성하는
API입니다. KB국민은행 공식 자료, 사용자가 제공한 KB 공식 PDF 2건, 한국무역
보험공사(K-SURE) 공식 페이지를 근거로 구성했습니다.

## v2.3 → v2.4: 존재하지 않는 exposureGroupId를 더 이상 조용히 무시하지 않음

v2.3까지는 `strategies[].exposureGroupId`/`groupTargets[].exposureGroupId`가
`contracts`로 만들어지는 노출 그룹에 실제로 존재하는지 검증하지
않았습니다 — 존재하지 않는 id를 가리키면 그 전략은 그냥 아무 후보도
만들지 못하고 조용히 사라졌고(에러도 notice도 없음), 그룹이 여러 개인데
`exposureGroupId`를 생략한 경우만 `notices`로 안내했습니다. 이번 개편은
두 경우 모두 **명시적 422**로 바꿨습니다 — 이 API는 이미 확정된 전략
결과(`strategyContext`)를 받는 API이므로, 그 결과가 가리키는 그룹이
실제로 존재하는지는 조용히 넘어갈 문제가 아니라고 판단했습니다.

### 검증 시점과 방식

`POST /recommend` 핸들러가 `RecommendRequest`를 Pydantic으로 파싱한
**직후, 추천 로직을 실행하기 전에** `app.exposure.validate_exposure_group_references()`
를 호출합니다. `contracts`로 노출 그룹을 만들고, `strategyContext.strategies[]`와
`strategyContext.groupTargets[]`의 모든 `exposureGroupId`를 그 목록과
대조합니다.

- **존재하지 않는 id** → `UnknownExposureGroupError` → 422
- **그룹이 여러 개인데 생략** → `MissingExposureGroupError` → 422
- **그룹이 하나뿐인데 생략** → 계속 허용, 자동으로 그 그룹에 연결(기존 동작 유지)

두 예외 모두 `app/exposure.py`에 정의되어 있고, `GET /sources/{id}`의
404와 같은 스타일로 **구조화된 JSON** `detail`을 반환합니다(Pydantic의
기본 `value_error` 문자열 메시지가 아니라, 프론트가 바로 파싱할 수 있는
필드로).

```json
// 존재하지 않는 exposureGroupId
{
  "detail": {
    "error": "unknown_exposure_group_id",
    "field": "strategyContext.strategies[1].exposureGroupId",
    "invalidExposureGroupId": "EXPORT-EUR",
    "availableExposureGroupIds": ["EXPORT-USD", "IMPORT-JPY"]
  }
}
```

```json
// 다중 그룹인데 exposureGroupId 생략
{
  "detail": {
    "error": "missing_exposure_group_id",
    "field": "strategyContext.strategies[2].exposureGroupId",
    "availableExposureGroupIds": ["EXPORT-USD", "IMPORT-JPY"],
    "message": "노출 그룹이 여러 개이므로 exposureGroupId를 반드시 지정해야 합니다."
  }
}
```

`field`는 `strategies`/`groupTargets` 중 어느 목록의 몇 번째(0-based)
항목인지까지 담아, 프론트가 정확히 어느 입력을 고쳐야 하는지 바로
알 수 있게 했습니다.

이 검증을 통과한 뒤에는 `app/recommender.py`/`app/valuation.py`가 모든
`exposureGroupId`를 항상 유효하다고 가정합니다 — `recommendation_service.py`에
있던 "그룹 미배정 전략은 notices로 안내하고 조용히 제외" 로직은 이제
도달할 수 없는 코드라 제거했습니다.

### riskContext.baseRate — deprecated

`RiskContextIn.baseRate`는 v2.3부터 원화 노출액 계산에 전혀 쓰이지
않습니다(계산은 오직 `contracts[].baseRate`/`contracts[].exposureKrw`,
또는 단일 그룹일 때만 `riskContext.exposureKrw`). 이번에 Pydantic
필드에 `deprecated=True`를 표시해 OpenAPI 스키마(`/openapi.json`,
`/docs`)에도 deprecated로 나타나도록 했습니다. 필드 자체는 하위 호환을
위해 계속 받고 값도 그대로 보관하지만, 어떤 값을 넣어도 계산 결과가
달라지지 않음을 `tests/test_v24_exposure_group_validation.py::test_deprecated_risk_context_base_rate_still_unused_in_calculation`
로 실측 검증합니다.

## v2.2 → v2.3: 다중 통화 환산 + 노출 그룹별 전략 배분

v2.2까지는 노출 그룹(방향×통화)을 나눴지만, 원화 환산은 여전히
`riskContext.baseRate` 하나를 모든 그룹에 공통 적용했고, 전략은 어느
그룹에 적용되는지 구분 없이 방향·통화가 맞는 모든 그룹에 자동으로
붙었습니다. v2.3은 이 두 가지를 고칩니다.

### 용어 정의

| 필드 | 정의 |
|---|---|
| `contracts[].exposureKrw` | 그 계약 **하나만의** 원화 환산 노출액(선택). 있으면 다른 계산보다 항상 우선한다. |
| `contracts[].baseRate` | 그 계약 **하나만의** 적용 환율(선택). `exposureKrw`가 없을 때 `foreignAmount × baseRate`로 노출액을 계산하는 데 쓰인다. |
| `groupExposureKrw` (카드 응답 필드) | 그 카드가 커버하는 노출 그룹(방향×통화) 전체의 원화 환산 노출액. 그룹 내 계약들의 `exposureKrw`(또는 `foreignAmount×baseRate`) 합계, 또는(노출 그룹이 하나뿐일 때만) `riskContext.exposureKrw`. |
| `strategyContext.groupTargets[].targetHedgeRatio` | 그 노출 그룹 전체 노출액 중 **목표로 헤지하려는 비율**(0~1). "이 정도는 헤지해야 한다"는 정책적 목표값이며, 실제 각 전략의 배분과는 별개다. |
| `strategyContext.hedgeTargetMin`/`hedgeTargetMax` | `allocationRatio`가 이 범위 안에 들면 fitScore에 가산점을 주는 **점수 산정용** 참고 구간이다. `targetHedgeRatio`(헤지금액 계산용)와는 별개 개념이며 서로 대체하지 않는다. |
| `strategyContext.strategies[].allocationRatio` | **목표 헤지금액(groupTargetHedgeAmountKrw) 안에서** 이 전략이 차지하는 배분 비율(0~1). 그룹 노출액 전체가 아니라 "목표 헤지금액 중 몇 %를 이 전략으로 채울지"를 뜻한다. |
| `groupTargetHedgeAmountKrw` (카드 응답 필드) | `groupExposureKrw × targetHedgeRatio`. `targetHedgeRatio`가 없으면 계산하지 않고 `null`(hedgeTargetMax로 대체하지 않음). |
| `recommendedHedgeAmountKrw` (카드 응답 필드) | `groupTargetHedgeAmountKrw × allocationRatio`. 위 두 값 중 하나라도 없으면 `null`. |

### 다중 통화 원화 환산 처리 원칙

`riskContext.baseRate`는 더 이상 노출액 계산에 쓰이지 않습니다(여러
통화쌍에 환율 하나를 공통 적용하는 문제를 근본적으로 없애기 위해 필드
자체를 계산 경로에서 제외했습니다 — 여전히 요청에는 보낼 수 있고
참고 정보로 보관되지만 계산에 관여하지 않습니다). 그룹 노출액 계산
우선순위:

1. `contracts[].exposureKrw` (계약별로 이미 계산된 값)
2. `contracts[].foreignAmount × contracts[].baseRate` (계약별 환율)
3. **노출 그룹이 요청 전체에서 하나뿐일 때만** `riskContext.exposureKrw`
4. 그래도 정할 수 없으면(전형적으로 다중 통화인데 계약별 환율·노출액이
   없는 경우) **추측하지 않고** `groupExposureKrw: null` +
   `pendingConditions`에 안내 문구를 반환합니다.

그룹에 속한 계약 중 하나라도 1~2번으로 못 채우면, 그 그룹 전체를
"계산 불가"로 취급합니다(일부만 반영해 그럴듯한 합계를 만들지 않기
위해서). `exposureCalculationStatus`로 그 사유를 구분합니다.

| 값 | 의미 |
|---|---|
| `PROVIDED` | 계약별 `exposureKrw`가 직접 주어졌거나(전부), 단일 그룹이라 `riskContext.exposureKrw`를 그대로 씀 |
| `CALCULATED` | 계약별 `foreignAmount × baseRate`로 계산함(일부라도 계산이 필요했던 경우) |
| `MISSING_RATE` | 계약 금액은 있지만 환산에 필요한 환율/노출액이 없음 |
| `MISSING_EXPOSURE` | 노출액을 판단할 근거 자체가 전혀 없음 |

### 전략의 노출 그룹 연결

`strategyContext.strategies[].exposureGroupId`(선택)로 전략이 적용될
노출 그룹을 명시합니다.

```json
{"exposureGroupId": "EXPORT-USD", "strategyType": "FORWARD", "allocationRatio": 0.6, "priority": 1}
```

- 노출 그룹이 **하나뿐**이면 생략을 허용하고 자동으로 그 그룹에 연결합니다(기존 단일 계약 요청과 호환).
- 노출 그룹이 **여러 개**인데 생략하면, 절대 임의로 그룹을 골라 배정하지 않습니다 — 이 전략은 추천 후보 생성에서 제외되고, `notices`에 "어느 그룹인지 알 수 없어 제외했다"는 안내가 남습니다.

### allocationRatio 검증(노출 그룹별)

기존에는 요청 전체 `allocationRatio` 합계(≤1.05)를 검증했지만, 이제는
**노출 그룹별로** 합계를 검증합니다(각 그룹 최대 1.0, 부동소수점 오차만
허용). 서로 다른 그룹은 각각 독립적으로 최대 1.0까지 배분할 수 있습니다
— `exposureGroupId`가 없는 전략은 노출 그룹이 하나뿐일 때만 그 그룹으로
집계하고, 그룹이 여럿이면 이 합계 검증에서도 제외합니다(추천 파이프라인과
동일한 기준).

## v2.1 → v2.2: 연동 전 핵심 보완

### 1. 카드 정렬 기준

카드 순위는 다음 우선순위로 결정됩니다(동점일 때만 다음 기준으로 넘어감).

1. **전략 priority** — 낮은 숫자가 우선(1이 최우선). 지정하지 않은 전략은
   지정된 전략들보다 항상 뒤로 밀립니다.
2. **fitScore** — 내림차순.
3. **allocationRatio** — 내림차순(같은 priority·fitScore라면 배분 비율이
   큰 쪽을 우선).
4. **상품명(공식 명칭)** — 위 세 기준이 모두 같을 때만 쓰는 최종 결정자.

이전에는 `(-fitScore, 상품명)`만으로 정렬해 priority가 사실상 무시됐습니다.
`tests/test_v22_refinements.py::test_sort_priority_overrides_fit_score`로,
관찰 조건이 부족해 fitScore가 낮게 나온 priority=1 전략의 상품이 그래도
fitScore가 더 높은 priority=2 상품보다 먼저 나오는지 검증합니다.

### 2. 수출입 겸업 기업의 혼합 계약 (노출 그룹)

`contracts`는 `(tradeDirection, currency)` 기준으로 **노출 그룹**
(`app/exposure.py::ExposureGroup`)으로 나뉩니다. 예: USD 수출 계약 1건 +
JPY 수입 계약 1건 → `EXPORT-USD`, `IMPORT-JPY` 두 그룹.

후보 생성·자격 판정·fitScore 계산은 전부 **그룹 단위**로 이뤄집니다 —
그룹마다 독립적으로 방향·통화·기간을 판정하므로, 한 그룹의 계약 조건이
다른 그룹의 판정에 영향을 주지 않습니다. 방향·통화 제한이 없는 범용
상품(예: 선물환)은 여러 그룹에 동시에 적용될 수 있으며, 이때는 **그룹마다
별도의 카드**가 생깁니다(하나로 합치지 않음).

각 카드에는 자신이 커버하는 그룹 정보가 담깁니다.

- `exposureGroupId`: 예) `"EXPORT-USD"`, `"IMPORT-JPY"`
- `coveredTradeDirection`, `coveredCurrency`
- `coveredContractIndexes`: 이 카드가 커버하는 `contracts` 배열의 인덱스만

`excludedProducts`에도 같은 필드가 담겨, 어느 그룹에서 왜 제외됐는지
구분할 수 있습니다(같은 상품이 A 그룹에서는 카드로, B 그룹에서는
`excludedProducts`로 동시에 나타날 수 있습니다 — 그룹별로 독립 판정이기
때문입니다).

**한계**: `riskContext`(baseRate/remainingDays 등)는 요청 전체에 하나뿐인
집계값입니다. 노출 그룹이 2개 이상이면 `baseRate`를 모든 그룹에 동일하게
적용하고(서로 다른 통화쌍의 환율을 구분해서 받는 필드가 없음),
`remainingDays`보다 그룹 자신의 계약 결제예정일을 우선 사용합니다(자세한
계산 순서는 `app/eligibility.py::derive_remaining_days` 참고). 그룹이
정확히 1개(대부분의 요청)일 때는 기존과 동일하게 `riskContext.remainingDays`를
그대로 신뢰합니다.

### 3. recommendedHedgeAmountKrw 계산 기준

> **v2.3에서 계산식이 바뀌었습니다.** 이제 `groupExposureKrw`(노출액) →
> `groupTargetHedgeAmountKrw`(목표 헤지금액) → `recommendedHedgeAmountKrw`
> (카드별 추천금액) 3단계입니다. 정확한 계산식·용어 정의·다중 통화 처리
> 원칙은 이 문서 맨 위 "v2.2 → v2.3: 다중 통화 환산 + 노출 그룹별 전략
> 배분" 섹션을 참고하세요. `riskContext.baseRate`는 더 이상 이 계산에
> 쓰이지 않습니다.

불변조건(모두 `tests/test_v22_refinements.py`, `tests/test_v23_multi_currency.py`로 검증):

- 추천 금액은 항상 0 이상.
- 카드가 커버하지 않는 계약의 금액은 절대 섞이지 않음(다른 노출 그룹의
  계약금액이 카드 헤지금액에 포함되지 않음을 실측).
- 같은 그룹 내 여러 카드(전략)의 `recommendedHedgeAmountKrw` 합계가 그
  그룹의 `groupTargetHedgeAmountKrw`를 초과하지 않음(`allocationRatio`가
  그룹별로 1.0을 넘지 못하도록 검증되므로 구조적으로 보장됨).
- 분할 결제(같은 그룹 내 여러 계약)는 중복 합산되지 않음 — 각 계약은
  정확히 하나의 그룹에만 속하므로 구조적으로 중복이 불가능합니다.

### 4. requestedProductNames 매칭 개선

부분 문자열 포함 매칭을 **완전히 제거**하고, 정규화(대소문자 통일, 공백·
가운뎃점·하이픈·언더스코어·슬래시·쉼표 정규화, 괄호 부가설명 제거) 후
**전체 문자열 일치**만 허용합니다(`app/verification.py::_names_equal`).
`input_name`/`canonical_name`/`aliases`(review_queue) 또는
`official_name`/`aliases`(product_master) 중 하나와 정규화 후 완전히
같아야 매칭됩니다. "MAR"처럼 "MARS"/"Market Average Rate"의 부분
문자열만 겹치는 입력은 더 이상 매칭되지 않습니다(이전 버전이었다면
잘못 매칭됐을 사례).

`"KB MARS (Market Average Rate System)"`처럼 review_queue의 공식
`input_name`이 괄호 부가설명을 포함하는 경우 정규화 과정에서 자동으로
제거되어 `"KB MARS"` 입력과 매칭됩니다. 괄호가 아닌 일반 텍스트로 덧붙은
경우(`"KB FX Matching 상계 처리 서비스"`)는 `review_queue.json`에
`aliases: ["KB FX Matching"]`처럼 짧은 형태를 명시적으로 등록해
대응합니다 — 데이터를 조작하는 게 아니라 이미 존재하는 같은 대상의
짧은 별칭을 인식표에 추가하는 것입니다.

기존 시나리오는 모두 유지됩니다: `"KB MARS"` → `MAR 거래`로 정정,
`"KB FX Matching"` → 제외, `"KB ONE TRADE"` → 제외(RETIRED).

### 5. 정의되지 않은 요청 필드

`app/models.py::CamelModel`에 `extra="forbid"`를 적용했습니다. 아직
외부 연동 전이라 호환성을 위해 조용히 무시할 이유가 없고, 오히려
"이 필드가 반영됐는지 무시됐는지" 호출 측이 헷갈릴 여지를 없애는 편이
낫다고 판단했습니다. `companySize`/`kSureEligible`/`hasExportPerformance`/
`hasForeignCurrencySurplus`/`importItemEligible`처럼 제거된 필드는 물론,
철자가 틀렸거나 아직 정의되지 않은 어떤 필드든 요청에 포함되면 즉시
**422**로 거부합니다(중첩 객체 내부 필드도 동일하게 적용).

## v2.0 → v2.1: "실제 서비스가 보유한 정보" 기준으로 재정렬

v2.0은 질의응답형 RAG를 카드 추천형으로 바꾸는 데 집중했지만, 요청
스키마에 `companySize`/`hasExportPerformance`/`kSureEligible`처럼
**실제 서비스가 추천 시점에 확정적으로 갖고 있지 않은 값**이 섞여
있었습니다. 이 값들이 없다는 이유로 상품이 `NOT_ELIGIBLE`(v2.1부터는
`NOT_RECOMMENDED`) 처리되거나, `ELIGIBLE`이라는 표현이 마치 심사가 끝난
것처럼 보일 수 있다는 문제가 있었습니다. v2.1은 이 문제를 고칩니다.

**핵심 원칙 변경**

- 이 API는 **가입 자격을 최종 판정하지 않습니다.** "현재 보유한 정보로
  얼마나 적합한가"만 계산합니다.
- 값이 있고 조건을 명백히 충족하지 않으면 → 추천 제외(`NOT_RECOMMENDED`).
- 값 자체가 없어서 판단할 수 없으면 → **추천 제외하지 않고** `pendingConditions`
  + `CONDITIONAL`로 유보.
- K-SURE·대출·파생상품의 **실제 가입/인수 가능 여부는 확정하지 않습니다.**
- 전략 결과(`strategyContext`)가 상품 추천에서 가장 높은 우선순위를 가집니다.

**요청 스키마 변경 (요약)**

| v2.0 | v2.1 |
|---|---|
| `companyProfile.companySize` | **제거** (서비스가 갖고 있지 않음) |
| `companyProfile.hasExportPerformance` | **제거** |
| `companyProfile.kSureEligible` | **제거** |
| 단일 `contract` 객체 | `contracts` **배열** (분할 결제 지원) |
| `contract.paymentMethod`(계약별) | `companyProfile.paymentTerms`(기업 단위 리스트) |
| `contract.confirmedCashflow` | **제거** — contracts에 실제 계약이 들어있는 것 자체가 확정 현금흐름의 근거 |
| `riskContext.expectedShortfallRate` | `riskContext.expectedLossRate` + `expectedShortfallKrw` |
| (없음) | `riskContext.baseRate`, `breakEvenRate`, `remainingBusinessDays` 추가 |
| `strategyContext.strategies`만 | `hedgeTargetMin`/`hedgeTargetMax`가 `strategyContext`로 이동 |
| (없음) | `companyProfile.monthlyTradeVolumeKrw`, `currentlyHedging` 추가 |

**상태 enum 변경**

| v2.0 | v2.1 | 표시 문구 |
|---|---|---|
| `ELIGIBLE` | **`RECOMMENDED`** | 추천 적합 |
| `CONDITIONAL` | `CONDITIONAL`(유지) | 조건 확인 필요 |
| `RM_REVIEW_REQUIRED` | `RM_REVIEW_REQUIRED`(유지) | 직원 확인 필요 |
| `NOT_ELIGIBLE` | **`NOT_RECOMMENDED`** | 추천 제외 |

필드명(`eligibilityStatus`)은 그대로 유지했습니다 — 프론트엔드가 값만
새 enum으로 갱신하면 되도록 호환성을 최대한 지켰습니다.

## v1.x → v2.0 (이전 개편, 배경은 계속 유효)

v1.x는 자연어 질문에 긴 답변을 생성하는 `POST /rag` 질의응답형
서비스였습니다. 실제 화면에는 질의응답 UI가 없고 "구조화된 입력 → 카드
목록"만 있어, TF-IDF 검색 점수가 상품 노출 순서를 사실상 결정하던 구조를
버리고 규칙 기반 카드 추천으로 전환했습니다. `POST /rag`는 **HTTP 410
Gone**을 반환합니다(이유는 하단 "기존 /rag 마이그레이션 안내" 참고).

## 전체 추천 파이프라인

```
기업·계약·리스크·전략 데이터 입력 (POST /recommend)
  → requestedProductNames를 review_queue로 검증 (verification.py)
  → 검증된 상품만 후보로 구성 (verification.is_candidate_verified)
  → 하드 조건 필터링 — "관찰 가능한" 조건만 (eligibility.py: NOT_RECOMMENDED 즉시 제외)
  → 규칙 기반 적합도(fitScore) 계산 (recommender.py, app/scoring_config.py)
  → 전략(strategyType)-상품 연결, priority·배분 비율 반영
  → 상품별 공식 근거 문서 조회 (evidence_retriever.py — strategyType→가이드
    문서는 고정 매핑, TF-IDF는 보조 검색에만 사용)
  → 카드 표시용 데이터 생성 (card_builder.py — 길이 제한, 금지어 필터,
    분할 결제 반영)
  → source_id 포함 응답 (RecommendResponse)
```

**LLM 역할**: 없습니다. `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` 환경변수는
읽는 코드가 존재하지 않으며, 카드 생성 파이프라인의 어떤 단계도 외부 LLM을
호출하지 않습니다. 상품 순위·자격 판정은 전적으로 `app/eligibility.py`와
`app/recommender.py`의 규칙으로 결정됩니다.

**RAG(검색) 역할**: 상품을 고르지 않습니다. `POST /recommend`가 상품을
확정한 *뒤에* `evidence_retriever.get_product_evidence()`가 근거 문서를
모을 뿐입니다. TF-IDF 검색은 `POST /search`(운영자·개발자용 디버깅
도구)에만 쓰입니다.

## 실행

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/validate_data.py
pytest -v
uvicorn app.main:app --reload
```

LLM API 키(`LLM_*` 환경변수)는 설정하지 않아도 모든 핵심 기능(`/recommend`,
`/search`, `/sources/{id}`, `/products/{id}`)이 동일하게 동작합니다.

## POST /recommend

### 요청 예시 (수출기업 혼합 헤지)

```json
{
  "companyProfile": {
    "tradeDirection": "EXPORT",
    "industry": "MANUFACTURING",
    "mainCountries": ["US"],
    "currencies": ["USD"],
    "monthlyTradeVolumeKrw": 300000000,
    "paymentTerms": ["T/T"],
    "currentlyHedging": false
  },
  "contracts": [
    {
      "tradeDirection": "EXPORT",
      "foreignAmount": 220000,
      "currency": "USD",
      "settlementDate": "2026-10-31",
      "installmentOrder": 1
    }
  ],
  "riskContext": {
    "exposureKrw": 300000000,
    "baseRate": 1363.64,
    "breakEvenRate": 1290,
    "remainingDays": 90,
    "remainingBusinessDays": 64,
    "expectedLossRate": 0.062,
    "expectedShortfallKrw": 18600000,
    "riskLevel": "HIGH",
    "riskPreference": "NEUTRAL"
  },
  "strategyContext": {
    "hedgeTargetMin": 0.2,
    "hedgeTargetMax": 0.5,
    "strategies": [
      {"strategyType": "FX_INSURANCE_GENERAL", "allocationRatio": 0.5, "priority": 1},
      {"strategyType": "FORWARD", "allocationRatio": 0.5, "priority": 2}
    ]
  },
  "options": {"maxCards": 3, "includeConditional": true, "includeEvidenceMap": true},
  "requestedProductNames": []
}
```

`companySize`/`hasExportPerformance`/`kSureEligible`/
`hasForeignCurrencySurplus`/`importItemEligible`은 요청 모델에 **존재하지
않습니다.** `extra="forbid"`가 적용돼 있어 이 필드를 포함해 어떤 정의되지
않은 필드를 보내도 **422**로 거부됩니다(`tests/test_api.py::test_recommend_removed_fields_are_rejected_with_422`
로 검증) — 자세한 이유는 위 "5. 정의되지 않은 요청 필드" 참고.

응답 스키마 개요(실제 응답 예시는 최종 보고서 참고):

```json
{
  "requestId": "rec_20260802_xxxxxxxx",
  "generatedAt": "2026-08-02T04:20:00+09:00",
  "recommendationVersion": "2.4",
  "cards": [
    {
      "rank": 1, "productId": "...", "fitScore": 93,
      "eligibilityStatus": "RECOMMENDED",
      "groupExposureKrw": 270000000,
      "targetHedgeRatio": 0.5,
      "groupTargetHedgeAmountKrw": 135000000,
      "recommendedHedgeAmountKrw": 81000000,
      "exposureCalculationStatus": "CALCULATED",
      "coveredContractIndexes": [0, 1],
      "paymentScheduleSummary": "총 2건 결제 예정 (2026-09-30, 2026-11-30)",
      "exposureGroupId": "EXPORT-USD",
      "coveredTradeDirection": "EXPORT",
      "coveredCurrency": "USD",
      "...": "..."
    }
  ],
  "excludedProducts": [ { "productId": "...", "eligibilityStatus": "NOT_RECOMMENDED", "reasons": ["..."] } ],
  "evidenceMap": { "SRC-017": { "title": "...", "provider": "...", "sourceType": "...", "checkedAt": "..." } },
  "verificationNotices": [ { "requestedName": "KB FX Matching", "status": "NOT_VERIFIED", "action": "EXCLUDE", "message": "..." } ],
  "notices": ["적합도는 입력된 기업 및 계약 정보를 기준으로 산정한 참고 결과입니다.", "..."]
}
```

### 검증 규칙

- `tradeDirection`은 `EXPORT`/`IMPORT`/`BOTH`만 허용, 그 외 값은 422.
- `contracts`는 **최소 1건 필수**(빈 배열이면 422). 여러 건이면 분할 결제로 처리.
- `settlementDate`는 ISO 날짜 형식만 허용(파싱 실패 시 422).
- `foreignAmount`, `exposureKrw`, `remainingDays` 등은 음수 불가(422).
- `strategies[].allocationRatio`는 0~1이고, **같은 노출 그룹에 속한
  전략들의 합**이 1.0을 넘으면 422(그룹이 다르면 각각 최대 1.0까지
  허용 — 자세한 내용은 위 "v2.2 → v2.3" 섹션 참고).
- `companyProfile.currencies`가 있는데 `contracts[].currency`가 그 목록에
  없으면 422(하나라도 불일치하면 전체 요청을 거부).
- `options.maxCards`는 1~10만 허용.
- `strategyContext.hedgeTargetMin > hedgeTargetMax`이면 422.
- `strategies[]`/`groupTargets[]`의 `exposureGroupId`가 `contracts`로
  만들어지는 노출 그룹에 없으면 422, 노출 그룹이 여러 개인데
  `exposureGroupId`를 생략해도 422(단일 그룹이면 생략 허용) — 자세한
  오류 형식은 위 "v2.3 → v2.4" 섹션 참고.
- 잘못된 enum(`tradeDirection`, `strategyType`, `paymentTerms` 등)은 모두
  Pydantic이 자동으로 422를 반환합니다.

### eligibilityStatus

| 값 | 표시 문구 | 의미 |
|---|---|---|
| `RECOMMENDED` | 추천 적합 | 관찰 가능한 조건을 모두 확인했고, 상품 자체도 절차상 항상 직원 확인이 필요하지는 않음 |
| `CONDITIONAL` | 조건 확인 필요 | 이 서비스가 갖고 있지 않은 정보(K-SURE 대상 여부, 신용심사, 외화 여유자금 등) 때문에 아직 판단할 수 없는 항목이 있음 — **자동으로 RECOMMENDED로 승격하지 않음** |
| `RM_REVIEW_REQUIRED` | 직원 확인 필요 | 상품 자체가 실수요·적합성 등 절차상 항상 직원 확인이 필요함(장외파생상품 전 종류, 또는 상품의 recommendation_mode가 이미 RM_REVIEW_REQUIRED) |
| `NOT_RECOMMENDED` | 추천 제외 | 거래 방향·통화·기간처럼 **관찰 가능한** 조건을 명백히 불충족 — 기본 `cards`에서 제외되고 `excludedProducts`에만 나타남 |

`RECOMMENDED`가 아니라고 해서 카드에서 빠지는 것은 아닙니다 —
`NOT_RECOMMENDED`만 `cards`에서 제외됩니다(`options.includeConditional=false`
이면 `CONDITIONAL`도 함께 제외). **어떤 상태도 "가입 승인"·"인수 확정"을
의미하지 않습니다** — `notices`에 항상 이 점을 명시합니다.

### fitScore 산정 원칙

0~100 정수, 가중치는 `app/scoring_config.py` 상수로 분리되어 있습니다
(검색 유사도 점수는 전혀 사용하지 않습니다). **확인할 수 없는 자격조건은
어떤 가중치에도 없습니다** — companySize/kSureEligible 같은 값은
fitScore를 깎지 않고, `pendingConditions`로만 표현됩니다.

| 요소 | 가중치 |
|---|---|
| 1. strategyType 직접 일치 | 40 |
| 2. 전략 priority(1순위 기준, 순위마다 -3) | 최대 8 |
| 3. allocationRatio 반영 | 최대 12 |
| 4. 수출·수입 방향 일치 | 10 |
| 5. 계약통화 일치 | 10 |
| 6. 결제조건(paymentTerms) 일치 | 8 |
| 7. 결제예정일까지의 기간 일치 | 8 |
| 8. 위험등급과 상품의 환율 고정 효과 | 최대 6 |
| 9. 위험 성향과 상품 구조 | 6 |
| 헤지 목표 범위 내 배분 비율 | 5 |
| 10. 현재 환리스크 관리 여부(미헤지 상태면 가산) | 5 |
| recommendation_mode 보정 | 0~+2 |
| 상품 신청 난이도(장외파생상품·합성선물환) | -5 |

각 항목이 점수에 반영된 이유는 카드의 `recommendationReasons`에 그대로
문장으로 나타납니다. 같은 입력에는 항상 동일한 점수·순위가 나옵니다
(`tests/test_scenarios.py::test_added9_deterministic_across_repeated_calls`).

## 분할 결제 처리

`contracts`는 배열입니다 — 하나의 결제일만 있다고 가정하지 않습니다.

- 통화가 같은 계약들은 하나의 카드에서 `coveredContractIndexes`로
  함께 묶입니다.
- 계약이 2건 이상이면 `paymentScheduleSummary`에 "총 N건 결제 예정
  (날짜1, 날짜2, ...)" 형태로 분포를 요약합니다.
- `recommendedHedgeAmountKrw`는 `allocationRatio × 노출액(KRW)`로
  계산합니다 — `riskContext.exposureKrw`가 있으면 그 값을, 없으면
  해당 상품이 커버하는 계약들의 외화금액 합계 × `riskContext.baseRate`를
  사용합니다. 둘 다 없으면 `null`(추측해서 채우지 않음).

## strategyType 목록

`FORWARD`, `MAR`, `FX_OPTION`, `RANGE_FORWARD`, `ENHANCED_FORWARD`,
`PARTICIPATING_FORWARD`, `SEAGULL_FORWARD`, `FX_SWAP`,
`FX_INSURANCE_GENERAL`, `FX_INSURANCE_OPTION`, `FOREIGN_CURRENCY_DEPOSIT`,
`IMPORT_PAYMENT_DEFERRAL`, `EXPORT_RECEIVABLE_FINANCE`,
`EXPORT_WORKING_CAPITAL`, `INTERNAL_MATCHING_NETTING`

`INTERNAL_MATCHING_NETTING`(매칭·네팅)은 어떤 상품에도 연결되어 있지
않습니다 — 가입형 금융상품이 아니라 기업 내부 환위험 관리기법이기
때문입니다. 이 값을 요청하면 카드 대신 `notices`에 안내 문구가 추가되고,
관련 지식문서는 `GUIDE-KB-RISK-001`로 고정 연결됩니다.

27개 상품 중 16개만 strategyType이 있어 카드 후보가 됩니다. 나머지
11개는 실행 채널·보증·정보 서비스로, "환헤지 전략"을 직접 구현하는
상품이 아니어서 카드 화면 대상에서 제외했습니다(데이터 자체는 남아 있고,
`GET /products/{id}`로는 계속 조회할 수 있습니다).

## 상품별 CONDITIONAL / RM_REVIEW_REQUIRED 처리 기준

| 상품군 | 예시 | 기본 상태 | 근거 |
|---|---|---|---|
| K-SURE 환변동보험(일반형·옵션형) | KSURE-FX-001/002 | `CONDITIONAL` | K-SURE 이용 대상 여부·인수한도·최종 인수 가능 여부를 이 서비스가 모름. `pendingConditions`: "K-SURE 이용 대상 기업 여부 확인", "대상 거래 및 통화 조건 확인", "인수한도 및 보험 인수 가능 여부 확인" |
| 선물환·통화옵션·구조화 4종·외환스왑 | FX-HEDGE-001/003/004, FX-STRUCT-001~004 | `RM_REVIEW_REQUIRED`(항상) | 계약금액·통화·결제예정일이 확인돼 fitScore는 계산되지만, 실수요·투자자적합성·거래한도·기본계약은 절차상 항상 직원 확인 대상 |
| Payment Usance·수출환어음·대출 | IMPORT-001, EXPORT-001/002, TRADE-002 | `CONDITIONAL`(관찰조건 미충족 시 제외되지 않는 한) 또는 `RM_REVIEW_REQUIRED`(상품 자체가 RM_REVIEW_REQUIRED 모드) | 신용심사·수출실적·담보/보증 정보가 없음. IMPORT-001은 product_master상 이미 RM_REVIEW_REQUIRED 모드라 그 상태가 우선 적용됨 |
| 외화예금 | FX-DEPOSIT-001/003 | `CONDITIONAL` | 실제 운용 가능한 외화 여유자금 여부·보유기간 정보가 없음. `pendingConditions`: "실제 운용 가능한 외화 여유자금 확인", "예상 보유기간 및 중도해지 가능성 확인" |
| MAR | FX-HEDGE-002 | `RECOMMENDED`(관찰 조건 충족 시) | 스팟 체결이라 별도 직원 확인 절차가 없음 |

## 데이터 파일

- `data/product_master.json`: `strategy_types`, `display.card_summary`/
  `short_cautions`는 유지. `eligibility_rules`는 v2.1에서 세 개 키로
  재구성했습니다.
  - `observable`: `contracts`/`companyProfile`/`riskContext`에서 실제
    관찰 가능한 하드 조건만(통화, 결제조건, 기간, 판매종료 여부). **이
    키의 값만 NOT_RECOMMENDED로 이어질 수 있습니다.**
  - `review_requirements`: 장외파생상품 거래처럼 어떤 입력이 와도 항상
    직원 확인이 필요한 절차 목록. 존재 자체가 `RM_REVIEW_REQUIRED`를
    강제합니다.
  - `unknown_eligibility_notes`: 이 서비스가 갖고 있지 않은 사실(K-SURE
    대상 여부, 신용심사, 외화 여유자금 등). `pendingConditions`에 표시될
    뿐, **절대 하드 차단하지 않습니다.**
- `data/recommendation_rules.json`: `rule_type: "SCORE"`만 사용(변경 없음,
  v2.0에서 이미 하드 조건과 분리).
- `data/review_queue.json`, `data/source_registry.json`,
  `data/knowledge_articles.json`, `data/rag_documents.jsonl`: v2.0과 동일.

## source_id 사용 방식

모든 카드의 `sourceIds`는 그 상품의 `product_master.json.source_ids` +
`STRATEGY_GUIDE_MAP`으로 연결된 가이드 문서의 `source_ids`를 합친
것입니다. `evidenceMap`에는 실제 카드에 쓰인 `sourceIds`만 채워집니다.
존재하지 않는 `source_id`를 조회하면 **404**를 반환합니다.

## review_queue 처리 방식

`requestedProductNames`(선택 입력)는 v2.0과 동일한 순서로 처리됩니다 —
`review_queue.json` 대조 → `recommendation_action`에 따라 차단/정정 →
`product_master` 공식명·별칭 대조 → 어디에도 없으면 `NOT_VERIFIED` +
`EXCLUDE`(새 조건을 지어내지 않음). 예: `"KB MARS"` → `MAR 거래`로 정정
안내, `"KB FX Matching"` → 카드 제외.

## 한계 및 직원 확인이 필요한 영역

- **실수요 확인**: 장외파생상품은 구조화 입력만으로 실수요를 확정할 수
  없어 항상 `RM_REVIEW_REQUIRED`로 귀결됩니다. 결함이 아니라 8단계
  절차(`GUIDE-KB-OTC-001`)상 실제로 직원이 확인해야 하는 단계입니다.
- **K-SURE 이용 대상·인수 가능 여부, 신용심사, 담보·보증, 파생상품
  적합성·거래한도**: 이 서비스가 원천적으로 갖고 있지 않은 정보라 확정
  판단을 하지 않습니다. `unknown_eligibility_notes`로 항상 `pendingConditions`에
  노출됩니다.
- **외화 여유자금 보유 여부**: `FOREIGN_CURRENCY_DEPOSIT` 전략은 후보에는
  포함하되 항상 `CONDITIONAL`로 유보합니다.
- **`requestedProductNames`의 느슨한 문자열 매칭**: 부분 문자열 포함
  여부로 review_queue를 대조합니다.
- **공식 자료 갱신**: `source_registry.json`의 `checked_at`은 모두
  2026-08-02 기준입니다. 정기적으로 재확인이 필요합니다.

## 테스트 실행

```bash
pytest -v
```

- `tests/test_data_integrity.py`(11개): product_id/rule_id/source_id 중복,
  참조 무결성, strategy_types enum, review_queue 연동 여부.
- `tests/test_card_schema.py`(10개): camelCase 직렬화, maxCards, rank
  순차성, fitScore 내림차순/범위, sourceIds ⊆ evidenceMap, 금지어(자격
  충족/가입 가능/승인 가능 포함) 없음.
- `tests/test_scenarios.py`(29개): 기존 8개 시나리오 + v2.1에서 추가된
  12개(K-SURE 정보 미입력 CONDITIONAL, 선물환 항상 RM_REVIEW_REQUIRED,
  Payment Usance CONDITIONAL/RM, 외화예금 CONDITIONAL, 명백한 방향 불일치
  제외, 미입력이 fitScore를 과도하게 깎지 않음, 분할 결제 2건 이상,
  반복 호출 결정론, 승인·확정 표현 없음, review_queue 차단 유지,
  sourceIds/evidenceMap 정합성 등).
- `tests/test_api.py`(19개): 엔드포인트별 상태 코드, 422/404/410 처리,
  정의되지 않은 필드는 422.
- `tests/test_v22_refinements.py`(15개, v2.2): 카드 정렬 기준(priority
  우선·동점 처리), 수출입 겸업 혼합 계약(노출 그룹 분리·교차오염 없음),
  recommendedHedgeAmountKrw 불변조건 4종, requestedProductNames 정규화
  매칭(부분 문자열 오탐 방지·MARS/FX Matching/ONE TRADE 기존 시나리오
  유지), 정의되지 않은 요청 필드 422(최상위·중첩 객체 모두).
- `tests/test_v23_multi_currency.py`(10개, v2.3): 통화별 서로 다른
  baseRate, 계약별 exposureKrw 우선순위, 다중 통화·환율 없음→null(추정
  금지), 노출 그룹별 allocationRatio 검증(같은 그룹 초과 시 422·다른
  그룹은 각각 1.0 허용), 카드별 추천금액 합계 ≤ 그룹 목표 헤지금액,
  통화 간 금액 미혼입, 단일 그룹 하위호환, 금액·순위 결정론.
- `tests/test_v24_exposure_group_validation.py`(8개, v2.4 신규): 존재하지
  않는 strategy/groupTargets exposureGroupId 422, 다중 그룹에서
  exposureGroupId 누락 422(strategies·groupTargets 모두), 단일 그룹
  생략 자동연결 200, 오류 응답에 availableExposureGroupIds 포함, 기존
  다중통화 금액 계산 결과 유지, riskContext.baseRate deprecated 이후에도
  계산 미반영 유지.

## 기존 /rag 마이그레이션 안내

`POST /rag`는 **HTTP 410 Gone**을 반환합니다. `app/generator.py`,
`app/retriever.py`, `app/rules_engine.py`는 v2.0에서 이미 삭제했습니다.
상품 상세가 필요하면 `GET /products/{product_id}`와
`GET /products/{product_id}/evidence`를 사용하세요.

## 상세 조회 엔드포인트

- `GET /products/{product_id}`: 카드에 담기 부족한 상세 정보. 없는 ID는 404.
- `GET /products/{product_id}/evidence`: `sourceIds`, `sources`,
  `relatedGuides`(연결된 운영 가이드). 통화옵션·구조화 상품을 조회하면
  `GUIDE-KB-OTC-001`(8단계 절차)이 항상 포함됩니다.

## 운영 전 추가 작업

1. 영업점 내부 상품설명서와 준법감시 최신본을 승인 저장소에 적재합니다.
2. 문서 유효일(`source_registry.json.checked_at`)과 판매중단 여부를
   정기 점검합니다(`eligibility_rules.observable.product_discontinued`).
3. K-SURE 이용 대상·인수 가능 여부, 신용심사, 파생상품 적합성·거래한도는
   현재도 이미 `unknown_eligibility_notes`/`review_requirements`로
   `pendingConditions`에 노출되고 있습니다 — 실제 운영에서는 이 항목들을
   확인하는 후속 절차(RM 상담, K-SURE 문의 등)와 연결해야 합니다.
4. 응답 로그에 `requestId`, `sourceId`, 확인일, 문서버전을 저장합니다.
5. `monthlyTradeVolumeKrw`, `currentlyHedging`처럼 이번에 새로 추가된
   입력 필드를 프론트엔드가 실제로 채워 보내는지 확인합니다(비어 있으면
   해당 가중치만 적용되지 않을 뿐 오류는 아닙니다).
