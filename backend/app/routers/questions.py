"""
Questions API — CRUD كامل + فلترة + بحث + مراجعة/اعتماد/رفض + Bulk.
يستدعي فقط app/services/question_service.py و review_workflow.py (المُختبرَين
بالكامل). هذا الملف نفسه (طبقة FastAPI/SQLAlchemy) غير مُشغَّل هنا لعدم توفر
الحزمتين — راجع backend/README.md.

⚠️ ملاحظة إصلاح مهمة (Route Ordering Bug — أُصلحت):
FastAPI/Starlette يطابق المسارات بترتيب التسجيل، ومسار مثل "/{question_id}"
(بدون محدّد نوع صريح في نص المسار، حتى لو كانت دالة بايثون تتوقع int) يُطابق
هيكليًا أي segment نصي — بما فيه الكلمات الحرفية "bulk" أو "search". لذلك
كانت مسارات POST /questions/bulk/approve و /bulk/reject تتصادم مع
POST /questions/{question_id}/approve و {question_id}/reject المُسجَّلين
قبلها، فتُخطَف الطلبات دائمًا إلى مسار السؤال الفردي (ويفشل هناك بخطأ تحقق
422 لأن "bulk" ليست رقمًا) ولا تصل أبدًا لمعالج bulk الصحيح. القاعدة
الصحيحة: كل المسارات الحرفية الثابتة (bulk/*, search/) يجب أن تُسجَّل قبل أي
مسار يحتوي {parameter} بنفس عدد الأجزاء والفعل (HTTP method). طُبِّقت هذه
القاعدة بالكامل أدناه، وأُضيف اختبار بنيوي يمنع تكرارها مستقبلًا
(test_questions_router_route_ordering.py).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Question
from app.security import CurrentUser, get_current_user, require_roles
from app.services import review_workflow as wf
from app.services.question_service import (
    QuestionData, QuestionServiceError, create_question, delete_question, get_question,
    list_questions, restore_question, search_questions, update_question,
)

router = APIRouter(prefix="/questions", tags=["questions"])


# ---------------------------------------------------------------------------
# محول SQLAlchemy <-> QuestionStore Protocol (question_service.py)
# ---------------------------------------------------------------------------

class SqlAlchemyQuestionStore:
    def __init__(self, db: Session):
        self.db = db

    def _to_data(self, row: Question) -> QuestionData:
        return QuestionData(
            id=row.id, question=row.question, answer=row.answer, correction=row.correction,
            choices=[c.choice_text for c in row.choices], lesson_id=row.lesson_id,
            question_type_id=row.question_type_id, original_question_type=row.original_question_type,
            canonical_type=row.original_question_type, status=row.status, approved=row.approved,
            is_hidden=row.is_hidden, is_deleted=row.is_deleted, source_type=row.source_type,
            points=float(row.points), created_by=row.created_by,
        )

    def insert(self, data: QuestionData) -> int:
        row = Question(
            question=data.question, answer=data.answer, lesson_id=data.lesson_id,
            original_question_type=data.original_question_type, status=data.status,
            approved=data.approved, source_type=data.source_type, created_by=data.created_by,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row.id

    def get(self, question_id: int) -> Optional[QuestionData]:
        row = self.db.get(Question, question_id)
        return self._to_data(row) if row else None

    def update(self, question_id: int, patch: dict) -> QuestionData:
        row = self.db.get(Question, question_id)
        if not row:
            raise QuestionServiceError(f"السؤال #{question_id} غير موجود.")
        for key, value in patch.items():
            if key == "canonical_type":
                continue  # مُشتق للعرض فقط، غير مُخزَّن كعمود منفصل حاليًا
            setattr(row, key, value)
        self.db.commit()
        self.db.refresh(row)
        return self._to_data(row)

    def list(self, filters: dict) -> List[QuestionData]:
        q = self.db.query(Question)
        if not filters.get("include_deleted"):
            q = q.filter(Question.is_deleted.is_(False))
        if filters.get("lesson_id"):
            q = q.filter(Question.lesson_id == filters["lesson_id"])
        if filters.get("status"):
            q = q.filter(Question.status == filters["status"])
        return [self._to_data(r) for r in q.all()]

    def all_texts(self):
        rows = self.db.query(Question.id, Question.question).filter(Question.is_deleted.is_(False)).all()
        return [(r.id, r.question) for r in rows]


def get_store(db: Session = Depends(get_db)) -> SqlAlchemyQuestionStore:
    return SqlAlchemyQuestionStore(db)


# ---------------------------------------------------------------------------
# محول Review Repository (يُستخدم في bulk وفي المسارات الفردية أدناه)
# ---------------------------------------------------------------------------

class SqlAlchemyReviewRepository:
    """محول رفيع يجعل صف Question متوافقًا مع QuestionRepository Protocol في review_workflow.py."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, question_id: int) -> wf.QuestionRecord:
        row = self.db.get(Question, question_id)
        if not row:
            raise wf.WorkflowError(f"السؤال #{question_id} غير موجود.")
        return wf.QuestionRecord(id=row.id, status=row.status, lesson_id=row.lesson_id,
                                  question_type_id=row.question_type_id, approved=row.approved,
                                  is_deleted=row.is_deleted)

    def save(self, record: wf.QuestionRecord) -> None:
        row = self.db.get(Question, record.id)
        row.status = record.status
        row.lesson_id = record.lesson_id
        row.question_type_id = record.question_type_id
        row.approved = record.approved
        row.is_deleted = record.is_deleted
        self.db.commit()

    def log_action(self, action: wf.ReviewActionRecord) -> None:
        from app.models import ReviewAction
        self.db.add(ReviewAction(
            question_id=action.question_id, reviewer_id=action.reviewer_id, action=action.action,
            before_json={"status": action.from_status}, after_json={"status": action.to_status,
                                                                      **action.details}))
        self.db.commit()


