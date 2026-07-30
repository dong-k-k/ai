ECOS Open API를 이용하여 USD/KRW 일별 시계열의 통계표 및 세부 항목 정보를 직접 조회하는 기능을 구현하자.

이번 작업의 목적은 다음 두 질문을 ECOS API 응답을 근거로 해결하는 것이다.

1. USD/KRW 시계열의 실제 통계표명과 통계표 코드는 무엇인가?
2. 해당 통계표 안에서 USD/KRW의 항목명과 항목 코드는 무엇인가?

중요한 원칙:

* 인터넷 블로그에 적힌 통계표 코드나 항목 코드를 그대로 하드코딩하지 않는다.
* `731Y001`, `0000001`과 같은 값을 정답이라고 미리 가정하지 않는다.
* ECOS API의 메타데이터 조회 결과에서 직접 후보를 찾고 검증한다.
* 기존 코드와 기존 주석은 임의로 삭제하지 않는다.
* 요청하지 않은 리팩터링은 하지 않는다.
* API 인증키를 코드에 하드코딩하지 않는다.
* 현재 단계에서는 단위, 관측 시점, 제공 기간, 결측치 처리까지 분석하지 않는다.
* 다만 API 응답에 관련 필드가 있으면 삭제하지 말고 원본 결과에는 보존한다.

## 1단계: 기존 프로젝트 확인

먼저 현재 프로젝트 구조와 ECOS 관련 코드를 확인하라.

다음을 찾아서 간단히 보고하라.

* 기존 ECOS API 호출 코드
* API 키를 읽는 방식
* 데이터 저장 디렉터리
* `requests`, `pandas`, `python-dotenv` 사용 여부
* 재사용 가능한 함수
* 새로 만들거나 수정해야 할 파일

기존 구현이 있다면 가능한 한 재사용하고, 중복 코드를 만들지 않는다.

구현 전에 다음 형식으로 작업 범위를 먼저 설명하라.

```text
수정 대상 파일:
- ...

추가 대상 파일:
- ...

구현 순서:
1. ...
2. ...
3. ...

기존 코드 보존 사항:
- ...
```

## 2단계: ECOS 인증키 처리

인증키는 환경변수에서 읽는다.

```text
ECOS_API_KEY
```

`.env`를 사용한다면 다음 형태를 지원한다.

```env
ECOS_API_KEY=발급받은_인증키
```

인증키가 없으면 요청을 보내지 말고 다음과 같이 명확한 오류를 출력한다.

```text
ECOS_API_KEY 환경변수가 설정되지 않았습니다.
```

로그나 예외 메시지에 전체 인증키가 노출되지 않도록 한다.

## 3단계: 통계표 목록 조회

ECOS의 `StatisticTableList` 서비스를 호출하여 통계표 목록을 가져온다.

URL은 다음 구조를 사용한다.

```text
https://ecos.bok.or.kr/api/StatisticTableList/{API_KEY}/json/kr/{START}/{END}
```

다음 조건을 만족해야 한다.

* 응답 형식은 JSON으로 요청한다.
* HTTP timeout을 설정한다.
* HTTP 오류를 확인한다.
* ECOS가 반환하는 오류 코드와 오류 메시지를 확인한다.
* `list_total_count`를 이용하여 전체 페이지를 조회한다.
* 한 번에 가져올 수 있는 최대 건수를 무작정 가정하지 않는다.
* 응답의 `StatisticTableList.row`를 DataFrame으로 변환한다.

통계표 후보를 찾기 위해 다음 검색어를 각각 적용한다.

```text
환율
대원화
미국달러
주요국 통화
원/미국달러
```

검색은 정확히 일치하는 경우만 찾지 말고, 통계표명에 검색어가 포함되는 경우를 모두 수집한다.

후보 결과에서는 API 응답에 존재하는 다음 필드를 가능한 한 출력한다.

```text
STAT_CODE
STAT_NAME
CYCLE
SRCH_YN
ORG_NAME
```

실제 응답에 필드명이 다르거나 일부 필드가 없다면, 존재하는 필드만 사용하고 임의로 만들지 않는다.

후보를 다음 우선순위로 정렬한다.

1. 일별 주기를 지원하는 통계표
2. 통계표명에 `대원화환율` 또는 유사 표현이 있는 통계표
3. 통계표명에 `주요국 통화` 또는 `미국달러`가 포함된 통계표
4. 현재 검색 가능한 통계표

