"""
Exam Service — إنشاء الامتحانات، اختيار الأسئلة يدويًا، بدء/إنهاء المحاولات،
باستخدام exam_engine.py (المُختبر) للتصحيح. مفصول عن FastAPI/DB عبر ExamStore
(Protocol) — قابل للاختبار بالكامل بمخزن وهمي في الذاكرة.

قاعدة صارمة: إضافة سؤال لامتحان تتطلب أن يكون status == "APPROVED" — لا يجوز
إطلاقًا إدراج سؤال غير معتمد ضمن امتحان رسمي (وضع "تدريب" استثناء موثّق أدناه).
"""
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol

from app.services.exam_engine import ExamQuestionSpec, StudentAnswer, submit_attempt


class ExamServiceError(Exception):
    pass


@dataclass
class ExamData:
    id: Optional[int]
    name: str
    question_ids: List[int] = field(default_factory=list)
    duration_minutes: Optional[int] = None
    shuffle_questions: bool = False
    shuffle_choices: bool = False
    allow_retake: bool = False
    is_training: bool = False   # وضع التدريب: يسمح بأسئلة غير APPROVED صراحةً، ولا يُسجَّل كمحاولة رسمية
    is_active: bool = True


@dataclass
class AttemptData:
    id: Optional[int]
    exam_id: int
    student_id: int
    answers: Dict[int, str] = field(default_factory=dict)
    submitted: bool = False
    result: object = None


class QuestionLookup(Protocol):
    def get_for_exam(self, question_id: int) -> dict:
        """يُرجع {"status","canonical_type","answer","points"} أو يرفع KeyError إن لم يوجد."""
        ...


class ExamStore(Protocol):
    def save_exam(self, data: ExamData) -> int: ...
    def get_exam(self, exam_id: int) -> ExamData: ...
    def save_attempt(self, data: AttemptData) -> int: ...
    def get_attempt(self, attempt_id: int) -> AttemptData: ...
    def count_attempts(self, exam_id: int, student_id: int) -> int: ...


def create_exam(store: ExamStore, questions: QuestionLookup, name: str, question_ids: List[int],
                 duration_minutes: Optional[int] = None, shuffle_questions: bool = False,
                 shuffle_choices: bool = False, allow_retake: bool = False,
                 is_training: bool = False) -> ExamData:
    if not question_ids:
        raise ExamServiceError("يجب اختيار سؤال واحد على الأقل للامتحان.")

    if not is_training:
        for qid in question_ids:
            q = questions.get_for_exam(qid)
            if q["status"] != "APPROVED":
                raise ExamServiceError(
                    f"السؤال #{qid} غير معتمد (status={q['status']}) — لا يجوز إضافته لامتحان رسمي.")

    data = ExamData(
        id=None, name=name, question_ids=list(question_ids), duration_minutes=duration_minutes,
        shuffle_questions=shuffle_questions, shuffle_choices=shuffle_choices,
        allow_retake=allow_retake, is_training=is_training,
    )
    data.id = store.save_exam(data)
    return data


def start_attempt(store: ExamStore, exam_id: int, student_id: int) -> AttemptData:
    exam = store.get_exam(exam_id)
    if not exam.is_active:
        raise ExamServiceError("هذا الامتحان غير مُفعَّل حاليًا.")
    if not exam.allow_retake and store.count_attempts(exam_id, student_id) > 0:
        raise ExamServiceError("إعادة المحاولة غير مسموحة لهذا الامتحان.")

    attempt = AttemptData(id=None, exam_id=exam_id, student_id=student_id)
    attempt.id = store.save_attempt(attempt)
    return attempt


def get_ordered_questions(exam: ExamData, shuffle_fn: Callable = random.shuffle) -> List[int]:
    """يُرجع ترتيب الأسئلة للعرض على الطالب — عشوائي إن طُلب، بدون تعديل exam.question_ids الأصلية."""
    ids = list(exam.question_ids)
    if exam.shuffle_questions:
        shuffle_fn(ids)
    return ids


def submit_answer(store: ExamStore, attempt_id: int, question_id: int, answer_text: str) -> AttemptData:
    attempt = store.get_attempt(attempt_id)
    if attempt.submitted:
        raise ExamServiceError("هذه المحاولة أُنهيت بالفعل، لا يمكن تعديل الإجابات.")
    attempt.answers[question_id] = answer_text
    store.save_attempt(attempt)
    return attempt


def finish_attempt(store: ExamStore, questions: QuestionLookup, attempt_id: int):
    attempt = store.get_attempt(attempt_id)
    if attempt.submitted:
        raise ExamServiceError("هذه المحاولة أُنهيت مسبقًا.")

    exam = store.get_exam(attempt.exam_id)
    specs = []
    for qid in exam.question_ids:
        q = questions.get_for_exam(qid)
        specs.append(ExamQuestionSpec(
            question_id=qid, correct_answer=q["answer"] or "",
            canonical_type=q["canonical_type"], marks=q.get("points", 1.0)))

    student_answers = [StudentAnswer(qid, text) for qid, text in attempt.answers.items()]
    result = submit_attempt(specs, student_answers)

    attempt.submitted = True
    attempt.result = result
    store.save_attempt(attempt)
    return result