def get_review_repo(db: Session = Depends(get_db)) -> SqlAlchemyReviewRepository:
    return SqlAlchemyReviewRepository(db)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class QuestionCreateIn(BaseModel):
    question: str
    lesson_id: int
    answer: Optional[str] = None
    choices: List[str] = []
    original_question_type: Optional[str] = None


class QuestionUpdateIn(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    correction: Optional[str] = None
    lesson_id: Optional[int] = None


class QuestionOut(BaseModel):
    id: int
    question: str
    answer: Optional[str]
    status: str
    approved: bool
    canonical_type: Optional[str]
    lesson_id: Optional[int]
    choices: List[str] = []

    @classmethod
    def from_data(cls, d: QuestionData) -> "QuestionOut":
        return cls(id=d.id, question=d.question, answer=d.answer, status=d.status,
                    approved=d.approved, canonical_type=d.canonical_type, lesson_id=d.lesson_id,
                    choices=d.choices or [])


class BulkActionIn(BaseModel):
    question_ids: List[int]
    reason: Optional[str] = None
    new_type_id: Optional[int] = None
    new_lesson_id: Optional[int] = None


# ---------------------------------------------------------------------------
# CRUD — مسارات ثابتة أولًا (create/list/search)، قبل أي مسار بمُعامل
# ---------------------------------------------------------------------------

@router.post("", response_model=QuestionOut)
def create(payload: QuestionCreateIn, store: SqlAlchemyQuestionStore = Depends(get_store),
           user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    try:
        record, duplicates = create_question(
            store, payload.question, payload.lesson_id, answer=payload.answer,
            choices=payload.choices, original_question_type=payload.original_question_type,
            source_type="MANUAL", created_by=user.id)
    except QuestionServiceError as e:
        raise HTTPException(400, str(e)) from e
    out = QuestionOut.from_data(record)
    if duplicates:
        out.status = record.status  # يبقى DUPLICATE ظاهرًا للمستخدم صراحة، لا إخفاء
    return out


@router.get("", response_model=List[QuestionOut])
def list_all(lesson_id: Optional[int] = None, status: Optional[str] = None,
             canonical_type: Optional[str] = None,
             store: SqlAlchemyQuestionStore = Depends(get_store),
             user: CurrentUser = Depends(get_current_user)):
    records = list_questions(store, lesson_id=lesson_id, status=status, canonical_type=canonical_type)
    return [QuestionOut.from_data(r) for r in records]


@router.get("/search/", response_model=List[QuestionOut])
def search(q: str, store: SqlAlchemyQuestionStore = Depends(get_store),
           user: CurrentUser = Depends(get_current_user)):
    results = search_questions(store, q)
    return [QuestionOut.from_data(r) for r, _score in results]


# ---------------------------------------------------------------------------
# Bulk Review — مسارات حرفية ثابتة (/bulk/...)؛ يجب أن تبقى مُسجَّلة هنا،
# قبل أي مسار /{question_id}/... بنفس الفعل (POST) وعدد الأجزاء، وإلا
# ستُخطَف طلباتها إلى مسار السؤال الفردي (راجع شرح الإصلاح أعلى الملف).
# ---------------------------------------------------------------------------

@router.post("/bulk/approve")
def bulk_approve(payload: BulkActionIn, repo: SqlAlchemyReviewRepository = Depends(get_review_repo),
                  user: CurrentUser = Depends(require_roles("REVIEWER", "TEACHER", "ADMIN", "SUPER_ADMIN"))):
    result = wf.bulk_apply(repo, payload.question_ids, user.id, user.role, operation="approve")
    return {"succeeded": result.succeeded, "failed": result.failed}


@router.post("/bulk/reject")
def bulk_reject(payload: BulkActionIn, repo: SqlAlchemyReviewRepository = Depends(get_review_repo),
                 user: CurrentUser = Depends(require_roles("REVIEWER", "TEACHER", "ADMIN", "SUPER_ADMIN"))):
    result = wf.bulk_apply(repo, payload.question_ids, user.id, user.role, operation="reject",
                            reason=payload.reason or "")
    return {"succeeded": result.succeeded, "failed": result.failed}


@router.post("/bulk/delete")
def bulk_delete(payload: BulkActionIn, repo: SqlAlchemyReviewRepository = Depends(get_review_repo),
                 user: CurrentUser = Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    result = wf.bulk_apply(repo, payload.question_ids, user.id, user.role, operation="delete")
    return {"succeeded": result.succeeded, "failed": result.failed}


@router.post("/bulk/change_type")
def bulk_change_type(payload: BulkActionIn, repo: SqlAlchemyReviewRepository = Depends(get_review_repo),
                      user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    result = wf.bulk_apply(repo, payload.question_ids, user.id, user.role, operation="change_type",
                            new_type_id=payload.new_type_id)
    return {"succeeded": result.succeeded, "failed": result.failed}


@router.post("/bulk/change_lesson")
def bulk_change_lesson(payload: BulkActionIn, repo: SqlAlchemyReviewRepository = Depends(get_review_repo),
                        user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    result = wf.bulk_apply(repo, payload.question_ids, user.id, user.role, operation="change_lesson",
                            new_lesson_id=payload.new_lesson_id)
    return {"succeeded": result.succeeded, "failed": result.failed}


# ---------------------------------------------------------------------------
# مسارات السؤال الفردي بمُعامل — تُسجَّل أخيرًا عمدًا (بعد كل المسارات الحرفية)
# ---------------------------------------------------------------------------

@router.get("/{question_id}", response_model=QuestionOut)
def get_one(question_id: int, store: SqlAlchemyQuestionStore = Depends(get_store),
            user: CurrentUser = Depends(get_current_user)):
    try:
        return QuestionOut.from_data(get_question(store, question_id))
    except QuestionServiceError as e:
        raise HTTPException(404, str(e)) from e


@router.patch("/{question_id}", response_model=QuestionOut)
def update(question_id: int, payload: QuestionUpdateIn,
           store: SqlAlchemyQuestionStore = Depends(get_store),
           user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        return QuestionOut.from_data(update_question(store, question_id, patch))
    except QuestionServiceError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/{question_id}")
def delete(question_id: int, store: SqlAlchemyQuestionStore = Depends(get_store),
           user: CurrentUser = Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    """Soft delete فقط — أبدًا حذف حقيقي من قاعدة البيانات."""
    delete_question(store, question_id)
    return {"status": "soft_deleted"}


@router.post("/{question_id}/restore")
def restore(question_id: int, store: SqlAlchemyQuestionStore = Depends(get_store),
            user: CurrentUser = Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    restore_question(store, question_id)
    return {"status": "restored"}


@router.post("/{question_id}/approve")
def approve(question_id: int, repo: SqlAlchemyReviewRepository = Depends(get_review_repo),
            user: CurrentUser = Depends(require_roles("REVIEWER", "TEACHER", "ADMIN", "SUPER_ADMIN"))):
    try:
        rec = wf.approve(repo, question_id, user.id, user.role)
    except wf.WorkflowError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": rec.status}


@router.post("/{question_id}/reject")
def reject(question_id: int, reason: str = "",
           repo: SqlAlchemyReviewRepository = Depends(get_review_repo),
           user: CurrentUser = Depends(require_roles("REVIEWER", "TEACHER", "ADMIN", "SUPER_ADMIN"))):
    try:
        rec = wf.reject(repo, question_id, user.id, user.role, reason=reason)
    except wf.WorkflowError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": rec.status}
