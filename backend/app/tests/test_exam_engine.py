import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.exam_engine import (  # noqa: E402
    ExamQuestionSpec, StudentAnswer, grade_answer, submit_attempt,
)


class TestGradeAnswer(unittest.TestCase):
    def test_mcq_correct(self):
        spec = ExamQuestionSpec(1, correct_answer="القاهرة", canonical_type="MCQ", marks=2)
        grade = grade_answer(spec, "القاهرة")
        self.assertTrue(grade.is_correct)
        self.assertEqual(grade.marks_awarded, 2)

    def test_mcq_incorrect(self):
        spec = ExamQuestionSpec(1, correct_answer="القاهرة", canonical_type="MCQ", marks=2)
        grade = grade_answer(spec, "الإسكندرية")
        self.assertFalse(grade.is_correct)
        self.assertEqual(grade.marks_awarded, 0)

    def test_mcq_tolerant_of_diacritics_and_punctuation(self):
        spec = ExamQuestionSpec(1, correct_answer="القاهرة!", canonical_type="MCQ", marks=1)
        grade = grade_answer(spec, "القاهره")
        self.assertTrue(grade.is_correct)

    def test_true_false(self):
        spec = ExamQuestionSpec(1, correct_answer="صح", canonical_type="TRUE_FALSE", marks=1)
        self.assertTrue(grade_answer(spec, "صح").is_correct)
        self.assertFalse(grade_answer(spec, "خطأ").is_correct)

    def test_empty_answer_marked_wrong_not_pending(self):
        spec = ExamQuestionSpec(1, correct_answer="القاهرة", canonical_type="MCQ", marks=1)
        grade = grade_answer(spec, "")
        self.assertFalse(grade.is_correct)
        self.assertFalse(grade.needs_manual_grading)

    def test_who_is_close_match_auto_graded_correct(self):
        spec = ExamQuestionSpec(1, correct_answer="محمد علي باشا", canonical_type="WHO_IS", marks=1)
        grade = grade_answer(spec, "محمد علي باشا")
        self.assertTrue(grade.is_correct)

    def test_who_is_gray_zone_needs_manual_grading(self):
        spec = ExamQuestionSpec(1, correct_answer="محمد علي باشا حاكم مصر", canonical_type="WHO_IS", marks=1)
        grade = grade_answer(spec, "محمد علي كان مهمًا في التاريخ")
        self.assertIsNone(grade.is_correct)
        self.assertTrue(grade.needs_manual_grading)
        self.assertEqual(grade.marks_awarded, 0)

    def test_essay_always_needs_manual_grading(self):
        spec = ExamQuestionSpec(1, correct_answer="أي شيء", canonical_type="ESSAY", marks=5)
        grade = grade_answer(spec, "مقال طويل كتبه الطالب")
        self.assertIsNone(grade.is_correct)
        self.assertTrue(grade.needs_manual_grading)


class TestSubmitAttempt(unittest.TestCase):
    def test_full_correct_attempt(self):
        specs = [
            ExamQuestionSpec(1, "القاهرة", "MCQ", marks=2),
            ExamQuestionSpec(2, "صح", "TRUE_FALSE", marks=1),
        ]
        answers = [StudentAnswer(1, "القاهرة"), StudentAnswer(2, "صح")]
        result = submit_attempt(specs, answers)
        self.assertEqual(result.score, 3)
        self.assertEqual(result.total_marks, 3)
        self.assertEqual(result.percentage, 100.0)
        self.assertEqual(result.correct_count, 2)
        self.assertEqual(result.wrong_count, 0)

    def test_partial_attempt_with_missing_answer(self):
        specs = [
            ExamQuestionSpec(1, "القاهرة", "MCQ", marks=1),
            ExamQuestionSpec(2, "صح", "TRUE_FALSE", marks=1),
        ]
        answers = [StudentAnswer(1, "القاهرة")]  # لم يُجب على السؤال الثاني إطلاقًا
        result = submit_attempt(specs, answers)
        self.assertEqual(result.score, 1)
        self.assertEqual(result.total_marks, 2)
        self.assertEqual(result.percentage, 50.0)
        self.assertEqual(result.wrong_count, 1)

    def test_zero_total_marks_does_not_divide_by_zero(self):
        result = submit_attempt([], [])
        self.assertEqual(result.percentage, 0.0)

    def test_manual_grading_count_reported(self):
        specs = [ExamQuestionSpec(1, "أي شيء", "ESSAY", marks=5)]
        answers = [StudentAnswer(1, "مقال الطالب")]
        result = submit_attempt(specs, answers)
        self.assertEqual(result.needs_manual_grading_count, 1)
        self.assertEqual(result.score, 0)  # لم تُحتسب الدرجة حتى يراجعها معلم بشري


if __name__ == "__main__":
    unittest.main(verbosity=2)
