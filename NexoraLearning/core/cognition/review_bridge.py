"""答题结算 → 认知证据（今日复习 / 闭环 flow 两条路径共用）。

语义（2026-09-19 用户确认）：「看答案」不是上报点，上报的是答对 / 答错；
未作答直接看答案按错误算，但用更低权重的 `revealed_answer` 证据类型，
让掌握度既反映「没会」也不把一次偷看当成一次正式失分。

幂等：同一 (user, quiz_id, question_id) 只产生一条证据；重复结算不改写第一次的结果。
概念绑定：题目自带 related_concept_id → 题库记录的 concept_id → 概念名出现在题干（先限本章，再放宽到本书）。
匹配不到就跳过并留事件日志，不捏造概念。
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

from core import user as user_store
from core.runlog import log_event

from .attribution import _load_catalog, _match_concepts
from .errors import CognitionConflictError, CognitionError

_OBJECTIVE_TYPES = {"choice", "single_choice", "multiple_choice", "选择题", "单选题", "多选题"}


def review_evidence_id(user_id: str, quiz_id: str, question_id: str) -> str:
    raw = f"{str(user_id or '').strip()}|{str(quiz_id or '').strip()}|{str(question_id or '').strip()}"
    return "ev_rv_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def completion_id_for(quiz_id: str, question_id: str) -> str:
    raw = f"{str(quiz_id or '').strip()}|{str(question_id or '').strip()}"
    return "qc_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _evidence_type(question: Mapping[str, Any], *, revealed_without_answer: bool) -> str:
    if revealed_without_answer:
        return "revealed_answer"
    question_type = str(question.get("type") or question.get("question_type") or "").strip().lower()
    options = question.get("options") or question.get("question_options") or []
    if question_type in _OBJECTIVE_TYPES or (isinstance(options, list) and len(options) >= 2):
        return "objective_question"
    return "constructed_response"


def _bank_concept_ids(cfg: Mapping[str, Any], username: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    try:
        rows = user_store.list_question_bank_items(dict(cfg), username) or []
    except Exception:
        return mapping
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        question_id = str(row.get("question_id") or "").strip()
        concept_id = str(row.get("concept_id") or "").strip()
        if not concept_id:
            nested = row.get("question") if isinstance(row.get("question"), Mapping) else {}
            concept_id = str(nested.get("related_concept_id") or "").strip()
        if question_id and concept_id:
            mapping[question_id] = concept_id
    return mapping


def resolve_concept(
    cfg: Mapping[str, Any],
    username: str,
    question: Mapping[str, Any],
    *,
    question_id: str,
    lecture_id: str,
    book_id: str,
    chapter_index: int,
    concepts: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """返回 (概念, 绑定方式)。概念为 None 表示无法绑定。"""
    if concepts is None:
        try:
            _, concepts = _load_catalog(cfg, username)
        except Exception:
            concepts = []
    by_id = {str(row.get("concept_id") or ""): row for row in concepts if isinstance(row, Mapping)}
    scoped = [row for row in concepts if not lecture_id or str(row.get("lecture_id") or "") == lecture_id]

    bound = str(question.get("related_concept_id") or question.get("concept_id") or "").strip()
    if bound and bound in by_id:
        return by_id[bound], "question"
    bank = _bank_concept_ids(cfg, username).get(question_id, "")
    if bank and bank in by_id:
        return by_id[bank], "question_bank"

    title = " ".join(str(question.get(key) or "") for key in ("title", "content"))
    matched = _match_concepts(title, scoped, chapter_index, book_id) if title.strip() else []
    if matched:
        return matched[0], "title_chapter"
    matched = _match_concepts(title, scoped, -1, book_id) if title.strip() else []
    if matched:
        return matched[0], "title_book"
    return None, ""


def record_review_evidence(
    cfg: Mapping[str, Any],
    username: str,
    *,
    quiz_id: str,
    question: Mapping[str, Any],
    question_id: str,
    lecture_id: str,
    book_id: str,
    chapter_index: int,
    chapter_name: str,
    is_correct: bool,
    revealed_without_answer: bool = False,
    occurred_at: Optional[int] = None,
    concepts: Optional[List[Dict[str, Any]]] = None,
    source_kind: str = "review",
) -> Dict[str, Any]:
    """一题一证据。写不进认知层不影响判分（返回 recorded=False + reason）。"""
    from .service import CognitionService

    timestamp = int(occurred_at or time.time())
    concept, binding = resolve_concept(
        cfg, username, question,
        question_id=question_id, lecture_id=lecture_id, book_id=book_id,
        chapter_index=chapter_index, concepts=concepts,
    )
    base = {"quiz_id": quiz_id, "question_id": question_id, "user_id": username}
    if concept is None:
        log_event("review_evidence_skipped", "答题无法绑定概念，未写入认知证据",
                  payload={**base, "reason": "concept_unbound", "lecture_id": lecture_id})
        return {"recorded": False, "reason": "concept_unbound"}

    evidence_type = _evidence_type(question, revealed_without_answer=revealed_without_answer)
    payload = {
        "evidence_id": review_evidence_id(username, quiz_id, question_id),
        "lecture_id": str(concept.get("lecture_id") or lecture_id),
        "book_id": str(concept.get("book_id") or book_id),
        "concept_id": str(concept.get("concept_id") or ""),
        "evidence_type": evidence_type,
        "source_type": "review",
        "source_id": f"{quiz_id}:{question_id}"[:200],
        "occurred_at": timestamp,
        "score": 1.0 if is_correct else 0.0,
        "confidence": 0.6 if revealed_without_answer else 1.0,
        "metadata": {
            "question_id": question_id,
            "chapter_name": str(chapter_name or "")[:160],
            "is_correct": bool(is_correct),
            "revealed_without_answer": bool(revealed_without_answer),
            "binding": binding,
            "source_kind": source_kind,
        },
    }
    try:
        result = CognitionService(cfg).record_evidence(username, payload)
    except CognitionConflictError:
        # 同一题第二次结算：第一次的结果作数，不改写。
        return {"recorded": True, "created": False, "reason": "already_recorded", "concept_id": payload["concept_id"]}
    except CognitionError as exc:
        log_event("review_evidence_failed", "答题已判分，但认知证据写入失败",
                  payload={**base, "concept_id": payload["concept_id"], "error": str(exc)})
        return {"recorded": False, "reason": "cognition_write_failed", "message": str(exc)}
    return {
        "recorded": True,
        "created": bool(result.get("created")),
        "concept_id": payload["concept_id"],
        "evidence_type": evidence_type,
        "binding": binding,
    }
