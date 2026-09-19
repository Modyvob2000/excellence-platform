"""
Import Pipeline (Phase: مركز الاستيراد الذكي) — يربط:

  Upload -> Batch -> Extract -> Parse -> Classify -> Map Content
  -> Duplicate Detection -> Answer Validation -> Review Queue

هذه الوحدة منطق خالص (لا قاعدة بيانات، لا شبكة) يعمل عبر الحقن (DI):
تُمرَّر لها extractor وrepository الأسئلة الموجودة وregistry الأنواع، فتُرجع
قائمة "قرارات" (PipelineDecision) لكل سؤال — القرار النهائي بالاعتماد يبقى
دائمًا بشريًا عبر review_workflow، هذه الوحدة لا تعتمد أي سؤال أبدًا.

مصدر الأسئلة (source_type) يُمرَّر صراحة من الطبقة المستدعية (PDF/WORD/EXCEL/TEXT)
ولا تخترع هذه الوحدة أي نص غير موجود في الملف — عند "استخراج من مصدر" فقط،
وليس "توليد بالذكاء الاصطناعي" (ذاك مسار منفصل بالكامل في ai_question_generator.py).
"""
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Tuple

from app.services.classification import ClassificationResult, classify as default_classify
from app.services.dedup import DuplicateMatch, find_duplicates


@dataclass
class PipelineDecision:
    raw_text: str
    question: str
    answer: Optional[str]
    original_type: Optional[str]
    status: str                      # NEEDS_REVIEW | NEEDS_CLASSIFICATION | DUPLICATE
    classification: ClassificationResult
    duplicates: List[DuplicateMatch] = field(default_factory=list)
    page_number: Optional[int] = None
    answer_flagged: bool = False     # True إذا الإجابة مفقودة أو تبدو غير مكتملة
    notes: List[str] = field(default_factory=list)


@dataclass
class BatchSummary:
    total: int = 0
    needs_review: int = 0
    needs_classification: int = 0
    duplicate: int = 0

    def record(self, status: str):
        self.total += 1
        if status == "NEEDS_REVIEW":
            self.needs_review += 1
        elif status == "NEEDS_CLASSIFICATION":
            self.needs_classification += 1
        elif status == "DUPLICATE":
            self.duplicate += 1


def validate_answer(answer: Optional[str]) -> bool:
    """فحص بسيط جدًا وصادق: هل توجد إجابة نصية غير فارغة على الإطلاق؟
    لا يوجد هنا أي تحقق 'دلالي' من صحة الإجابة — ذلك يتطلب مزود AI فعلي غير متاح هنا،
    وسيُضاف لاحقًا خلف نفس نمط الحقن (DI) دون تغيير هذه الدالة من الخارج."""
    return bool(answer and answer.strip())


def process_import_item(
    raw_text: str,
    question_text: str,
    answer: Optional[str],
    existing_questions: Iterable[Tuple[int, str]],
    original_type: Optional[str] = None,
    page_number: Optional[int] = None,
    classify_fn: Callable[[str, Optional[str]], ClassificationResult] = default_classify,
) -> PipelineDecision:
    """يعالج سؤالًا واحدًا مستخرجًا عبر: Classify -> Duplicate Detection -> Answer Validation."""
    classification = classify_fn(question_text, original_type)
    duplicates = find_duplicates(question_text, existing_questions)

    notes: List[str] = []
    answer_ok = validate_answer(answer)
    if not answer_ok:
        notes.append("لم يتم العثور على إجابة صريحة في المصدر — يحتاج مراجعة يدوية.")

    if duplicates:
        status = "DUPLICATE"
    elif classification.needs_classification:
        status = "NEEDS_CLASSIFICATION"
    else:
        status = "NEEDS_REVIEW"  # أبدًا APPROVED تلقائيًا — قاعدة صارمة غير قابلة للكسر هنا

    return PipelineDecision(
        raw_text=raw_text, question=question_text, answer=answer, original_type=original_type,
        status=status, classification=classification, duplicates=duplicates,
        page_number=page_number, answer_flagged=not answer_ok, notes=notes,
    )


def run_batch(
    items: List[dict],  # كل عنصر: {"raw_text","question","answer","original_type","page_number"}
    existing_questions: Iterable[Tuple[int, str]],
    classify_fn: Callable[[str, Optional[str]], ClassificationResult] = default_classify,
) -> Tuple[List[PipelineDecision], BatchSummary]:
    """
    ينفّذ خط الأنابيب الكامل على دفعة (Batch) من العناصر المُستخرجة مسبقًا من
    ملف (PDF/Word/Excel/نص مُلصَق). existing_questions تُمرَّر لحظة كل استدعاء
    تباعًا (accumulating) بحيث يُكتشف التكرار أيضًا بين أسئلة الدفعة نفسها مع
    بعضها، وليس فقط مع بنك الأسئلة القديم — يحاكي هذا حقيقة أن ملفات الاستيراد
    كثيرًا ما تحوي أسئلة مكررة داخليًا.
    """
    summary = BatchSummary()
    decisions: List[PipelineDecision] = []
    accumulated = list(existing_questions)
    next_temp_id = -1  # معرّفات مؤقتة سالبة لأسئلة الدفعة نفسها (لم تُحفظ بعد في DB)

    for item in items:
        decision = process_import_item(
            raw_text=item["raw_text"], question_text=item["question"], answer=item.get("answer"),
            existing_questions=accumulated, original_type=item.get("original_type"),
            page_number=item.get("page_number"), classify_fn=classify_fn,
        )
        summary.record(decision.status)
        decisions.append(decision)
        accumulated.append((next_temp_id, decision.question))
        next_temp_id -= 1

    return decisions, summary
