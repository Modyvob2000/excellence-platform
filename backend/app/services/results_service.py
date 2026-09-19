"""
Results Service — سجل المحاولات، تقارير حسب الامتحان/المادة/الدرس.
منطق تجميع خالص (لا قاعدة بيانات) — يُغذّى بقوائم نتائج فعلية من exam_engine
عبر الاستعلام في الـrouter، فيبقى قابلاً للاختبار بالكامل بدون DB.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class AttemptSummary:
    attempt_id: int
    exam_id: int
    student_id: int
    score: float
    total_marks: float
    percentage: float
    correct_count: int
    wrong_count: int
    submitted_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None


@dataclass
class ExamReport:
    exam_id: int
    attempts_count: int
    average_percentage: float
    pass_rate: float          # نسبة من حقق >= PASS_THRESHOLD
    highest_percentage: float
    lowest_percentage: float


PASS_THRESHOLD = 50.0


def student_history(attempts: List[AttemptSummary], student_id: int) -> List[AttemptSummary]:
    return sorted(
        [a for a in attempts if a.student_id == student_id],
        key=lambda a: a.submitted_at or datetime.min, reverse=True,
    )


def build_exam_report(attempts: List[AttemptSummary], exam_id: int) -> ExamReport:
    relevant = [a for a in attempts if a.exam_id == exam_id]
    if not relevant:
        return ExamReport(exam_id=exam_id, attempts_count=0, average_percentage=0.0,
                           pass_rate=0.0, highest_percentage=0.0, lowest_percentage=0.0)

    percentages = [a.percentage for a in relevant]
    passed = sum(1 for p in percentages if p >= PASS_THRESHOLD)
    return ExamReport(
        exam_id=exam_id, attempts_count=len(relevant),
        average_percentage=round(sum(percentages) / len(percentages), 2),
        pass_rate=round((passed / len(relevant)) * 100, 2),
        highest_percentage=max(percentages), lowest_percentage=min(percentages),
    )


def student_average_percentage(attempts: List[AttemptSummary], student_id: int) -> float:
    relevant = [a for a in attempts if a.student_id == student_id]
    if not relevant:
        return 0.0
    return round(sum(a.percentage for a in relevant) / len(relevant), 2)
