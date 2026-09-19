"""
Exam Engine — تصحيح المحاولات وحساب النتائج. منطق خالص، بدون قاعدة بيانات.

قواعد التصحيح:
- MCQ / TRUE_FALSE: تطابق حرفي بعد التطبيع (dedup.normalize_text) لأن الإجابة
  محددة (اختيار واحد صحيح).
- باقي الأنواع (TERM, WHO_IS, WHY, ...): تُصحَّح تلقائيًا فقط عند تطابق نصي
  قوي (similarity >= AUTO_GRADE_THRESHOLD)، وإلا تُوسَم needs_manual_grading
  ولا تُحتسب صح/خطأ تلقائيًا — لا نخمّن تصحيح إجابة مقالية.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.services.dedup import LocalTextSimilarityBackend, normalize_text

AUTO_GRADE_THRESHOLD = 0.85
AUTO_GRADABLE_TYPES = {"MCQ", "TRUE_FALSE", "COMPLETE", "TERM", "WHO_IS", "WHY", "WHAT_HAPPENS", "RELATION"}


@dataclass
class ExamQuestionSpec:
    question_id: int
    correct_answer: str
    canonical_type: str
    marks: float = 1.0


@dataclass
class StudentAnswer:
    question_id: int
    answer_text: str


@dataclass
class AnswerGrade:
    question_id: int
    is_correct: Optional[bool]  # None = يحتاج تصحيح يدوي (لم يُحسم تلقائيًا)
    marks_awarded: float
    needs_manual_grading: bool = False


@dataclass
class ExamResult:
    score: float
    total_marks: float
    percentage: float
    correct_count: int
    wrong_count: int
    needs_manual_grading_count: int
    grades: List[AnswerGrade] = field(default_factory=list)
    graded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def grade_answer(spec: ExamQuestionSpec, student_answer: Optional[str],
                  backend=None) -> AnswerGrade:
    backend = backend or LocalTextSimilarityBackend()
    if not student_answer or not student_answer.strip():
        return AnswerGrade(spec.question_id, is_correct=False, marks_awarded=0.0)

    if spec.canonical_type in ("MCQ", "TRUE_FALSE"):
        is_correct = normalize_text(student_answer) == normalize_text(spec.correct_answer)
        return AnswerGrade(spec.question_id, is_correct, spec.marks if is_correct else 0.0)

    if spec.canonical_type in AUTO_GRADABLE_TYPES:
        score = backend.similarity(student_answer, spec.correct_answer)
        if score >= AUTO_GRADE_THRESHOLD:
            return AnswerGrade(spec.question_id, True, spec.marks)
        if score <= 0.2:
            return AnswerGrade(spec.question_id, False, 0.0)
        # منطقة رمادية: لا نجزم آليًا — تحتاج مراجعة معلم
        return AnswerGrade(spec.question_id, None, 0.0, needs_manual_grading=True)

    # ESSAY / SHORT_ANSWER / أنواع مقالية بطبيعتها: تصحيح يدوي دائمًا
    return AnswerGrade(spec.question_id, None, 0.0, needs_manual_grading=True)


def submit_attempt(exam_questions: List[ExamQuestionSpec],
                    student_answers: List[StudentAnswer]) -> ExamResult:
    answers_by_qid: Dict[int, str] = {a.question_id: a.answer_text for a in student_answers}
    grades = [grade_answer(spec, answers_by_qid.get(spec.question_id)) for spec in exam_questions]

    total_marks = sum(spec.marks for spec in exam_questions)
    score = sum(g.marks_awarded for g in grades)
    correct = sum(1 for g in grades if g.is_correct is True)
    wrong = sum(1 for g in grades if g.is_correct is False)
    pending = sum(1 for g in grades if g.needs_manual_grading)

    percentage = round((score / total_marks) * 100, 2) if total_marks > 0 else 0.0
    return ExamResult(
        score=score, total_marks=total_marks, percentage=percentage,
        correct_count=correct, wrong_count=wrong, needs_manual_grading_count=pending, grades=grades,
    )
