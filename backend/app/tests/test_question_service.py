import os
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.question_service import (  # noqa: E402
    QuestionData, QuestionServiceError, create_question, delete_question, get_question,
    list_questions, restore_question, search_questions, update_question,
)


class FakeQuestionStore:
    """مستودع وهمي كامل في الذاكرة — بديل SqlAlchemyQuestionStore الحقيقي للاختبار فقط."""

    def __init__(self):
        self._next_id = 1
        self._data = {}

    def insert(self, data: QuestionData) -> int:
        qid = self._next_id
        self._next_id += 1
        data.id = qid
        self._data[qid] = data
        return qid

    def get(self, question_id):
        return self._data.get(question_id)

    def update(self, question_id, patch):
        record = self._data[question_id]
        updated = replace(record, **patch)
        self._data[question_id] = updated
        return updated

    def list(self, filters):
        results = list(self._data.values())
        if not filters.get("include_deleted"):
            results = [r for r in results if not r.is_deleted]
        if filters.get("lesson_id"):
            results = [r for r in results if r.lesson_id == filters["lesson_id"]]
        if filters.get("canonical_type"):
            results = [r for r in results if r.canonical_type == filters["canonical_type"]]
        if filters.get("status"):
            results = [r for r in results if r.status == filters["status"]]
        return results

    def all_texts(self):
        return [(qid, d.question) for qid, d in self._data.items() if not d.is_deleted]


class TestCreateQuestion(unittest.TestCase):
    def test_create_clear_question_goes_to_needs_review(self):
        store = FakeQuestionStore()
        record, dups = create_question(store, "من هو أحمد عرابي؟", lesson_id=3, answer="قائد")
        self.assertEqual(record.status, "NEEDS_REVIEW")
        self.assertEqual(record.canonical_type, "WHO_IS")
        self.assertEqual(dups, [])
        self.assertIsNotNone(record.id)

    def test_create_never_auto_approves(self):
        store = FakeQuestionStore()
        record, _ = create_question(store, "من هو محمد علي؟", lesson_id=1, answer="حاكم")
        self.assertNotEqual(record.status, "APPROVED")
        self.assertFalse(record.approved)

    def test_create_flags_duplicate_but_still_creates(self):
        store = FakeQuestionStore()
        create_question(store, "بم تفسر أهمية نهر النيل؟", lesson_id=1, answer="مهم")
        record, dups = create_question(store, "وضح سبب أهمية نهر النيل.", lesson_id=1, answer="مهم")
        self.assertEqual(record.status, "DUPLICATE")
        self.assertEqual(len(dups), 1)
        self.assertIsNotNone(record.id, "يجب أن يُنشأ السؤال رغم التكرار، لا يُرفض ولا يُحذف تلقائيًا")

    def test_empty_question_text_rejected(self):
        store = FakeQuestionStore()
        with self.assertRaises(QuestionServiceError):
            create_question(store, "   ", lesson_id=1)

    def test_missing_lesson_id_rejected(self):
        store = FakeQuestionStore()
        with self.assertRaises(QuestionServiceError):
            create_question(store, "سؤال صحيح", lesson_id=None)

    def test_ambiguous_text_needs_classification(self):
        store = FakeQuestionStore()
        record, _ = create_question(store, "نص غامض تمامًا 123", lesson_id=1)
        self.assertEqual(record.status, "NEEDS_CLASSIFICATION")


class TestReadUpdateDelete(unittest.TestCase):
    def test_get_existing_question(self):
        store = FakeQuestionStore()
        created, _ = create_question(store, "من هو أحمد عرابي؟", lesson_id=1)
        fetched = get_question(store, created.id)
        self.assertEqual(fetched.question, "من هو أحمد عرابي؟")

    def test_get_nonexistent_question_raises(self):
        store = FakeQuestionStore()
        with self.assertRaises(QuestionServiceError):
            get_question(store, 999)

    def test_get_deleted_question_raises(self):
        store = FakeQuestionStore()
        created, _ = create_question(store, "سؤال", lesson_id=1)
        delete_question(store, created.id)
        with self.assertRaises(QuestionServiceError):
            get_question(store, created.id)

    def test_update_question_text_re_evaluates_classification(self):
        store = FakeQuestionStore()
        created, _ = create_question(store, "نص غامض 111", lesson_id=1)
        self.assertEqual(created.canonical_type, "OTHER")
        updated = update_question(store, created.id, {"question": "من هو أحمد عرابي؟"})
        self.assertEqual(updated.canonical_type, "WHO_IS")

    def test_update_does_not_change_approval_status_implicitly(self):
        store = FakeQuestionStore()
        created, _ = create_question(store, "سؤال", lesson_id=1)
        store.update(created.id, {"status": "APPROVED", "approved": True})
        updated = update_question(store, created.id, {"answer": "إجابة محدّثة"})
        self.assertEqual(updated.status, "APPROVED")
        self.assertTrue(updated.approved)

    def test_delete_is_soft_and_restorable(self):
        store = FakeQuestionStore()
        created, _ = create_question(store, "سؤال", lesson_id=1)
        delete_question(store, created.id)
        self.assertTrue(store.get(created.id).is_deleted)
        self.assertIsNotNone(store.get(created.id), "السجل يجب أن يبقى موجودًا فعليًا في المخزن")
        restore_question(store, created.id)
        self.assertFalse(store.get(created.id).is_deleted)


class TestListingAndFiltering(unittest.TestCase):
    def test_filter_by_lesson_and_status(self):
        store = FakeQuestionStore()
        create_question(store, "من هو أحمد عرابي؟", lesson_id=1)     # NEEDS_REVIEW, lesson 1
        create_question(store, "من هو سعد زغلول؟", lesson_id=2)      # NEEDS_REVIEW, lesson 2
        create_question(store, "نص غامض 1", lesson_id=1)             # NEEDS_CLASSIFICATION, lesson 1

        lesson1 = list_questions(store, lesson_id=1)
        self.assertEqual(len(lesson1), 2)

        lesson1_needs_review = list_questions(store, lesson_id=1, status="NEEDS_REVIEW")
        self.assertEqual(len(lesson1_needs_review), 1)

    def test_deleted_excluded_by_default(self):
        store = FakeQuestionStore()
        created, _ = create_question(store, "سؤال", lesson_id=1)
        delete_question(store, created.id)
        self.assertEqual(list_questions(store), [])
        self.assertEqual(len(list_questions(store, include_deleted=True)), 1)


class TestSearchIntegration(unittest.TestCase):
    def test_search_finds_relevant_question(self):
        store = FakeQuestionStore()
        create_question(store, "أهمية نهر النيل في حياة المصريين", lesson_id=1)
        create_question(store, "قواعد اللغة الإنجليزية", lesson_id=1)
        results = search_questions(store, "نهر النيل")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0].question, "أهمية نهر النيل في حياة المصريين")


if __name__ == "__main__":
    unittest.main(verbosity=2)
