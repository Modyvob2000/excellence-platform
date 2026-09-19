"""
Review API — "الأسئلة قيد المراجعة" (Review Center). عمليات الاعتماد/الرفض/
Bulk موجودة فعليًا في routers/questions.py (تستخدم نفس review_workflow.py
المُختبر) تفاديًا لازدواج المنطق؛ هذا الملف يوفّر فقط استعلامات القائمة
والتفاصيل التي تحتاجها شاشة المراجعة (السؤال + المصدر + التشابه + الحالة).
⚠️ غير مُشغَّل عبر HTTP هنا.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ImportedQuestion, Question
from app.security import CurrentUser, require_roles

router = APIRouter(prefix="/review", tags=["review"])


class ReviewItemOut(BaseModel):
    question_id: int
    question: str
    answer: Optional[str]
    status: str
    original_question_type: Optional[str]
    source_type: str
    source_file_name: Optional[str] = None
    page_number: Optional[int] = None
    duplicate_of_question_id: Optional[int] = None
    similarity_score: Optional[float] = None


@router.get("/queue", response_model=List[ReviewItemOut])
def review_queue(status: Optional[str] = None, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(require_roles("REVIEWER", "TEACHER", "ADMIN", "SUPER_ADMIN"))):
    """
    القائمة الافتراضية (بدون status) تُرجع كل ما ينتظر قرارًا بشريًا:
    NEEDS_REVIEW + NEEDS_CLASSIFICATION + DUPLICATE — لا شيء APPROVED يظهر هنا أبدًا كـ'قيد المراجعة'.
    """
    statuses = [status] if status else ["NEEDS_REVIEW", "NEEDS_CLASSIFICATION", "DUPLICATE"]
    rows = (db.query(Question)
            .filter(Question.status.in_(statuses), Question.is_deleted.is_(False))
            .order_by(Question.created_at).all())

    imported_meta = {
        iq.question_id: iq for iq in
        db.query(ImportedQuestion).filter(ImportedQuestion.question_id.in_([r.id for r in rows])).all()
    } if rows else {}

    results = []
    for r in rows:
        meta = imported_meta.get(r.id)
        results.append(ReviewItemOut(
            question_id=r.id, question=r.question, answer=r.answer, status=r.status,
            original_question_type=r.original_question_type, source_type=r.source_type,
            source_file_name=r.source_file_name, page_number=r.source_page_number,
            duplicate_of_question_id=meta.duplicate_of_question_id if meta else None,
            similarity_score=float(meta.similarity_score) if meta and meta.similarity_score else None,
        ))
    return results
