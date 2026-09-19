"""无图谱课程兜底：选课后自动补建 outline → mindmap，并给认知层一个「图谱状态」探针。

- `graph_status(cfg, lecture_id)`：ready / building / missing。
- `ensure_course_graph(cfg, lecture_id, *, user_id)`：缺文件就起 daemon 线程依次跑 outline、mindmap；
  同一课程同时只跑一个（与 personalized.py 的 SSE 生成共享 `_ACTIVE_MINDMAP_STREAMS` 语义，键用 ("auto", lecture_id)）。
- 生成失败只记事件；下次选课或调用会再试（带 10 分钟冷却，避免模型不可用时循环打）。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Mapping

from core.runlog import log_event

_LOCK = threading.Lock()
_BUILDING: set[str] = set()
_LAST_FAILURE: Dict[str, float] = {}
FAILURE_COOLDOWN_SECONDS = 600.0


def _has_outline(cfg: Mapping[str, Any], lecture_id: str) -> bool:
    from core.booksproc.outline import load_outline

    try:
        return isinstance(load_outline(cfg, lecture_id), dict)
    except Exception:
        return False


def _has_mindmap(cfg: Mapping[str, Any], lecture_id: str) -> bool:
    from core.booksproc.mindmap import load_mindmap

    try:
        return isinstance(load_mindmap(cfg, lecture_id), dict)
    except Exception:
        return False


def is_building(lecture_id: str) -> bool:
    with _LOCK:
        return str(lecture_id or "") in _BUILDING


def graph_status(cfg: Mapping[str, Any], lecture_id: str) -> str:
    lid = str(lecture_id or "").strip()
    if not lid:
        return "missing"
    if _has_outline(cfg, lid) and _has_mindmap(cfg, lid):
        return "ready"
    return "building" if is_building(lid) else "missing"


def reset_state() -> None:
    """测试用。"""
    with _LOCK:
        _BUILDING.clear()
        _LAST_FAILURE.clear()


def ensure_course_graph(cfg: Mapping[str, Any], lecture_id: str, *, user_id: str = "", sync: bool = False) -> str:
    """返回调用后的状态；已 ready 直接返回，缺则安排构建（返回 building）。"""
    lid = str(lecture_id or "").strip()
    if not lid:
        return "missing"
    if _has_outline(cfg, lid) and _has_mindmap(cfg, lid):
        return "ready"
    now = time.time()
    with _LOCK:
        if lid in _BUILDING:
            return "building"
        if now - _LAST_FAILURE.get(lid, 0.0) < FAILURE_COOLDOWN_SECONDS:
            return "missing"
        _BUILDING.add(lid)

    def run() -> None:
        started = time.time()
        try:
            if not _has_outline(cfg, lid):
                from core.booksproc.outline import generate_outline

                generate_outline(cfg, lid, user_id=user_id or "auto")
            if not _has_mindmap(cfg, lid):
                from core.booksproc.mindmap import generate_mindmap

                generate_mindmap(cfg, lid, user_id=user_id or "auto")
            log_event("course_graph_auto_built", "选课后自动补建课程图谱完成", payload={
                "lecture_id": lid, "user_id": user_id, "seconds": round(time.time() - started, 1),
            })
        except Exception as exc:  # noqa: BLE001
            with _LOCK:
                _LAST_FAILURE[lid] = time.time()
            log_event("course_graph_auto_failed", "选课后自动补建课程图谱失败", payload={
                "lecture_id": lid, "user_id": user_id, "error": str(exc)[:400],
            })
        finally:
            with _LOCK:
                _BUILDING.discard(lid)

    if sync:
        run()
        return graph_status(cfg, lid)
    threading.Thread(target=run, name=f"course-graph-{lid[:24]}", daemon=True).start()
    return "building"
