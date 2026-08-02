# KB·K-SURE 기업 외환 상품 공식 검증 보고서

- 검증 기준일: 2026-08-02
- 검증 범위: KB국민은행 공식 웹·약관·사용자 제공 KB 공식 PDF, K-SURE 공식 웹페이지
- 데이터 구성: 상품·서비스 27건, 출처 25건, 추천 규칙 33건, 지식문서 6건
- 사용 원칙: 복합 장외파생상품은 자동 확정 추천을 금지하고, K-SURE 상품은 제공기관과 자격요건을 별도로 표시합니다.

## 1. 이번 업데이트의 검증 결과

- 업로드된 KB 거래안내에서 선물환, 통화옵션, Range/Enhanced/Participating/Seagull Forward가 확인되었습니다.
- KB 장외파생상품은 투자자 구분, 투자정보 확인, 실수요·적합성 확인, 한도 설정, 기본계약, 거래확인, 사후관리 절차를 거칩니다.
- 인터넷 선물환은 체결 후 단순 변경·취소가 불가하며 조기결제와 반대거래가 가능합니다. 반대거래 시 시장환율에 따른 정산손익이 발생할 수 있습니다.
- K-SURE 환변동보험 일반형과 옵션형을 별도 상품으로 추가했습니다. 일반형은 유리한 환율에서 이익금 납부 가능성이 있고, 옵션형은 이익금 납부가 없는 대신 보험료와 기간·결제 제한이 있습니다.

## 2. 검증 상품·서비스

