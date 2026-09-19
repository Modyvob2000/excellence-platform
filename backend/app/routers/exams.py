"""
Exams API — إنشاء امتحان، بدء/إنهاء محاولة، حساب النتيجة عبر exam_engine.py.
يستدعي فقط app/services/exam_service.py (مُختبر بالكامل، 13/13).
⚠️ هذا الملف (طبقة FastAPI/SQLAlchemy) غير مُشغَّل هنا — راجع backend/README.md.
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Exam, ExamAttempt, ExamQuestion, Question, AttemptAnswer
from app.security import CurrentUser, get_current_user, require_roles
from app.services.exam_service import (
    AttemptData, ExamData, ExamServiceError, create_exam, finish_attempt, get_ordered_questions,
    start_attempt, submit_answer,
)

router = APIRouter(prefix="/exams", tags=["exams"])


# ---------------------------------------------------------------------------
# محولات SQLAlchemy <-> exam_service Protocols
# ---------------------------------------------------------------------------

class SqlAlchemyQuestionLookup:
    def __init__(self, db: Session):
        self.db = db

    def get_for_exam(self, question_id: int) -> dict:
        row = self.db.get(Question, question_id)
        if not row:
            raise KeyError(question_id)
        return {
            "status": row.status, "canonical_type": row.original_question_type or "OTHER",
            "answer": row.answer, "points": float(row.points),
        }


class SqlAlchemyExamStore:
    def __init__(self, db: Session):
        self.db = db

    def save_exam(self, data: ExamData) -> int:
        if data.id is None:
            row = Exam(name=data.name, duration_minutes=data.duration_minutes,
                        shuffle_questions=data.shuffle_questions, shuffle_choices=data.shuffle_choices,
                        allow_retake=data.allow_retake, is_active=data.is_active)
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            for order, qid in enumerate(data.question_ids):
                self.db.add(ExamQuestion(exam_id=row.id, question_id=qid, question_order=order))
            self.db.commit()
            return row.id
        return data.id

    def get_exam(self, exam_id: int) -> ExamData:
        row = self.db.get(Exam, exam_id)
        if not row:
            raise ExamServiceError(f"الامتحان #{exam_id} غير موجود.")
        qids = [eq.question_id for eq in
                self.db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam_id)
                .order_by(ExamQuestion.question_order).all()]
        return ExamData(id=row.id, name=row.name, question_ids=qids,
                         duration_minutes=row.duration_minutes, shuffle_questions=row.shuffle_questions,
                         shuffle_choices=row.shuffle_choices, allow_retake=row.allow_retake,
                         is_active=row.is_active)

    def save_attempt(self, data: AttemptData) -> int:
        if data.id is None:
            row = ExamAttempt(exam_id=data.exam_id, student_user_id=data.student_id)
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            return row.id
        row = self.db.get(ExamAttempt, data.id)
        # نحفظ كل إجابة كسطر في attempt_answers (upsert بسيط) بدل الاعتماد على حالة في الذاكرة
        existing = {a.question_id: a for a in
                    self.db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == row.id).all()}
        for qid, text in data.answers.items():
            if qid in existing:
                existing[qid].student_answer = text
            else:
                self.db.add(AttemptAnswer(attempt_id=row.id, question_id=qid, student_answer=text))
        if data.submitted and data.result is not None:
            from datetime import datetime, timezone
            row.submitted_at = datetime.now(timezone.utc)
            row.score = data.result.score
            row.percentage = data.result.percentage
            row.correct_count = data.result.correct_count
            row.wrong_count = data.result.wrong_count
        self.db.commit()
        return row.id

    def get_attempt(self, attempt_id: int) -> AttemptData:
        row = self.db.get(ExamAttempt, attempt_id)
        if not row:
            raise ExamServiceError(f"المحاولة #{attempt_id} غير موجودة.")
        answers = {a.question_id: a.student_answer for a in
                   self.db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()}
        return AttemptData(id=row.id, exam_id=row.exam_id, student_id=row.student_user_id,
                            answers=answers, submitted=row.submitted_at is not None)

    def count_attempts(self, exam_id: int, student_id: int) -> int:
        return self.db.query(ExamAttempt).filter(
            ExamAttempt.exam_id == exam_id, ExamAttempt.student_user_id == student_id,
            ExamAttempt.submitted_at.isnot(None)).count()


def get_question_lookup(db: Session = Depends(get_db)) -> SqlAlchemyQuestionLookup:
    return SqlAlchemyQuestionLookup(db)


def get_exam_store(db: Session = Depends(get_db)) -> SqlAlchemyExamStore:
    return SqlAlchemyExamStore(db)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ExamCreateIn(BaseModel):
    name: str
    question_ids: List[int]
    duration_minutes: Optional[int] = None
    shuffle_questions: bool = False
    shuffle_choices: bool = False
    allow_retake: bool = False
    is_training: bool = False


class ExamOut(BaseModel):
    id: int
    name: str
    question_ids: List[int]
    duration_minutes: Optional[int]
    is_training: bool


class SubmitAnswerIn(BaseModel):
    question_id: int
    answer_text: str


class ResultOut(BaseModel):
    score: float
    total_marks: float
    percentage: float
    correct_count: int
    wrong_count: int
    needs_manual_grading_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=ExamOut)
def create(payload: ExamCreateIn, store: SqlAlchemyExamStore = Depends(get_exam_store),
           lookup: SqlAlchemyQuestionLookup = Depends(get_question_lookup),
           user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    try:
        exam = create_exam(store, lookup, payload.name, payload.question_ids,
                            duration_minutes=payload.duration_minutes,
                            shuffle_questions=payload.shuffle_questions,
                            shuffle_choices=payload.shuffle_choices,
                            allow_retake=payload.allow_retake, is_training=payload.is_training)
    except ExamServiceError as e:
        raise HTTPException(400, str(e)) from e
    return ExamOut(id=exam.id, name=exam.name, question_ids=exam.question_ids,
                    duration_minutes=exam.duration_minutes, is_training=exam.is_training)


@router.get("/{exam_id}/questions", response_model=List[int])
def get_questions_for_taking(exam_id: int, store: SqlAlchemyExamStore = Depends(get_exam_store),
                              user: CurrentUser = Depends(get_current_user)):
    """يُرجع ترتيب الأسئلة للطالب — عشوائي إن كان الامتحان يفعّل shuffle_questions."""
    exam = store.get_exam(exam_id)
    return get_ordered_questions(exam)


@router.post("/{exam_id}/attempts")
def begin_attempt(exam_id: int, store: SqlAlchemyExamStore = Depends(get_exam_store),
                   user: CurrentUser = Depends(require_roles("STUDENT", "TEACHER", "ADMIN", "SUPER_ADMIN"))):
    try:
        attempt = start_attempt(store, exam_id, student_id=user.id)
    except ExamServiceError as e:
        raise HTTPException(400, str(e)) from e
    return {"attempt_id": attempt.id}


@router.post("/attempts/{attempt_id}/answers")
def answer(attempt_id: int, payload: SubmitAnswerIn, store: SqlAlchemyExamStore = Depends(get_exam_store),
           user: CurrentUser = Depends(get_current_user)):
    try:
        submit_answer(store, attempt_id, payload.question_id, payload.answer_text)
    except ExamServiceError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": "saved"}


@router.post("/attempts/{attempt_id}/finish", response_model=ResultOut)
def finish(attempt_id: int, store: SqlAlchemyExamStore = Depends(get_exam_store),
           lookup: SqlAlchemyQuestionLookup = Depends(get_question_lookup),
           user: CurrentUser = Depends(get_current_user)):
    try:
        result = finish_attempt(store, lookup, attempt_id)
    except ExamServiceError as e:
        raise HTTPException(400, str(e)) from e
    return ResultOut(score=result.score, total_marks=result.total_marks, percentage=result.percentage,
                      correct_count=result.correct_count, wrong_count=result.wrong_count,
                      needs_manual_grading_count=result.needs_manual_grading_count)
