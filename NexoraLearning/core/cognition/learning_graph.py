"""Read-only learner overlays on the shared textbook graph and chapter index."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping

from core.cognition.errors import CognitionCatalogError
from core.cognition.service import CognitionService
from core.knowledge_graph import load_cached_graph
from core.lectures import get_book
from core.user.learning_progress import compute_user_lecture_progress


def build_learning_graph(cfg: Mapping[str, Any], username: str, lecture_id: str, book_id: str) -> Dict[str, Any]:
    """Never store a student's reading or mastery in the shared graph cache."""
    book = get_book(cfg, lecture_id, book_id)
    if book is None:
        raise ValueError("book not found in this lecture")
    cached = load_cached_graph(cfg, lecture_id, book_id)
    progress = compute_user_lecture_progress(username, lecture_id, [book], cfg=cfg)
    try:
        overview = CognitionService(cfg).get_overview(username, lecture_id=lecture_id, book_id=book_id)
        states = overview.get("states") or []
    except CognitionCatalogError:
        # A learner can read a textbook before the model-generated concept map.
        states = []
    graph = deepcopy(cached) if cached else {"chapters": [], "relations": []}
    cached_chapters = graph.get("chapters") or []
    chapters = []
    for position in progress["chapters"]:
        candidates = [row for row in cached_chapters if row.get("name") == position["chapter_name"]]
        chapter = deepcopy(candidates[0]) if len(candidates) == 1 else {"name": position["chapter_name"], "summary": "", "concepts": []}
        chapter_states = [state for state in states if state.get("concept", {}).get("book_id") == book_id
                          and state.get("concept", {}).get("chapter_index") == position["chapter_index"]]
        exposed = position["read_chars"] > 0 or position["completed"]
        if chapter_states:
            chapter["concepts"] = [{
                "name": state["concept"]["name"], "detail": state["concept"].get("detail", ""),
                "concept_id": state["concept"]["concept_id"], "mastery": state.get("mastery"),
                "status": "unverified" if exposed and state.get("mastery") is None else state.get("status", "unknown"),
                "assessed_count": state.get("assessed_count", 0),
            } for state in chapter_states]
        else:
            for concept in chapter.get("concepts") or []:
                concept.update(mastery=None, status="unverified" if exposed else "unknown", assessed_count=0)
        chapter.update(chapter_index=position["chapter_index"], reading_percent=position["reading_percent"],
                       completed=position["completed"], reading_seconds=position["reading_seconds"])
        chapters.append(chapter)
    graph["chapters"] = chapters
    graph["reading_progress_percent"] = progress["reading_progress"]
    graph["concepts_available"] = any(chapter.get("concepts") for chapter in chapters)
    return {"graph": graph, "cached": cached is not None}
