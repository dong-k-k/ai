"""review_queue.json 적용: 상품 후보 생성 전에 검증 상태를 먼저 확인한다.
requestedProductNames 자유 입력을 review_queue 판정으로 매핑해
verificationNotices를 만들고, 어떤 새 상품 조건도 지어내지 않는다.

매칭은 정규화 후 **전체 문자열 일치**만 허용한다(부분 문자열 포함 매칭은
쓰지 않는다) — 예를 들어 다른 상품명의 일부만 겹치는 경우 잘못 매칭되지
않도록 하기 위해서다. "KB MARS"처럼 review_queue의 공식 input_name이 더
긴 설명을 포함하는 경우(`"KB MARS (Market Average Rate System)"`)는
review_queue.json의 `aliases`에 짧은 형태를 명시적으로 등록해 대응한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.models import VerificationNotice
from app.store import products, review_queue

# review_queue.recommendation_action 값 중 "정상 상품으로 취급하지 않는다"는
# 뜻 — 이 값들은 카드 후보를 절대 만들지 않는다.
_BLOCKING_ACTIONS = {
    "EXCLUDE",
    "EXCLUDE_UNTIL_RM_DOC",
    "DO_NOT_AUTO_RECOMMEND",
    "DO_NOT_AUTO_RECOMMEND_TO_CORPORATE",
    "RM_ONLY",
}

# "상품은 존재하지만 다른 공식 명칭/항목으로 등록돼 있다"는 뜻 — 실제
# product_id로 정정 연결한다.
_RESOLVABLE_ACTIONS = {
    "ACTIVE_AFTER_CORRECTION",
    "ACTIVE_AFTER_RENAME",
    "ADD_AS_RM_REVIEW_REQUIRED",
    "REPLACE_WITH_VERIFIED_PRODUCTS",
    "REPLACE_BY_PAYMENT_STRUCTURE",
    "SUPPLEMENTARY_ONLY",
}


@dataclass
class VerificationOutcome:
    notices: list[VerificationNotice] = field(default_factory=list)
    resolved_product_ids: set[str] = field(default_factory=set)
    blocked_product_ids: set[str] = field(default_factory=set)


def _normalize(s: str) -> str:
    """대소문자 통일 + 공백·일반 구분기호(가운뎃점/하이픈/언더스코어/슬래시/
    쉼표) 정규화. 괄호로 덧붙은 부가 설명은 비교에서 제외한다(짧은 입력이
    review_queue의 긴 공식 input_name과 여전히 같은 대상을 가리킬 수
    있도록)."""
    s = s.strip().lower()
    s = re.sub(r"\([^)]*\)", " ", s)  # 괄호 부가설명 제거
    s = re.sub(r"[·\-_/,]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _names_equal(a: str, b: str) -> bool:
    na, nb = _normalize(a), _normalize(b)
    return bool(na) and na == nb


def _find_review_entry(name: str) -> dict[str, Any] | None:
    for entry in review_queue():
        candidates = [entry["input_name"], *entry.get("aliases", [])]
        if entry.get("canonical_name"):
            candidates.append(entry["canonical_name"])
        if any(_names_equal(name, c) for c in candidates):
            return entry
    return None


def _find_product_by_name(name: str) -> dict[str, Any] | None:
    for p in products():
        candidates = [p["official_name"], *p.get("aliases", [])]
        if any(_names_equal(name, c) for c in candidates):
            return p
    return None


def is_product_blocked(product_id: str) -> bool:
    """True if any review_queue row targets this product_id's canonical
    name with a blocking action — i.e. it must never be recommended even if
    it happens to sit in product_master.json."""
    for entry in review_queue():
        if entry["recommendation_action"] not in _BLOCKING_ACTIONS:
            continue
        canonical = entry.get("canonical_name")
        if not canonical:
            continue
        p = _find_product_by_name(canonical)
        if p and p["product_id"] == product_id:
            return True
    return False


def check_requested_names(requested_names: list[str]) -> VerificationOutcome:
    outcome = VerificationOutcome()
    for name in requested_names:
        queue_entry = _find_review_entry(name)
        if queue_entry is not None:
            action = queue_entry["recommendation_action"]
            canonical = queue_entry.get("canonical_name")
            resolved_product = _find_product_by_name(canonical) if canonical else None

            if action in _BLOCKING_ACTIONS:
                message = queue_entry["reason"]
                if resolved_product:
                    outcome.blocked_product_ids.add(resolved_product["product_id"])
            elif action in _RESOLVABLE_ACTIONS and resolved_product:
                outcome.resolved_product_ids.add(resolved_product["product_id"])
                message = (
                    f"공식 명칭은 '{resolved_product['official_name']}'입니다. {queue_entry['reason']}"
                )
            else:
                message = queue_entry["reason"]

            outcome.notices.append(
                VerificationNotice(
                    requested_name=name,
                    status=queue_entry["status"],
                    canonical_name=resolved_product["official_name"] if resolved_product else canonical,
                    message=message,
                    action=action,
                )
            )
            continue

        direct = _find_product_by_name(name)
        if direct is not None:
            outcome.resolved_product_ids.add(direct["product_id"])
            outcome.notices.append(
                VerificationNotice(
                    requested_name=name,
                    status="VERIFIED",
                    canonical_name=direct["official_name"],
                    message="공식 상품 목록에서 확인된 상품입니다.",
                    action="ACTIVE",
                )
            )
            continue

        outcome.notices.append(
            VerificationNotice(
                requested_name=name,
                status="NOT_VERIFIED",
                canonical_name=None,
                message="공식 검증 목록과 검토 이력 어디에서도 확인되지 않은 명칭입니다. 임의로 상품을 생성하지 않습니다.",
                action="EXCLUDE",
            )
        )
    return outcome


def is_candidate_verified(product: dict[str, Any]) -> bool:
    """6-1 검증 상태 필터: only products that are verified, not
    EXCLUDE-mode, not blocked by review_queue, and backed by at least one
    confirmed source_id are allowed as card candidates."""
    if product["recommendation_mode"] == "EXCLUDE":
        return False
    if not product.get("verification_status", "").startswith("VERIFIED"):
        return False
    if not product.get("source_ids"):
        return False
    if is_product_blocked(product["product_id"]):
        return False
    return True