단, 이 단계에서 후보 하나를 성급하게 확정하지 않는다.

## 4단계: 통계표별 세부 항목 조회

앞에서 찾은 통계표 후보 각각에 대해 `StatisticItemList` 서비스를 호출한다.

URL은 다음 구조를 사용한다.

```text
https://ecos.bok.or.kr/api/StatisticItemList/{API_KEY}/json/kr/{START}/{END}/{STAT_CODE}
```

다음 조건을 만족해야 한다.

* 각 후보 통계표의 전체 항목을 페이지네이션하여 조회한다.
* 응답의 `StatisticItemList.row`를 DataFrame으로 변환한다.
* 통계표별 원본 응답을 구분하여 저장한다.
* 후보 하나에서 오류가 발생해도 전체 프로그램이 즉시 중단되지 않도록 한다.
* 실패한 통계표 코드와 실패 원인을 마지막에 정리한다.

세부 항목에서는 다음 검색어를 적용한다.

```text
미국달러
원/미국달러
달러
USD
매매기준율
```

다음 필드를 우선 확인한다.

```text
STAT_CODE
STAT_NAME
ITEM_CODE
ITEM_NAME
ITEM_CODE1
ITEM_NAME1
ITEM_CODE2
ITEM_NAME2
ITEM_CODE3
ITEM_NAME3
ITEM_CODE4
ITEM_NAME4
CYCLE
UNIT_NAME
START_TIME
END_TIME
DATA_CNT
```

ECOS 응답에 모든 필드가 존재한다고 가정하지 않는다. 실제로 반환된 필드만 출력하며, 항목 코드가 `ITEM_CODE`가 아니라 `ITEM_CODE1` 등에 존재할 가능성도 확인한다.

## 5단계: USD/KRW 후보 판정

USD/KRW 일별 시계열의 최종 후보는 다음 조건으로 판정한다.

필수 조건:

* 미국 달러와 원화 사이의 환율임이 항목명에서 확인된다.
* 일별 조회가 가능한 통계표 또는 항목이다.
* 실제 통계 조회에 사용할 수 있는 통계표 코드와 항목 코드가 모두 존재한다.

우선 조건:

* 항목명에 `원/미국달러`가 명시되어 있다.
* 항목명에 환율 산정 기준이 함께 표시되어 있다.
* 통계표명이 주요국 통화의 대원화 환율을 의미한다.

후보가 여러 개라면 임의로 하나만 선택하지 말고 다음 표를 먼저 출력한다.

```text
통계표 코드 | 통계표명 | 주기 | 항목 코드 | 항목명 | 선정 여부 | 판단 근거
```

최종 후보를 하나 선정한 경우에도 다른 후보를 제외한 이유를 간단히 기록한다.

## 6단계: 실제 데이터 조회로 최소 검증

선정한 통계표 코드와 항목 코드가 실제로 유효한지 확인하기 위해 `StatisticSearch`를 사용하여 짧은 기간의 데이터만 조회한다.

URL 구조:

```text
https://ecos.bok.or.kr/api/StatisticSearch/{API_KEY}/json/kr/{START}/{END}/{STAT_CODE}/D/{START_DATE}/{END_DATE}/{ITEM_CODE1}
```

검증 목적이므로 최근에 데이터가 있을 가능성이 높은 짧은 기간만 사용한다.

다음 사항을 확인한다.

* HTTP 요청 성공 여부
* ECOS 오류 응답 여부
* `StatisticSearch.row` 존재 여부
* 반환된 `STAT_CODE`
* 반환된 `STAT_NAME`
* 반환된 `ITEM_CODE1`
* 반환된 `ITEM_NAME1`
* 반환된 `TIME`
* 반환된 `DATA_VALUE`

이 단계는 통계표 코드와 항목 코드 조합이 실제 조회 가능한지 검증하기 위한 것이다. 환율값 자체를 분석하거나 예측에 사용하지는 않는다.

최근 기간에 데이터가 없어 결과가 비어 있다면 코드가 틀렸다고 즉시 단정하지 말고, 조회 기간을 이전 영업일 구간으로 한 번 확장한다.

## 7단계: 결과 저장

다음 파일을 저장한다. 기존 프로젝트 구조에 더 적절한 경로가 있다면 그 구조를 우선한다.