| ID | 제공기관 | 공식 명칭 | 카테고리 | 추천 모드 | 출처 |
|---|---|---|---|---|---|
| FX-PLATFORM-001 | KB국민은행 | KB Star FX | 기업 인프라/거래 플랫폼 | SUPPLEMENTARY | [SRC-001](https://fx.kbstar.com/quics?page=C110657) / [SRC-002](https://img2.kbstar.com/obj/ocommon/230317_kbstarfx_terms_n.pdf) / [SRC-003](https://img2.kbstar.com/obj/ocommon/240708_kbstarfx_user_manual.pdf) |
| FX-HEDGE-001 | KB국민은행 | 인터넷 선물환 거래 | 환리스크 헤지 | AUTO_WITH_GUARDRAILS | [SRC-002](https://img2.kbstar.com/obj/ocommon/230317_kbstarfx_terms_n.pdf) / [SRC-003](https://img2.kbstar.com/obj/ocommon/240708_kbstarfx_user_manual.pdf) / [SRC-004](https://obiz.kbstar.com/quics?page=C101981) / [SRC-017](sources/kb_fx_derivatives_and_risk_management.pdf) / [SRC-018](sources/kb_internet_spot_forward_terms.pdf) |
| FX-HEDGE-002 | KB국민은행 | MAR 거래 | 환리스크 분산 | AUTO_WITH_GUARDRAILS | [SRC-002](https://img2.kbstar.com/obj/ocommon/230317_kbstarfx_terms_n.pdf) / [SRC-003](https://img2.kbstar.com/obj/ocommon/240708_kbstarfx_user_manual.pdf) |
| FX-HEDGE-003 | KB국민은행 | 외환스왑 거래 | 환리스크·외화유동성 관리 | RM_REVIEW_REQUIRED | [SRC-002](https://img2.kbstar.com/obj/ocommon/230317_kbstarfx_terms_n.pdf) / [SRC-003](https://img2.kbstar.com/obj/ocommon/240708_kbstarfx_user_manual.pdf) |
| FX-EXEC-001 | KB국민은행 | KB환율픽(Pick) | 외화매매 실행 | AUTO_WITH_GUARDRAILS | [SRC-005](https://obiz.kbstar.com/quics?page=C101935) |
| FX-PLATFORM-002 | KB국민은행 | 마이딜링룸Pro | 기업 인프라/거래 플랫폼 | SUPPLEMENTARY | [SRC-006](https://obiz.kbstar.com/quics?page=C101682) |
| FX-DEPOSIT-001 | KB국민은행 | 외화정기예금 | 외화 운용 | AUTO_WITH_GUARDRAILS | [SRC-007](https://obiz.kbstar.com/quics?page=C101930) |
| FX-DEPOSIT-002 | KB국민은행 | KB수출입기업우대 외화통장 | 외화 운용 | AUTO_WITH_GUARDRAILS | [SRC-008](https://obiz.kbstar.com/quics?QSL=&cc=b102196%3Ab103478&page=C101932&%EB%B8%8C%EB%9E%9C%EB%93%9C%EC%83%81%ED%92%88%EB%AA%85=KB%EC%88%98%EC%B6%9C%EC%9E%85%EA%B8%B0%EC%97%85%EC%9A%B0%EB%8C%80%EC%99%B8%ED%99%94%ED%86%B5%EC%9E%A5&%EB%B8%8C%EB%9E%9C%EB%93%9C%EC%83%81%ED%92%88%EC%BD%94%EB%93%9C=FD01000948) |
| FX-DEPOSIT-003 | KB국민은행 | KB WISE 외화정기예금 | 외화 운용 | AUTO_WITH_GUARDRAILS | [SRC-009](https://obiz.kbstar.com/quics?QSL=&cc=b102196%3Ab103478&page=C101932&%EB%B8%8C%EB%9E%9C%EB%93%9C%EC%83%81%ED%92%88%EB%AA%85=KB+WISE+%EC%99%B8%ED%99%94%EC%A0%95%EA%B8%B0%EC%98%88%EA%B8%88&%EB%B8%8C%EB%9E%9C%EB%93%9C%EC%83%81%ED%92%88%EC%BD%94%EB%93%9C=FD01000955) |
| EXPORT-001 | KB국민은행 | 수출환어음매입(추심) | 수출금융 | RM_REVIEW_REQUIRED | [SRC-010](https://obiz.kbstar.com/quics?page=C105749) / [SRC-011](https://obiz.kbstar.com/quics?page=C101674) |
| EXPORT-002 | KB국민은행 | KB 수출기업 우대대출 | 수출금융 | RM_REVIEW_REQUIRED | [SRC-012](https://obiz.kbstar.com/quics?page=C016287) |
| TRADE-SUPPORT-001 | KB국민은행 | 수출패키지 우대금융 | 수출입 정책·보증 연계금융 | RM_REVIEW_REQUIRED | [SRC-011](https://obiz.kbstar.com/quics?page=C101674) |
| IMPORT-001 | KB국민은행 | KB Payment Usance | 수입금융 | RM_REVIEW_REQUIRED | [SRC-013](https://obiz.kbstar.com/quics?page=C102065) / [SRC-011](https://obiz.kbstar.com/quics?page=C101674) |
| IMPORT-002 | KB국민은행 | 수입신용장 개설 | 수입금융 | RM_REVIEW_REQUIRED | [SRC-010](https://obiz.kbstar.com/quics?page=C105749) / [SRC-011](https://obiz.kbstar.com/quics?page=C101674) |
| IMPORT-003 | KB국민은행 | 선취화물보증(L/G) 발급 | 수입금융 | RM_REVIEW_REQUIRED | [SRC-010](https://obiz.kbstar.com/quics?page=C105749) |
| TRADE-001 | KB국민은행 | 내국신용장 | 국내 수출공급망 금융 | RM_REVIEW_REQUIRED | [SRC-010](https://obiz.kbstar.com/quics?page=C105749) |
| TRADE-002 | KB국민은행 | 무역금융 | 수출금융 | RM_REVIEW_REQUIRED | [SRC-010](https://obiz.kbstar.com/quics?page=C105749) / [SRC-011](https://obiz.kbstar.com/quics?page=C101674) |
| TRADE-003 | KB국민은행 | 글로벌구매론 | 수입·구매금융 | RM_REVIEW_REQUIRED | [SRC-010](https://obiz.kbstar.com/quics?page=C105749) |
| TRADE-SERVICE-001 | KB국민은행 | 전자무역(EDI) | 기업 인프라/무역 플랫폼 | SUPPLEMENTARY | [SRC-010](https://obiz.kbstar.com/quics?page=C105749) |
| TRADE-SERVICE-002 | KB국민은행 | 해외거래처 신용조사 | 무역 리스크 관리 | SUPPLEMENTARY | [SRC-014](https://obiz.kbstar.com/quics?page=C101670) |
| FX-HEDGE-004 | KB국민은행 | 통화옵션(콜옵션·풋옵션) | 환리스크 헤지 | RM_REVIEW_REQUIRED | [SRC-017](sources/kb_fx_derivatives_and_risk_management.pdf) |
| FX-STRUCT-001 | KB국민은행 | Range Forward | 구조화 환헤지 | RM_REVIEW_REQUIRED | [SRC-017](sources/kb_fx_derivatives_and_risk_management.pdf) |
| FX-STRUCT-002 | KB국민은행 | Enhanced Forward | 구조화 환헤지 | RM_REVIEW_REQUIRED | [SRC-017](sources/kb_fx_derivatives_and_risk_management.pdf) |
| FX-STRUCT-003 | KB국민은행 | Participating Forward | 구조화 환헤지 | RM_REVIEW_REQUIRED | [SRC-017](sources/kb_fx_derivatives_and_risk_management.pdf) |
| FX-STRUCT-004 | KB국민은행 | Seagull Forward | 구조화 환헤지 | RM_REVIEW_REQUIRED | [SRC-017](sources/kb_fx_derivatives_and_risk_management.pdf) |
| KSURE-FX-001 | K-SURE(한국무역보험공사) | K-SURE 환변동보험(선물환 방식·일반형) | 정책형 환헤지·무역보험 | AUTO_WITH_GUARDRAILS | [SRC-019](https://www.ksure.or.kr/rh-fx/cntnts/i-512/dir.do) / [SRC-020](https://www.ksure.or.kr/rh-fx/cntnts/i-517/web.do) / [SRC-022](https://www.ksure.or.kr/rh-fx/cntnts/i-514/web.do) / [SRC-023](https://www.ksure.or.kr/rh-fx/cntnts/i-516/web.do) / [SRC-024](https://www.ksure.or.kr/rh-kr/cntnts/i-254/web.do) / [SRC-025](https://www.ksure.or.kr/rh-fx/cntnts/i-515/web.do) |
| KSURE-FX-002 | K-SURE(한국무역보험공사) | K-SURE 환변동보험(옵션형) | 정책형 환헤지·무역보험 | AUTO_WITH_GUARDRAILS | [SRC-019](https://www.ksure.or.kr/rh-fx/cntnts/i-512/dir.do) / [SRC-021](https://www.ksure.or.kr/rh-kr/cntnts/i-264/web.do) / [SRC-022](https://www.ksure.or.kr/rh-fx/cntnts/i-514/web.do) / [SRC-023](https://www.ksure.or.kr/rh-fx/cntnts/i-516/web.do) / [SRC-024](https://www.ksure.or.kr/rh-kr/cntnts/i-254/web.do) / [SRC-025](https://www.ksure.or.kr/rh-fx/cntnts/i-515/web.do) |

## 3. 사용자 제공 목록 검증 결과

| 입력 명칭 | 상태 | 공식·대체 명칭 | RAG 처리 | 판단 |
|---|---|---|---|---|
| KB MARS (Market Average Rate System) | RENAME_AND_CORRECT | MAR 거래 | ACTIVE_AFTER_CORRECTION | 공식 표기는 MAR입니다. 당일 USD/KRW 거래량 가중평균 환율이며, 일정 기간 평균으로 미래 위험을 분산하는 상품 설명은 부정확합니다. |
| KB 통화스왑(CRS) | RM_DOCUMENT_REQUIRED | 통화스왑(CRS) 장외파생상품 | DO_NOT_AUTO_RECOMMEND | KB가 통화스왑을 취급하는 범주는 확인되지만, 현재 공개된 표준 상품 조건과 기업 고객 적합성 기준이 부족합니다. KB Star FX의 외환스왑과 구분해야 합니다. |
| KB 통화옵션(FX Option) | VERIFIED_FROM_UPLOADED_KB_PDF | 통화옵션(콜옵션·풋옵션) | ADD_AS_RM_REVIEW_REQUIRED | 업로드된 KB 공식 거래안내에서 통화옵션, 콜옵션·풋옵션의 활용과 옵션 프리미엄 위험을 확인했습니다. 장외파생상품이므로 자동 확정 추천은 금지하고 적합성·실수요·한도 확인 후 상담 후보로 제시합니다. |
| 외화 MMM | NOT_VERIFIED | - | EXCLUDE | 현재 KB 공식 기업 외화예금 목록에서 해당 명칭을 확인하지 못했습니다. MMDA와 혼동 가능성이 있습니다. |
| KB외화MMDA | VERIFY_TARGET_CUSTOMER | KB외화MMDA | DO_NOT_AUTO_RECOMMEND_TO_CORPORATE | 공식 보호금융상품 등록부에서 명칭은 확인되지만 공개 금리 화면은 개인용으로 표시됩니다. 기업 가입대상과 조건을 내부 상품설명서로 확인해야 합니다. |
| KB 무소구권 수출채권 매입(Forfaiting/Factoring) | NOT_VERIFIED_AS_CURRENT_STANDARD_PRODUCT | - | EXCLUDE_UNTIL_RM_DOC | 현재 공개 KB 공식 페이지에서 해당 표준 상품명과 무소구 조건을 확인하지 못했습니다. 수출환어음매입의 소구권 여부를 자동으로 무소구로 단정하면 안 됩니다. |
| KB EDI 수출팩토링 | NOT_VERIFIED | - | EXCLUDE | EDI 채널은 확인되지만 EDI 수출팩토링이라는 현재 표준 상품은 확인되지 않았습니다. |
| KB 수출기업 국내 운전자금 외화대출 | NAME_NOT_VERIFIED | KB 수출기업 우대대출 또는 K-SURE 연계 일반·협약운전자금대출 | REPLACE_WITH_VERIFIED_PRODUCTS | 입력 명칭 그대로의 공개 상품을 찾지 못했습니다. 현재 확인되는 수출기업 대출과 K-SURE 연계 운전자금으로 대체합니다. |
| KB 외화 무역대출(Import Trade Loan) | NAME_NOT_VERIFIED | KB Payment Usance/글로벌구매론/수입신용장 개설 | REPLACE_BY_PAYMENT_STRUCTURE | 입력 명칭 그대로의 공개 상품을 찾지 못했습니다. 송금방식이면 Payment Usance, L/C 방식이면 수입신용장, 구매 선지급이면 글로벌구매론을 검토합니다. |
| KB 수입패키지 우대금융 | RENAME | 수출패키지 우대금융 | ACTIVE_AFTER_RENAME | 공식 명칭은 수출패키지 우대금융이며 수입기업의 수입신용장과 Payment Usance도 지원합니다. |
| KB FX Matching 상계 처리 서비스 | NOT_VERIFIED | - | EXCLUDE | 현재 공개 KB 공식 출처에서 독립 상품 또는 서비스로 확인하지 못했습니다. 고객의 자연상계 전략과 은행 상품을 구분해야 합니다. |
| KB 해외지점 연계 외화대출 | TOO_BROAD | - | RM_ONLY | 글로벌 금융 솔루션 범주의 표현이며 자동추천 가능한 표준 상품 조건이 아닙니다. |
| KB 에스크로 외화계좌 | NOT_VERIFIED | - | EXCLUDE | KB의 에스크로 기능은 확인되지만 기업 외화 에스크로계좌라는 공개 표준 상품을 확인하지 못했습니다. |
| KB ONE TRADE | RETIRED | - | EXCLUDE | 2022년 서비스 종료 안내가 확인됩니다. 현재 추천 플랫폼으로 사용하면 안 됩니다. |
| 기업전용송금(인터넷 증빙 연동) | SERVICE_SCOPE_NEEDS_DEFINITION | 기업뱅킹 해외기업전용송금/전자무역(EDI) | SUPPLEMENTARY_ONLY | 기업 송금과 전자무역 채널은 존재하지만 하나의 금융상품처럼 추천하기보다 실행 채널로 분류해야 합니다. |

## 4. 상담·운영 지식문서

| 문서 ID | 제목 | 활용 목적 | 출처 |
|---|---|---|---|
| GUIDE-KB-OTC-001 | KB 장외파생상품 거래 8단계 절차 | 투자자 구분부터 사후관리까지 장외파생상품 거래를 8단계로 통제하는 절차입니다. | SRC-017 |
| GUIDE-KB-EVIDENCE-001 | KB 선물환 실수요 증빙서류 | 일반투자자의 장외파생상품은 위험회피 목적의 실수요 범위에서 거래하므로 거래목적별 증빙이 필요합니다. | SRC-017 |
| GUIDE-KB-FORWARD-OPS-001 | KB 인터넷 선물환 체결·결제·취소 규칙 | 인터넷 선물환의 거래한도, 시가평가, 반대거래, 만기결제, 조기결제와 취소 제한을 정리합니다. | SRC-018 |
| GUIDE-KB-RISK-001 | 기업 환위험 유형과 내부 관리기법 | 영업환위험·거래환위험·환산환위험을 구분하고 매칭·네팅·리딩/래깅·ALM을 내부 관리기법으로 설명합니다. | SRC-017 |
| GUIDE-KSURE-001 | K-SURE 환변동보험 이용요건·절차·서류 | 중소·중견기업의 이용요건과 인수한도, 청약, 증권 발급, 정산 및 신청서류를 정리합니다. | SRC-022 / SRC-023 / SRC-024 |
| GUIDE-COMPARE-001 | KB 선물환과 K-SURE 환변동보험 비교 | 은행 선물환, K-SURE 일반형, K-SURE 옵션형의 핵심 차이를 비교합니다. | SRC-017 / SRC-018 / SRC-020 / SRC-021 |

## 5. K-SURE 환변동보험 추천 기준

### 일반형
- 중소·중견기업이며 실헤지 수요가 확인되고, 증거금·담보 부담을 줄이면서 원화 현금흐름을 확정하려는 경우 후보로 제시합니다.
- 수출 기준 환율 하락 시 보험금, 환율 상승 시 이익금 납부 구조를 함께 안내합니다.
- 수입은 지원대상 품목과 기업 요건을 확인합니다.

### 옵션형
- 환율 상승 이익을 유지하고 환율 하락을 방어하려는 수출기업에 우선 검토합니다.
- 최장 6개월, 통화별 최소청약금액, 부분·완전보장과 조기결제 가능 여부를 확인합니다.
- 일반형보다 높은 보험료와 부분보장 구간 제한을 함께 안내합니다.

## 6. 공식 출처 레지스트리

| Source ID | 문서 | 유형 | 확인 범위 | URL |
|---|---|---|---|---|
| SRC-001 | KB Star FX 서비스 안내 | OFFICIAL_WEB | 지원상품·대상·플랫폼 특징 | https://fx.kbstar.com/quics?page=C110657 |
| SRC-002 | KB Star FX 이용약관 | OFFICIAL_PDF | 현물환·선물환·MAR·외환스왑 정의 | https://img2.kbstar.com/obj/ocommon/230317_kbstarfx_terms_n.pdf |
| SRC-003 | KB Star FX 사용자 매뉴얼 | OFFICIAL_PDF | 주문방식·상품 화면·장외파생상품 한도와 서류점검 | https://img2.kbstar.com/obj/ocommon/240708_kbstarfx_user_manual.pdf |
| SRC-004 | 인터넷 선(현)물환 거래안내 | OFFICIAL_WEB | 선물환 정의 | https://obiz.kbstar.com/quics?page=C101981 |
| SRC-005 | KB환율픽 서비스이용안내 | OFFICIAL_WEB | 목표환율 예약주문·자동체결 | https://obiz.kbstar.com/quics?page=C101935 |
| SRC-006 | 마이딜링룸Pro 서비스안내 | OFFICIAL_WEB | PC 외환거래 플랫폼 특징 | https://obiz.kbstar.com/quics?page=C101682 |
| SRC-007 | 기업 외화예금상품 HOME | OFFICIAL_WEB | 현재 판매·추천 외화예금 목록 | https://obiz.kbstar.com/quics?page=C101930 |
| SRC-008 | KB수출입기업우대 외화통장 상품안내 | OFFICIAL_WEB | 대상·통화·우대 조건 | https://obiz.kbstar.com/quics?QSL=&cc=b102196%3Ab103478&page=C101932&%EB%B8%8C%EB%9E%9C%EB%93%9C%EC%83%81%ED%92%88%EB%AA%85=KB%EC%88%98%EC%B6%9C%EC%9E%85%EA%B8%B0%EC%97%85%EC%9A%B0%EB%8C%80%EC%99%B8%ED%99%94%ED%86%B5%EC%9E%A5&%EB%B8%8C%EB%9E%9C%EB%93%9C%EC%83%81%ED%92%88%EC%BD%94%EB%93%9C=FD01000948 |
| SRC-009 | KB WISE 외화정기예금 상품안내 | OFFICIAL_WEB | 통화·금액·기간·회전주기·추가입금 | https://obiz.kbstar.com/quics?QSL=&cc=b102196%3Ab103478&page=C101932&%EB%B8%8C%EB%9E%9C%EB%93%9C%EC%83%81%ED%92%88%EB%AA%85=KB+WISE+%EC%99%B8%ED%99%94%EC%A0%95%EA%B8%B0%EC%98%88%EA%B8%88&%EB%B8%8C%EB%9E%9C%EB%93%9C%EC%83%81%ED%92%88%EC%BD%94%EB%93%9C=FD01000955 |
| SRC-010 | KB 기업뱅킹 수출입 서비스 메뉴 | OFFICIAL_WEB | 수입L/C·L/G·수출환어음·Payment Usance·글로벌구매론·내국신용장·무역금융·EDI 서비스 존재 | https://obiz.kbstar.com/quics?page=C105749 |
| SRC-011 | KB국민은행 특별출연 수출입 금융지원 안내 | OFFICIAL_WEB | 2025~2030 수출패키지 우대금융·K-SURE·Payment Usance·수출환어음·무역금융 | https://obiz.kbstar.com/quics?page=C101674 |
| SRC-012 | KB 기업대출 기타대출상품 목록 | OFFICIAL_WEB | KB 수출기업 우대대출 현재 상품 확인 | https://obiz.kbstar.com/quics?page=C016287 |
| SRC-013 | KB Payment Usance 서비스 소개 | OFFICIAL_WEB | 상품 구조·만기·한도 활용 | https://obiz.kbstar.com/quics?page=C102065 |
| SRC-014 | 해외거래처 신용조사 | OFFICIAL_WEB | 제공 정보와 상담 안내 | https://obiz.kbstar.com/quics?page=C101670 |
| SRC-015 | KB OneTrade 서비스 종료 사전 안내 | OFFICIAL_WEB | KB OneTrade 종료 확인 | https://obiz.kbstar.com/quics?articleId=118079&bbsMode=view&boardId=768&page=C025030 |
| SRC-016 | 외화예금 보호금융상품 등록부 | OFFICIAL_WEB | KB외화MMDA 명칭 존재·기업 추천 적합성은 별도 확인 | https://obiz.kbstar.com/quics?page=C023865 |
| SRC-017 | KB FX/파생상품 거래안내 및 환위험 관리 안내 | USER_UPLOADED_OFFICIAL_PDF | 선물환·통화옵션·합성선물환, 장외파생상품 8단계 절차, 실수요 증빙, 환위험 관리기법 | sources/kb_fx_derivatives_and_risk_management.pdf |
| SRC-018 | KB 인터넷 선(현)물환 거래 이용약관 | USER_UPLOADED_OFFICIAL_PDF | 선·현물환 정의, 이용절차, 거래한도, 시가평가, 반대거래, 결제, 조기결제와 취소 제한 | sources/kb_internet_spot_forward_terms.pdf |
| SRC-019 | K-SURE 환변동보험 제도개요 | OFFICIAL_WEB | 제도 목적, 수출입 환위험, 차액정산, 일반 특징 | https://www.ksure.or.kr/rh-fx/cntnts/i-512/dir.do |
| SRC-020 | K-SURE 환변동보험(선물환) 안내 | OFFICIAL_WEB | 일반형 구조, 헤지기간, 비용, 조기결제, 수출·수입 손익구조 | https://www.ksure.or.kr/rh-fx/cntnts/i-517/web.do |
| SRC-021 | K-SURE 환변동보험(옵션형) 안내 | OFFICIAL_WEB | 부분·완전보장 옵션형, 대상통화, 최소금액, 기간, 조기결제 제한 | https://www.ksure.or.kr/rh-kr/cntnts/i-264/web.do |
| SRC-022 | K-SURE 환변동보험 이용요건 | OFFICIAL_WEB | 중소·중견기업 요건, 대상통화, 제한기업, 수입 추가요건 | https://www.ksure.or.kr/rh-fx/cntnts/i-514/web.do |
| SRC-023 | K-SURE 환변동보험 이용절차 | OFFICIAL_WEB | 한도책정, 13시 청약, 증권발급, 결제통지, 보험금·이익금 정산 | https://www.ksure.or.kr/rh-fx/cntnts/i-516/web.do |
| SRC-024 | K-SURE 환변동보험 신청서류 | OFFICIAL_WEB | 인수한도 신청서, 헤지수요조사표, 약정서, 거래내역 확인서, 동의서 | https://www.ksure.or.kr/rh-kr/cntnts/i-254/web.do |
| SRC-025 | K-SURE 환변동보험 보험료 | OFFICIAL_WEB | 일반형 할인, 옵션형 기본요율·옵션프리미엄, 기간별 기본요율 | https://www.ksure.or.kr/rh-fx/cntnts/i-515/web.do |
