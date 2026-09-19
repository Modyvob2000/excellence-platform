"""
Smart Search API — نقطة بحث موحّدة عبر الدروس والأسئلة معًا (وليس الأسئلة فقط
كما في /questions/search/). يستخدم نفس app/services/search.py المُختبر (6/6).
⚠️ غير مُشغَّل عبر HTTP هنا.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Lesson, Question
from app.security import CurrentUser, get_current_user
from app.services.search import rank_by_relevance

router = APIRouter(prefix="/search", tags=["search"])


class SearchResultOut(BaseModel):
    entity_type: str  # "question" | "lesson"
    entity_id: int
    text: str
    score: float


@router.get("", response_model=List[SearchResultOut])
def search(q: str, entity_type: Optional[str] = None, limit: int = 20,
           db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    results: List[SearchResultOut] = []

    if entity_type in (None, "question"):
        questions = db.query(Question.id, Question.question).filter(Question.is_deleted.is_(False)).all()
        for qid, score in rank_by_relevance(q, [(r.id, r.question) for r in questions], limit=limit):
            row = next(r for r in questions if r.id == qid)
            results.append(SearchResultOut(entity_type="question", entity_id=qid, text=row.question, score=score))

    if entity_type in (None, "lesson"):
        lessons = db.query(Lesson.id, Lesson.name).filter(Lesson.is_deleted.is_(False)).all()
        for lid, score in rank_by_relevance(q, [(r.id, r.name) for r in lessons], limit=limit):
            row = next(r for r in lessons if r.id == lid)
            results.append(SearchResultOut(entity_type="lesson", entity_id=lid, text=row.name, score=score))

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]
