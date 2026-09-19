"""Results API — سجل المحاولات وتقارير الامتحانات. ⚠️ غير مُشغَّل عبر HTTP هنا."""
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ExamAttempt
from app.security import CurrentUser, require_roles
from app.services.results_service import AttemptSummary, build_exam_report, student_history

router = APIRouter(prefix="/results", tags=["results"])


class AttemptOut(BaseModel):
    attempt_id: int
    exam_id: int
    score: float
    percentage: float
    correct_count: int
    wrong_count: int


class ExamReportOut(BaseModel):
    exam_id: int
    attempts_count: int
    average_percentage: float
    pass_rate: float
    highest_percentage: float
    lowest_percentage: float


def _load_attempts(db: Session, exam_id: int = None, student_id: int = None) -> List[AttemptSummary]:
    q = db.query(ExamAttempt).filter(ExamAttempt.submitted_at.isnot(None))
    if exam_id:
        q = q.filter(ExamAttempt.exam_id == exam_id)
    if student_id:
        q = q.filter(ExamAttempt.student_user_id == student_id)
    return [
        AttemptSummary(
            attempt_id=r.id, exam_id=r.exam_id, student_id=r.student_user_id,
            score=float(r.score or 0), total_marks=float(r.score or 0),
            percentage=float(r.percentage or 0), correct_count=r.correct_count or 0,
            wrong_count=r.wrong_count or 0, submitted_at=r.submitted_at,
        ) for r in q.all()
    ]


@router.get("/students/{student_id}/history", response_model=List[AttemptOut])
def history(student_id: int, db: Session = Depends(get_db),
            user: CurrentUser = Depends(require_roles("STUDENT", "TEACHER", "ADMIN", "SUPER_ADMIN"))):
    attempts = _load_attempts(db, student_id=student_id)
    ordered = student_history(attempts, student_id)
    return [AttemptOut(attempt_id=a.attempt_id, exam_id=a.exam_id, score=a.score,
                        percentage=a.percentage, correct_count=a.correct_count,
                        wrong_count=a.wrong_count) for a in ordered]


@router.get("/exams/{exam_id}/report", response_model=ExamReportOut)
def exam_report(exam_id: int, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    """تقرير للمعلم/المدير: متوسط الدرجات، نسبة النجاح، أعلى/أقل درجة."""
    attempts = _load_attempts(db, exam_id=exam_id)
    report = build_exam_report(attempts, exam_id)
    return ExamReportOut(exam_id=report.exam_id, attempts_count=report.attempts_count,
                          average_percentage=report.average_percentage, pass_rate=report.pass_rate,
                          highest_percentage=report.highest_percentage,
                          lowest_percentage=report.lowest_percentage)
