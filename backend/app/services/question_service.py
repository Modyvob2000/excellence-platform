"""
Question Service — طبقة المنطق الكاملة لبنك الأسئلة (إنشاء/قراءة/تعديل/حذف
منطقي/فلترة/بحث)، مفصولة تمامًا عن FastAPI وSQLAlchemy عبر واجهة QuestionStore
(Protocol) — بحيث تُختبر بالكامل بمستودع وهمي في الذاكرة (انظر
test_question_service.py)، ثم يُستخدم في الإنتاج عبر SqlAlchemyQuestionStore
(routers/questions.py) بدون تغيير أي سطر هنا.

قاعدة صارمة: create_question لا تضع أبدًا status="APPROVED" ولا تحذف حرفيًا —
delete_question هنا يعني دائمًا soft delete (is_deleted=True).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Tuple

from app.services.classification import classify as default_classify
from app.services.dedup import find_duplicates


@dataclass
class QuestionData:
    id: Optional[int]
    question: str
    answer: Optional[str] = None
    correction: Optional[str] = None
    choices: List[str] = field(default_factory=list)
    lesson_id: Optional[int] = None
    question_type_id: Optional[int] = None
    original_question_type: Optional[str] = None
    canonical_type: Optional[str] = None
    status: str = "NEEDS_REVIEW"
    approved: bool = False
    is_hidden: bool = False
    is_deleted: bool = False
    source_type: str = "MANUAL"
    points: float = 1.0
    created_by: Optional[int] = None


class QuestionStore(Protocol):
    def insert(self, data: QuestionData) -> int: ...
    def get(self, question_id: int) -> Optional[QuestionData]: ...
    def update(self, question_id: int, patch: dict) -> QuestionData: ...
    def list(self, filters: dict) -> List[QuestionData]: ...
    def all_texts(self) -> List[Tuple[int, str]]: ...


class QuestionServiceError(Exception):
    pass


def create_question(store: QuestionStore, question: str, lesson_id: int,
                     answer: Optional[str] = None, choices: Optional[List[str]] = None,
                     original_question_type: Optional[str] = None,
                     source_type: str = "MANUAL", created_by: Optional[int] = None,
                     classify_fn=default_classify) -> Tuple[QuestionData, list]:
    """
    ينشئ سؤالًا جديدًا. يُصنَّف تلقائيًا (مع NEEDS_CLASSIFICATION عند الثقة
    المنخفضة)، ويُفحص فورًا مقابل بنك الأسئلة الحالي لتنبيه المستخدم بوجود
    تكرار محتمل — **لا يُرفض الإنشاء ولا يُحذف تلقائيًا أبدًا**، فقط يُرجَع
    مع تحذير (duplicates) ليقرر المستخدم/المراجع.
    """
    if not question or not question.strip():
        raise QuestionServiceError("نص السؤال لا يمكن أن يكون فارغًا.")
    if not lesson_id:
        raise QuestionServiceError("يجب ربط السؤال بدرس (lesson_id).")

    classification = classify_fn(question, original_question_type)
    duplicates = find_duplicates(question, store.all_texts())

    status = "NEEDS_CLASSIFICATION" if classification.needs_classification else "NEEDS_REVIEW"
    if duplicates:
        status = "DUPLICATE"

    data = QuestionData(
        id=None, question=question, answer=answer, choices=choices or [],
        lesson_id=lesson_id, canonical_type=classification.canonical_type,
        original_question_type=original_question_type, status=status,
        source_type=source_type, created_by=created_by,
    )
    new_id = store.insert(data)
    saved = store.get(new_id)
    return saved, duplicates


def get_question(store: QuestionStore, question_id: int) -> QuestionData:
    record = store.get(question_id)
    if record is None or record.is_deleted:
        raise QuestionServiceError(f"السؤال #{question_id} غير موجود.")
    return record


def update_question(store: QuestionStore, question_id: int, patch: dict) -> QuestionData:
    """
    تعديل محتوى سؤال. تعديل نص السؤال يُعيد فحص التصنيف والتكرار تلقائيًا
    (لأن المحتوى تغيّر)، لكنه **لا يغيّر حالة الاعتماد تلقائيًا** — سؤال
    APPROVED يظل APPROVED بعد تعديل بسيط إلا إذا غيّر المستخدم الحالة صراحة
    عبر review_workflow (المسار المخصص لذلك).
    """
    existing = get_question(store, question_id)
    if "question" in patch and patch["question"] != existing.question:
        classification = default_classify(patch["question"], existing.original_question_type)
        patch.setdefault("canonical_type", classification.canonical_type)
    return store.update(question_id, patch)


def delete_question(store: QuestionStore, question_id: int) -> QuestionData:
    """Soft delete فقط — أبدًا حذف حقيقي. راجع review_workflow.soft_delete للمسار الموحّد مع الصلاحيات."""
    return store.update(question_id, {"is_deleted": True})


def restore_question(store: QuestionStore, question_id: int) -> QuestionData:
    return store.update(question_id, {"is_deleted": False})


def list_questions(store: QuestionStore, grade_id=None, subject_id=None, unit_id=None,
                    lesson_id=None, canonical_type=None, status=None,
                    include_deleted: bool = False) -> List[QuestionData]:
    filters = {
        "grade_id": grade_id, "subject_id": subject_id, "unit_id": unit_id,
        "lesson_id": lesson_id, "canonical_type": canonical_type, "status": status,
        "include_deleted": include_deleted,
    }
    return store.list({k: v for k, v in filters.items() if v is not None or k == "include_deleted"})


def search_questions(store: QuestionStore, query: str, limit: int = 20) -> List[Tuple[QuestionData, float]]:
    """بحث ذكي: تطابق كلمات + تشابه نصي محلي (انظر services/search.py للواجهة العامة الموحّدة)."""
    from app.services.search import rank_by_relevance
    candidates = [(qid, text) for qid, text in store.all_texts()]
    ranked = rank_by_relevance(query, candidates, limit=limit)
    results = []
    for qid, score in ranked:
        record = store.get(qid)
        if record and not record.is_deleted:
            results.append((record, score))
    return results
