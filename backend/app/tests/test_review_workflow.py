import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.review_workflow import (  # noqa: E402
    QuestionRecord, WorkflowError, approve, bulk_apply, change_lesson, change_type,
    mark_duplicate, reject, restore, send_to_review, soft_delete,
)


class FakeQuestionRepository:
    """مستودع وهمي في الذاكرة بالكامل — لا قاعدة بيانات، لا شبكة، DI بحت."""

    def __init__(self, records):
        self._records = {r.id: r for r in records}
        self.actions = []

    def get(self, question_id):
        return self._records[question_id]

    def save(self, record):
        self._records[record.id] = record

    def log_action(self, action):
        self.actions.append(action)


def repo_with(*records):
    return FakeQuestionRepository(list(records))


class TestSingleTransitions(unittest.TestCase):
    def test_approve_from_needs_review(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"))
        rec = approve(repo, 1, reviewer_id=9, reviewer_role="TEACHER")
        self.assertEqual(rec.status, "APPROVED")
        self.assertTrue(rec.approved)
        self.assertEqual(len(repo.actions), 1)
        self.assertEqual(repo.actions[0].action, "APPROVE")

    def test_cannot_approve_directly_from_imported(self):
        repo = repo_with(QuestionRecord(id=1, status="IMPORTED"))
        with self.assertRaises(WorkflowError):
            approve(repo, 1, reviewer_id=9, reviewer_role="TEACHER")

    def test_student_cannot_approve(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"))
        with self.assertRaises(WorkflowError):
            approve(repo, 1, reviewer_id=9, reviewer_role="STUDENT")
        # لم يتغيّر شيء فعليًا
        self.assertEqual(repo.get(1).status, "NEEDS_REVIEW")

    def test_reject_records_reason(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"))
        reject(repo, 1, reviewer_id=9, reviewer_role="REVIEWER", reason="إجابة غير دقيقة")
        self.assertEqual(repo.actions[-1].details["reason"], "إجابة غير دقيقة")

    def test_rejected_can_be_reopened_to_needs_review(self):
        repo = repo_with(QuestionRecord(id=1, status="REJECTED"))
        rec = send_to_review(repo, 1, reviewer_id=9, reviewer_role="ADMIN")
        self.assertEqual(rec.status, "NEEDS_REVIEW")

    def test_approved_can_be_reverted_to_rejected(self):
        repo = repo_with(QuestionRecord(id=1, status="APPROVED", approved=True))
        rec = reject(repo, 1, reviewer_id=9, reviewer_role="ADMIN")
        self.assertEqual(rec.status, "REJECTED")
        self.assertFalse(rec.approved)

    def test_mark_duplicate_from_needs_review(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"))
        rec = mark_duplicate(repo, 1, reviewer_id=9, reviewer_role="TEACHER", duplicate_of=55)
        self.assertEqual(rec.status, "DUPLICATE")
        self.assertEqual(repo.actions[-1].details["duplicate_of"], 55)

    def test_duplicate_marked_question_can_still_be_approved_by_manager_decision(self):
        # القرار النهائي للمدير كما في المتطلبات — DUPLICATE ليس رفضًا تلقائيًا
        repo = repo_with(QuestionRecord(id=1, status="DUPLICATE"))
        rec = approve(repo, 1, reviewer_id=9, reviewer_role="ADMIN")
        self.assertEqual(rec.status, "APPROVED")

    def test_change_type_moves_out_of_needs_classification(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_CLASSIFICATION", question_type_id=None))
        rec = change_type(repo, 1, reviewer_id=9, reviewer_role="TEACHER", new_type_id=3)
        self.assertEqual(rec.question_type_id, 3)
        self.assertEqual(rec.status, "NEEDS_REVIEW")

    def test_change_lesson_updates_lesson_id(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW", lesson_id=5))
        rec = change_lesson(repo, 1, reviewer_id=9, reviewer_role="ADMIN", new_lesson_id=8)
        self.assertEqual(rec.lesson_id, 8)

    def test_soft_delete_never_hard_deletes(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"))
        soft_delete(repo, 1, reviewer_id=9, reviewer_role="ADMIN")
        rec = repo.get(1)  # لا يزال موجودًا في المستودع
        self.assertTrue(rec.is_deleted)
        restored = restore(repo, 1, reviewer_id=9, reviewer_role="ADMIN")
        self.assertFalse(restored.is_deleted)

    def test_every_transition_is_audit_logged(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"))
        approve(repo, 1, reviewer_id=42, reviewer_role="ADMIN")
        self.assertEqual(repo.actions[0].reviewer_id, 42)
        self.assertEqual(repo.actions[0].from_status, "NEEDS_REVIEW")
        self.assertEqual(repo.actions[0].to_status, "APPROVED")


class TestBulkReview(unittest.TestCase):
    def test_bulk_approve_multiple_questions(self):
        repo = repo_with(
            QuestionRecord(id=1, status="NEEDS_REVIEW"),
            QuestionRecord(id=2, status="NEEDS_REVIEW"),
            QuestionRecord(id=3, status="NEEDS_REVIEW"),
        )
        result = bulk_apply(repo, [1, 2, 3], reviewer_id=9, reviewer_role="ADMIN", operation="approve")
        self.assertEqual(result.succeeded, [1, 2, 3])
        self.assertEqual(result.failed, {})
        for qid in (1, 2, 3):
            self.assertEqual(repo.get(qid).status, "APPROVED")

    def test_bulk_approve_partial_failure_does_not_stop_batch(self):
        repo = repo_with(
            QuestionRecord(id=1, status="NEEDS_REVIEW"),
            QuestionRecord(id=2, status="IMPORTED"),  # لا يمكن اعتماده مباشرة من IMPORTED
            QuestionRecord(id=3, status="NEEDS_REVIEW"),
        )
        result = bulk_apply(repo, [1, 2, 3], reviewer_id=9, reviewer_role="ADMIN", operation="approve")
        self.assertEqual(result.succeeded, [1, 3])
        self.assertIn(2, result.failed)
        self.assertEqual(repo.get(1).status, "APPROVED")
        self.assertEqual(repo.get(2).status, "IMPORTED")  # لم يتأثر
        self.assertEqual(repo.get(3).status, "APPROVED")

    def test_bulk_reject_with_shared_reason(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"), QuestionRecord(id=2, status="NEEDS_REVIEW"))
        bulk_apply(repo, [1, 2], reviewer_id=9, reviewer_role="TEACHER", operation="reject",
                   reason="دفعة مستوردة بجودة منخفضة")
        self.assertEqual(repo.get(1).status, "REJECTED")
        self.assertEqual(repo.actions[0].details["reason"], "دفعة مستوردة بجودة منخفضة")

    def test_bulk_change_type(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"), QuestionRecord(id=2, status="NEEDS_REVIEW"))
        result = bulk_apply(repo, [1, 2], reviewer_id=9, reviewer_role="ADMIN",
                             operation="change_type", new_type_id=7)
        self.assertEqual(result.succeeded, [1, 2])
        self.assertEqual(repo.get(1).question_type_id, 7)

    def test_bulk_delete_is_soft(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"))
        bulk_apply(repo, [1], reviewer_id=9, reviewer_role="ADMIN", operation="delete")
        self.assertTrue(repo.get(1).is_deleted)

    def test_bulk_unknown_operation_raises(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"))
        with self.assertRaises(WorkflowError):
            bulk_apply(repo, [1], reviewer_id=9, reviewer_role="ADMIN", operation="explode")

    def test_bulk_student_role_fails_all(self):
        repo = repo_with(QuestionRecord(id=1, status="NEEDS_REVIEW"), QuestionRecord(id=2, status="NEEDS_REVIEW"))
        result = bulk_apply(repo, [1, 2], reviewer_id=9, reviewer_role="STUDENT", operation="approve")
        self.assertEqual(result.succeeded, [])
        self.assertEqual(len(result.failed), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