```text
data/raw/ecos/statistic_tables.json
data/raw/ecos/statistic_items_{STAT_CODE}.json
data/raw/ecos/usdkrw_sample.json
data/processed/ecos/usdkrw_table_candidates.csv
data/processed/ecos/usdkrw_item_candidates.csv
data/processed/ecos/usdkrw_metadata.json
```

`usdkrw_metadata.json`은 다음 구조로 저장한다.

```json
{
  "stat_code": "API에서 확인한 값",
  "stat_name": "API에서 확인한 값",
  "cycle": "API에서 확인한 값",
  "item_code": "API에서 확인한 값",
  "item_name": "API에서 확인한 값",
  "verification": {
    "success": true,
    "sample_time": "API에서 확인한 값",
    "sample_value": "API에서 확인한 값"
  },
  "source": "Bank of Korea ECOS Open API"
}
```

## 8단계: 현재 구현에서 사용하는 변수·필드 정리

이번 작업에서 실제로 사용한 이름은 다음과 같이 정리한다.

### 8.1 환경 변수

```text
ECOS_API_KEY
```

- 값의 형식: 문자열
- 역할: ECOS Open API 인증키
- 저장 위치: 프로젝트 루트의 `.env` 파일
- 코드에서의 사용: `get_api_key()` 함수

### 8.2 ECOS 서비스 이름

```text
StatisticTableList
StatisticItemList
StatisticSearch
```

- `StatisticTableList`: 통계표 목록 조회
- `StatisticItemList`: 통계표별 세부 항목 조회
- `StatisticSearch`: 실제 데이터 조회 검증

### 8.3 요청 경로 형식

```text
StatisticTableList: /api/StatisticTableList/{API_KEY}/json/kr/{START}/{END}
StatisticItemList: /api/StatisticItemList/{API_KEY}/json/kr/{START}/{END}/{STAT_CODE}
StatisticSearch: /api/StatisticSearch/{API_KEY}/json/kr/{START}/{END}/{STAT_CODE}/D/{START_DATE}/{END_DATE}/{ITEM_CODE1}
```

실제 구현에서는 다음처럼 사용한다.

```text
StatisticTableList -> 1/100
StatisticItemList -> 1/100/{STAT_CODE}
StatisticSearch -> 1/100/{STAT_CODE}/D/{START_DATE}/{END_DATE}/{ITEM_CODE1}
```

### 8.4 통계표 응답에서 사용하는 필드

통계표 후보를 만들 때 주로 사용한 필드는 다음과 같다.

```text
STAT_CODE
STAT_NAME
CYCLE
SRCH_YN
ORG_NAME
priority_score
```

- `STAT_CODE`: 통계표 코드
- `STAT_NAME`: 통계표명
- `CYCLE`: 주기 (예: D, M)
- `SRCH_YN`: 검색 가능 여부
- `ORG_NAME`: 산정 기관명
- `priority_score`: 후보 우선순위 점수

### 8.5 세부 항목 응답에서 사용하는 필드

항목 후보를 찾을 때 주로 사용한 필드는 다음과 같다.

```text
STAT_CODE
STAT_NAME
ITEM_CODE
ITEM_NAME
ITEM_CODE1
ITEM_NAME1
ITEM_CODE2
ITEM_NAME2
ITEM_CODE3
ITEM_NAME3
ITEM_CODE4
ITEM_NAME4
CYCLE
UNIT_NAME
START_TIME
END_TIME
DATA_CNT
score
```

- `ITEM_CODE` 또는 `ITEM_CODE1` 등: 항목 코드
- `ITEM_NAME` 또는 `ITEM_NAME1` 등: 항목명
- `UNIT_NAME`: 단위명
- `START_TIME`, `END_TIME`: 제공 시작/종료 시점
- `DATA_CNT`: 데이터 건수
- `score`: USD/KRW 관련성 점수

### 8.6 후보 선정 결과에서 사용하는 필드

후보 선정 표를 저장할 때 쓰는 필드는 다음과 같다.

```text
STAT_CODE
STAT_NAME
CYCLE
ITEM_CODE
ITEM_NAME
SELECTION
JUDGMENT_REASON
```

- `SELECTION`: `YES` 또는 `NO`
- `JUDGMENT_REASON`: 선정/탈락 이유

### 8.7 검증 결과에서 사용하는 필드

실제 데이터 조회 검증 단계에서 쓰는 필드는 다음과 같다.

```text
success
sample_time
sample_value
stat_code
item_code
stat_name
item_name
```

### 8.8 저장되는 메타데이터 JSON 구조

