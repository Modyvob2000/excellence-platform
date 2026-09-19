import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.import_pipeline import process_import_item, run_batch, validate_answer  # noqa: E402


class TestValidateAnswer(unittest.TestCase):
    def test_empty_or_none_invalid(self):
        self.assertFalse(validate_answer(None))
        self.assertFalse(validate_answer(""))
        self.assertFalse(validate_answer("   "))

    def test_present_answer_valid(self):
        self.assertTrue(validate_answer("القاهرة"))


class TestProcessImportItem(unittest.TestCase):
    def test_clear_question_with_answer_goes_to_needs_review(self):
        decision = process_import_item(
            raw_text="1- من هو أحمد عرابي؟\nج: قائد عسكري مصري",
            question_text="من هو أحمد عرابي؟", answer="قائد عسكري مصري",
            existing_questions=[],
        )
        self.assertEqual(decision.status, "NEEDS_REVIEW")
        self.assertFalse(decision.answer_flagged)
        self.assertEqual(decision.classification.canonical_type, "WHO_IS")

    def test_missing_answer_is_flagged_but_not_invented(self):
        decision = process_import_item(
            raw_text="سؤال بلا إجابة", question_text="من هو أحمد عرابي؟", answer=None,
            existing_questions=[],
        )
        self.assertTrue(decision.answer_flagged)
        self.assertIsNone(decision.answer)  # لم يُخترع أي جواب

    def test_duplicate_detected_against_existing_bank(self):
        decision = process_import_item(
            raw_text="", question_text="بم تفسر أهمية نهر النيل؟", answer="لأنه مصدر الحياة",
            existing_questions=[(1, "وضح سبب أهمية نهر النيل.")],
        )
        self.assertEqual(decision.status, "DUPLICATE")
        self.assertEqual(len(decision.duplicates), 1)

    def test_unrecognized_type_goes_to_needs_classification(self):
        decision = process_import_item(
            raw_text="", question_text="نص غامض لا يطابق أي نمط 999", answer="جواب ما",
            existing_questions=[],
        )
        self.assertEqual(decision.status, "NEEDS_CLASSIFICATION")

    def test_duplicate_takes_priority_over_needs_classification(self):
        # سؤال بصياغة غامضة (NEEDS_CLASSIFICATION) لكنه أيضًا مطابق حرفيًا لموجود
        decision = process_import_item(
            raw_text="", question_text="نص غامض 123", answer="جواب",
            existing_questions=[(1, "نص غامض 123")],
        )
        self.assertEqual(decision.status, "DUPLICATE")

    def test_never_returns_approved(self):
        for q, a, existing in [
            ("سؤال واضح جدًا: من هو محمد علي؟", "حاكم مصر", []),
            ("نص غامض", None, []),
            ("سؤال مكرر", "جواب", [(1, "سؤال مكرر")]),
        ]:
            decision = process_import_item("", q, a, existing)
            self.assertNotEqual(decision.status, "APPROVED",
                                 "خط الأنابيب يجب ألا يعتمد أي سؤال تلقائيًا أبدًا.")


class TestRunBatch(unittest.TestCase):
    def test_batch_summary_counts_match_decisions(self):
        items = [
            {"raw_text": "", "question": "من هو أحمد عرابي؟", "answer": "قائد"},
            {"raw_text": "", "question": "نص غامض 42", "answer": "شيء"},
            {"raw_text": "", "question": "بم تفسر أهمية نهر النيل؟", "answer": "مهم"},
        ]
        existing = [(1, "وضح سبب أهمية نهر النيل.")]
        decisions, summary = run_batch(items, existing)
        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.needs_review, 1)
        self.assertEqual(summary.needs_classification, 1)
        self.assertEqual(summary.duplicate, 1)
        self.assertEqual(len(decisions), 3)

    def test_internal_batch_duplicates_detected_between_items_of_same_file(self):
        # نفس السؤال مكرر مرتين داخل نفس ملف الاستيراد (بدون أي وجود مسبق في البنك)
        items = [
            {"raw_text": "", "question": "من هو مؤسس مدينة القاهرة؟", "answer": "جوهر الصقلي"},
            {"raw_text": "", "question": "من هو مؤسس مدينة القاهرة؟", "answer": "جوهر الصقلي"},
        ]
        decisions, summary = run_batch(items, existing_questions=[])
        self.assertEqual(decisions[0].status, "NEEDS_REVIEW")   # أول ظهور: لا تكرار بعد، ونمط WHO_IS معروف
        self.assertEqual(decisions[1].status, "DUPLICATE")      # ثاني ظهور: مكرر لسابقه بنفس الدفعة
        self.assertEqual(summary.duplicate, 1)

    def test_empty_batch(self):
        decisions, summary = run_batch([], existing_questions=[])
        self.assertEqual(decisions, [])
        self.assertEqual(summary.total, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
