import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.exam_service import (  # noqa: E402
    ExamServiceError, create_exam, finish_attempt, get_ordered_questions, start_attempt, submit_answer,
)


class FakeQuestionLookup:
    def __init__(self, questions: dict):
        self._q = questions  # {id: {"status","canonical_type","answer","points"}}

    def get_for_exam(self, question_id):
        return self._q[question_id]


class FakeExamStore:
    def __init__(self):
        self._exams = {}
        self._attempts = {}
        self._next_exam_id = 1
        self._next_attempt_id = 1

    def save_exam(self, data):
        if data.id is None:
            data.id = self._next_exam_id
            self._next_exam_id += 1
        self._exams[data.id] = data
        return data.id

    def get_exam(self, exam_id):
        return self._exams[exam_id]

    def save_attempt(self, data):
        if data.id is None:
            data.id = self._next_attempt_id
            self._next_attempt_id += 1
        self._attempts[data.id] = data
        return data.id

    def get_attempt(self, attempt_id):
        return self._attempts[attempt_id]

    def count_attempts(self, exam_id, student_id):
        return sum(1 for a in self._attempts.values()
                    if a.exam_id == exam_id and a.student_id == student_id and a.submitted)


APPROVED_Q = {"status": "APPROVED", "canonical_type": "MCQ", "answer": "القاهرة", "points": 1.0}
NEEDS_REVIEW_Q = {"status": "NEEDS_REVIEW", "canonical_type": "MCQ", "answer": "شيء", "points": 1.0}


class TestCreateExam(unittest.TestCase):
    def test_create_exam_with_approved_questions(self):
        store, lookup = FakeExamStore(), FakeQuestionLookup({1: APPROVED_Q, 2: APPROVED_Q})
        exam = create_exam(store, lookup, "امتحان تجريبي", [1, 2])
        self.assertIsNotNone(exam.id)
        self.assertEqual(exam.question_ids, [1, 2])

    def test_cannot_use_unapproved_question_in_official_exam(self):
        store, lookup = FakeExamStore(), FakeQuestionLookup({1: NEEDS_REVIEW_Q})
        with self.assertRaises(ExamServiceError):
            create_exam(store, lookup, "امتحان", [1])

    def test_training_mode_allows_unapproved_questions(self):
        store, lookup = FakeExamStore(), FakeQuestionLookup({1: NEEDS_REVIEW_Q})
        exam = create_exam(store, lookup, "تدريب", [1], is_training=True)
        self.assertTrue(exam.is_training)

    def test_empty_question_list_rejected(self):
        store, lookup = FakeExamStore(), FakeQuestionLookup({})
        with self.assertRaises(ExamServiceError):
            create_exam(store, lookup, "امتحان فارغ", [])


class TestAttemptLifecycle(unittest.TestCase):
    def setUp(self):
        self.store = FakeExamStore()
        self.lookup = FakeQuestionLookup({1: APPROVED_Q, 2: APPROVED_Q})
        self.exam = create_exam(self.store, self.lookup, "امتحان", [1, 2], allow_retake=False)

    def test_start_attempt(self):
        attempt = start_attempt(self.store, self.exam.id, student_id=100)
        self.assertIsNotNone(attempt.id)
        self.assertFalse(attempt.submitted)

    def test_retake_blocked_when_not_allowed(self):
        a1 = start_attempt(self.store, self.exam.id, student_id=100)
        submit_answer(self.store, a1.id, 1, "القاهرة")
        finish_attempt(self.store, self.lookup, a1.id)
        with self.assertRaises(ExamServiceError):
            start_attempt(self.store, self.exam.id, student_id=100)

    def test_retake_allowed_when_enabled(self):
        exam = create_exam(self.store, self.lookup, "امتحان قابل للإعادة", [1], allow_retake=True)
        a1 = start_attempt(self.store, exam.id, student_id=200)
        finish_attempt(self.store, self.lookup, a1.id)
        a2 = start_attempt(self.store, exam.id, student_id=200)  # يجب ألا يفشل
        self.assertNotEqual(a1.id, a2.id)

    def test_submit_answer_then_finish_calculates_score_via_exam_engine(self):
        attempt = start_attempt(self.store, self.exam.id, student_id=100)
        submit_answer(self.store, attempt.id, 1, "القاهرة")   # صحيحة
        submit_answer(self.store, attempt.id, 2, "خطأ")       # خاطئة
        result = finish_attempt(self.store, self.lookup, attempt.id)
        self.assertEqual(result.correct_count, 1)
        self.assertEqual(result.wrong_count, 1)
        self.assertEqual(result.percentage, 50.0)

    def test_cannot_submit_answer_after_finishing(self):
        attempt = start_attempt(self.store, self.exam.id, student_id=100)
        finish_attempt(self.store, self.lookup, attempt.id)
        with self.assertRaises(ExamServiceError):
            submit_answer(self.store, attempt.id, 1, "أي إجابة بعد الإنهاء")

    def test_cannot_finish_twice(self):
        attempt = start_attempt(self.store, self.exam.id, student_id=100)
        finish_attempt(self.store, self.lookup, attempt.id)
        with self.assertRaises(ExamServiceError):
            finish_attempt(self.store, self.lookup, attempt.id)

    def test_inactive_exam_blocks_new_attempts(self):
        exam_obj = self.store.get_exam(self.exam.id)
        exam_obj.is_active = False
        with self.assertRaises(ExamServiceError):
            start_attempt(self.store, self.exam.id, student_id=999)


class TestQuestionOrdering(unittest.TestCase):
    def test_shuffle_disabled_keeps_original_order(self):
        store, lookup = FakeExamStore(), FakeQuestionLookup({i: APPROVED_Q for i in range(1, 6)})
        exam = create_exam(store, lookup, "امتحان", [1, 2, 3, 4, 5], shuffle_questions=False)
        self.assertEqual(get_ordered_questions(exam), [1, 2, 3, 4, 5])

    def test_shuffle_enabled_uses_injected_shuffle_function(self):
        store, lookup = FakeExamStore(), FakeQuestionLookup({i: APPROVED_Q for i in range(1, 6)})
        exam = create_exam(store, lookup, "امتحان", [1, 2, 3, 4, 5], shuffle_questions=True)
        reversed_shuffle = lambda lst: lst.reverse()  # noqa: E731 — حقن دالة عشوائية حتمية للاختبار
        ordered = get_ordered_questions(exam, shuffle_fn=reversed_shuffle)
        self.assertEqual(ordered, [5, 4, 3, 2, 1])
        self.assertEqual(exam.question_ids, [1, 2, 3, 4, 5], "لا يجوز تعديل ترتيب الأسئلة الأصلي في الامتحان")


if __name__ == "__main__":
    unittest.main(verbosity=2)