```json
{
  "stat_code": "string",
  "stat_name": "string",
  "cycle": "string",
  "item_code": "string",
  "item_name": "string",
  "verification": {
    "success": true,
    "sample_time": "string",
    "sample_value": "string"
  },
  "source": "Bank of Korea ECOS Open API"
}
```

### 8.9 시계열 저장용 컬럼

실제 시계열 CSV에 저장하는 컬럼은 다음과 같다.

```text
date
value
item_code
item_name
unit_name
series_code
notes
```

이 규칙은 이후 JPY/KRW, EUR/KRW, CNY/KRW 확장 시에도 동일하게 유지한다.

API 응답에 없는 값을 추측하여 채우지 않는다. 확인하지 못한 값은 `null`로 기록하고 그 이유를 함께 남긴다.

## 8단계: 코드 구조

가능하면 다음처럼 기능을 분리한다.

```python
def get_api_key() -> str:
    ...

def request_ecos(service: str, path_params: list[str]) -> dict:
    ...

def fetch_all_pages(
    service: str,
    extra_params: list[str] | None = None,
) -> list[dict]:
    ...

def search_statistic_tables(rows: list[dict]) -> pd.DataFrame:
    ...

def fetch_statistic_items(stat_code: str) -> list[dict]:
    ...

def search_usdkrw_items(rows: list[dict]) -> pd.DataFrame:
    ...

def verify_series(
    stat_code: str,
    item_code: str,
) -> dict:
    ...

def save_results(...) -> None:
    ...

def main() -> None:
    ...
```

함수명은 기존 프로젝트 스타일에 맞게 조정할 수 있다.

다음 예외를 명확히 처리한다.

* 인증키 누락
* 네트워크 연결 실패
* HTTP 오류
* JSON 파싱 실패
* ECOS 오류 코드
* 예상한 서비스 키가 응답에 없음
* `row`가 없음
* 검색 결과가 없음
* 후보가 둘 이상이라 자동 확정하기 어려움
* 실제 데이터 검증 실패

## 9단계: 실행 결과 출력

프로그램 실행이 끝나면 다음 형식으로 출력한다.

```text
[ECOS USD/KRW 메타데이터 조회 결과]

1. 통계표
- 통계표명:
- 통계표 코드:
- 주기:

2. 세부 항목
- 항목명:
- 항목 코드:

3. 실제 조회 검증
- 검증 성공 여부:
- 샘플 기준 시점:
- 샘플 데이터 존재 여부:

4. 근거
- 선택된 통계표 후보 수:
- 선택된 항목 후보 수:
- 다른 후보를 제외한 이유:

5. 저장 파일
- ...
```

아직 확인되지 않은 내용은 다음처럼 분리한다.

```text
이번 단계에서 확인한 내용
- 통계표명과 통계표 코드
- USD/KRW 항목명과 항목 코드

다음 단계에서 확인할 내용
- 단위
- 관측 시점과 환율 산정 기준
- 실제 제공 기간
- 결측치 처리
- 수정치 처리
```

## 10단계: 작업 완료 보고

작업을 마치면 다음 내용을 보고한다.

* 수정하거나 추가한 파일
* 호출한 ECOS API 서비스
* 발견한 통계표 후보
* 발견한 USD/KRW 항목 후보
* 최종 선정 결과
* 실제 데이터 조회 검증 결과
* 저장한 원본 및 가공 파일
* 실행 명령어
* 오류 또는 아직 확정할 수 없는 사항

중요:

* 통계표 코드와 항목 코드를 추측해서 결과를 작성하지 않는다.
* 실제 ECOS API 응답에서 확인된 값만 최종 결과로 인정한다.
* 기존 코드와 주석을 임의로 삭제하지 않는다.
* 이번 작업 범위 밖의 환율 예측 코드나 Chronos 코드는 수정하지 않는다.

## 추가 메타데이터 및 데이터 품질 확인

통계표와 USD/KRW 항목을 확정한 뒤, `StatisticItemList`와 `StatisticSearch` 응답을 이용해 다음 항목도 확인하라.

### 1. 단위 확인

`StatisticItemList` 응답에서 다음 필드를 추출한다.

```text
ITEM_NAME
UNIT_NAME
```

단위를 임의로 추정하지 말고 다음 형식으로 출력한다.

```text
항목명:
API 단위:
단위 해석:
```

`UNIT_NAME`만으로 기준 외화 수량을 알 수 없다면 `ITEM_NAME`과 함께 해석한다.

