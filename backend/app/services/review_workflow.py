"""
Review Workflow — حالات السؤال والانتقالات المسموحة + Bulk Review.

الحالات (Phase 18):
    IMPORTED -> NEEDS_REVIEW | NEEDS_CLASSIFICATION | DUPLICATE
    NEEDS_REVIEW -> APPROVED | REJECTED | NEEDS_CLASSIFICATION | DUPLICATE
    NEEDS_CLASSIFICATION -> NEEDS_REVIEW (بعد تحديد المدير للنوع يدويًا)
    DUPLICATE -> NEEDS_REVIEW | REJECTED | APPROVED (القرار النهائي للمدير دائمًا)
    APPROVED -> REJECTED (يمكن التراجع لاحقًا إذا اكتُشفت مشكلة)
    REJECTED -> NEEDS_REVIEW (يمكن إعادة فتحه للمراجعة)

قاعدة صارمة غير قابلة للكسر مهما كانت الحالة: **لا يدخل أي سؤال حالة
APPROVED إلا بفعل صريح من مستخدم بشري بصلاحية REVIEWER فأعلى** — لا يوجد
مسار واحد في هذا الملف يضع APPROVED تلقائيًا.

هذه الوحدة لا تعرف شيئًا عن قاعدة البيانات؛ تتعامل مع QuestionRepository
كواجهة (Protocol) — ما يجعلها قابلة للاختبار الكامل بمستودع وهمي في الذاكرة
(انظر app/tests/test_review_workflow.py) بدون أي اتصال بقاعدة بيانات حقيقية.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Protocol

STATUSES = ["IMPORTED", "NEEDS_REVIEW", "NEEDS_CLASSIFICATION", "DUPLICATE", "APPROVED", "REJECTED"]

ALLOWED_TRANSITIONS: Dict[str, List[str]] = {
    "IMPORTED": ["NEEDS_REVIEW", "NEEDS_CLASSIFICATION", "DUPLICATE"],
    "NEEDS_REVIEW": ["APPROVED", "REJECTED", "NEEDS_CLASSIFICATION", "DUPLICATE"],
    "NEEDS_CLASSIFICATION": ["NEEDS_REVIEW"],
    "DUPLICATE": ["NEEDS_REVIEW", "REJECTED", "APPROVED"],
    "APPROVED": ["REJECTED"],
    "REJECTED": ["NEEDS_REVIEW"],
}

ROLES_ALLOWED_TO_REVIEW = ("REVIEWER", "TEACHER", "ADMIN", "SUPER_ADMIN")


class WorkflowError(Exception):
    pass


@dataclass
class QuestionRecord:
    """تمثيل مبسّط لسؤال داخل هذه الطبقة — الحقول الحقيقية أكثر في models.py."""
    id: int
    status: str = "IMPORTED"
    lesson_id: Optional[int] = None
    question_type_id: Optional[int] = None
    approved: bool = False
    is_deleted: bool = False


@dataclass
class ReviewActionRecord:
    question_id: int
    reviewer_id: int
    action: str
    from_status: str
    to_status: str
    details: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class QuestionRepository(Protocol):
    def get(self, question_id: int) -> QuestionRecord: ...
    def save(self, record: QuestionRecord) -> None: ...
    def log_action(self, action: ReviewActionRecord) -> None: ...


def _transition(repo: QuestionRepository, question_id: int, to_status: str,
                 reviewer_id: int, reviewer_role: str, action_name: str, details: dict = None):
    if reviewer_role not in ROLES_ALLOWED_TO_REVIEW:
        raise WorkflowError(f"الدور {reviewer_role} لا يملك صلاحية مراجعة الأسئلة.")
    record = repo.get(question_id)
    allowed = ALLOWED_TRANSITIONS.get(record.status, [])
    if to_status not in allowed:
        raise WorkflowError(
            f"انتقال غير مسموح: {record.status} -> {to_status} للسؤال #{question_id}.")
    from_status = record.status
    record.status = to_status
    record.approved = (to_status == "APPROVED")
    repo.save(record)
    repo.log_action(ReviewActionRecord(
        question_id=question_id, reviewer_id=reviewer_id, action=action_name,
        from_status=from_status, to_status=to_status, details=details or {}))
    return record


def approve(repo: QuestionRepository, question_id: int, reviewer_id: int, reviewer_role: str) -> QuestionRecord:
    return _transition(repo, question_id, "APPROVED", reviewer_id, reviewer_role, "APPROVE")


def reject(repo: QuestionRepository, question_id: int, reviewer_id: int, reviewer_role: str,
           reason: str = "") -> QuestionRecord:
    return _transition(repo, question_id, "REJECTED", reviewer_id, reviewer_role, "REJECT",
                        {"reason": reason})


def mark_duplicate(repo: QuestionRepository, question_id: int, reviewer_id: int, reviewer_role: str,
                    duplicate_of: int) -> QuestionRecord:
    return _transition(repo, question_id, "DUPLICATE", reviewer_id, reviewer_role, "MARK_DUPLICATE",
                        {"duplicate_of": duplicate_of})


def send_to_review(repo: QuestionRepository, question_id: int, reviewer_id: int, reviewer_role: str) -> QuestionRecord:
    return _transition(repo, question_id, "NEEDS_REVIEW", reviewer_id, reviewer_role, "SEND_TO_REVIEW")


def change_type(repo: QuestionRepository, question_id: int, reviewer_id: int, reviewer_role: str,
                 new_type_id: int) -> QuestionRecord:
    if reviewer_role not in ROLES_ALLOWED_TO_REVIEW:
        raise WorkflowError(f"الدور {reviewer_role} لا يملك صلاحية تعديل الأسئلة.")
    record = repo.get(question_id)
    old_type = record.question_type_id
    record.question_type_id = new_type_id
    if record.status == "NEEDS_CLASSIFICATION":
        record.status = "NEEDS_REVIEW"
    repo.save(record)
    repo.log_action(ReviewActionRecord(
        question_id=question_id, reviewer_id=reviewer_id, action="CHANGE_TYPE",
        from_status=record.status, to_status=record.status,
        details={"old_type_id": old_type, "new_type_id": new_type_id}))
    return record


def change_lesson(repo: QuestionRepository, question_id: int, reviewer_id: int, reviewer_role: str,
                   new_lesson_id: int) -> QuestionRecord:
    if reviewer_role not in ROLES_ALLOWED_TO_REVIEW:
        raise WorkflowError(f"الدور {reviewer_role} لا يملك صلاحية تعديل الأسئلة.")
    record = repo.get(question_id)
    old_lesson = record.lesson_id
    record.lesson_id = new_lesson_id
    repo.save(record)
    repo.log_action(ReviewActionRecord(
        question_id=question_id, reviewer_id=reviewer_id, action="CHANGE_LESSON",
        from_status=record.status, to_status=record.status,
        details={"old_lesson_id": old_lesson, "new_lesson_id": new_lesson_id}))
    return record


def soft_delete(repo: QuestionRepository, question_id: int, reviewer_id: int, reviewer_role: str) -> QuestionRecord:
    """
    'حذف' في هذا النظام يعني دائمًا Soft Delete (is_deleted=True) — أبدًا حذف
    فعلي من قاعدة البيانات. السؤال يختفي من كل الواجهات لكنه قابل للاستعادة.
    """
    if reviewer_role not in ROLES_ALLOWED_TO_REVIEW:
        raise WorkflowError(f"الدور {reviewer_role} لا يملك صلاحية حذف الأسئلة.")
    record = repo.get(question_id)
    record.is_deleted = True
    repo.save(record)
    repo.log_action(ReviewActionRecord(
        question_id=question_id, reviewer_id=reviewer_id, action="SOFT_DELETE",
        from_status=record.status, to_status=record.status, details={}))
    return record


def restore(repo: QuestionRepository, question_id: int, reviewer_id: int, reviewer_role: str) -> QuestionRecord:
    if reviewer_role not in ROLES_ALLOWED_TO_REVIEW:
        raise WorkflowError(f"الدور {reviewer_role} لا يملك صلاحية استعادة الأسئلة.")
    record = repo.get(question_id)
    record.is_deleted = False
    repo.save(record)
    repo.log_action(ReviewActionRecord(
        question_id=question_id, reviewer_id=reviewer_id, action="RESTORE",
        from_status=record.status, to_status=record.status, details={}))
    return record


@dataclass
class BulkResult:
    succeeded: List[int]
    failed: Dict[int, str]


def bulk_apply(repo: QuestionRepository, question_ids: List[int], reviewer_id: int,
               reviewer_role: str, operation: str, **kwargs) -> BulkResult:
    """
    عملية جماعية آمنة: كل سؤال يُعالَج بمعزل عن الآخرين — فشل سؤال واحد
    (مثلاً انتقال حالة غير مسموح) لا يوقف بقية الدفعة ولا يُرجعها (لا Rollback
    جماعي)، لكنه يُسجَّل بوضوح في failed بدل تجاهله بصمت.
    """
    ops = {
        "approve": lambda qid: approve(repo, qid, reviewer_id, reviewer_role),
        "reject": lambda qid: reject(repo, qid, reviewer_id, reviewer_role, kwargs.get("reason", "")),
        "change_type": lambda qid: change_type(repo, qid, reviewer_id, reviewer_role, kwargs["new_type_id"]),
        "change_lesson": lambda qid: change_lesson(repo, qid, reviewer_id, reviewer_role, kwargs["new_lesson_id"]),
        "delete": lambda qid: soft_delete(repo, qid, reviewer_id, reviewer_role),
    }
    if operation not in ops:
        raise WorkflowError(f"عملية جماعية غير معروفة: {operation}")

    succeeded, failed = [], {}
    for qid in question_ids:
        try:
            ops[operation](qid)
            succeeded.append(qid)
        except WorkflowError as e:
            failed[qid] = str(e)
    return BulkResult(succeeded=succeeded, failed=failed)