예를 들어 항목명이 `원/미국달러`라면 미국달러 1단위당 원화로 해석할 수 있는지 표시하되, API 응답만으로 확정할 수 없는 경우 `공식 설명자료 추가 확인 필요`로 기록한다.

### 2. 관측 기준 확인

다음 필드에서 관측 기준을 나타내는 표현을 찾는다.

```text
STAT_NAME
ITEM_NAME
```

다음 키워드를 탐색한다.

```text
매매기준율
시장평균환율
종가
고시환율
기준환율
평균
```

항목명에 `매매기준율`이 포함되어 있으면 해당 사실을 기록한다.

단, API 응답만으로 다음 내용을 추측하지 않는다.

* 정확한 산출 시각
* 거래량 가중평균 여부
* 직전 거래일 반영 여부
* 특정 은행 고시값인지 여부

이 내용은 `공식 통계설명자료에서 추가 확인할 항목`으로 분리한다.

### 3. 데이터 주기와 제공 기간 확인

`StatisticItemList`에서 다음 필드를 확인한다.

```text
CYCLE
START_TIME
END_TIME
DATA_CNT
```

다음 형식으로 출력한다.

```text
데이터 주기:
메타데이터상 시작 시점:
메타데이터상 종료 시점:
메타데이터상 관측값 수:
```

이후 `StatisticSearch`를 이용해 전체 제공 기간 또는 구간별 페이지 조회를 수행하고 실제 반환 데이터에서 다음을 계산한다.

```text
실제 최초 TIME
실제 최종 TIME
실제 행 개수
중복 TIME 개수
빈 DATA_VALUE 개수
```

메타데이터의 `START_TIME`, `END_TIME`, `DATA_CNT`와 실제 조회 결과가 다르면 양쪽 값을 모두 보존하고 차이를 보고한다.

### 4. 결측치 확인

`StatisticSearch` 결과에서 다음을 검사한다.

* `DATA_VALUE`가 null인 행
* `DATA_VALUE`가 빈 문자열인 행
* 숫자로 변환할 수 없는 값
* 동일한 `TIME`이 두 번 이상 존재하는 중복
* 조회 기간 중 반환되지 않은 날짜

누락 날짜를 다음 두 종류로 구분한다.

```text
구조적 비관측 후보
- 토요일
- 일요일
- 공휴일
- 외환시장 휴장일

실제 결측 후보
- 일반적인 영업일인데 데이터가 없음
- 행은 있으나 DATA_VALUE가 비어 있음
- 중복 또는 비정상 값이 존재함
```

공휴일 정보가 없어 구조적 비관측과 실제 결측을 확정할 수 없다면 임의로 판단하지 말고 `휴장일 달력 추가 검증 필요`로 기록한다.

결측값을 0, 전일값 또는 보간값으로 자동 대체하지 않는다.

### 5. 수정치 확인 가능성

현재 API 응답에 다음 정보가 있는지 확인한다.

```text
잠정치 여부
확정치 여부
수정 일자
이전 값
수정 사유
```

관련 필드가 없다면 다음과 같이 기록한다.

```text
ECOS 현재 응답만으로 과거 수정 이력을 직접 확인할 수 없음
```

API 호출 시마다 다음 정보를 스냅샷으로 저장할 수 있도록 구조를 만든다.

```text
fetched_at
STAT_CODE
ITEM_CODE
TIME
DATA_VALUE
```

이전 스냅샷이 존재하면 동일한 `TIME`의 `DATA_VALUE`를 비교하여 변경된 값을 별도 파일에 기록한다.

```text
data/processed/ecos/usdkrw_revision_candidates.csv
```

출력 필드:

```text
TIME
previous_value
current_value
previous_fetched_at
current_fetched_at
```

### 6. 최종 출력 구분

결과를 다음 세 범주로 나누어 보고한다.

```text
API에서 직접 확인된 내용
- 통계표명과 코드
- 항목명과 코드
- 단위 필드
- 데이터 주기
- 제공 시작·종료 시점
- 실제 조회 행 수
- 빈 값과 중복 여부

API 결과로 해석 가능한 내용
- 원/미국달러 표시의 단위 해석
- 항목명에 표시된 매매기준율 여부

공식 설명자료가 추가로 필요한 내용
- 매매기준율의 정확한 산출 방식
- 고시 시점과 실제 거래 시점
- 잠정치·확정치 여부
- 공식 수정 정책
```
