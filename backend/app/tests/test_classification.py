import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.classification import classify, NEEDS_CLASSIFICATION_THRESHOLD  # noqa: E402


class TestClassification(unittest.TestCase):
    def test_true_false_pattern(self):
        r = classify("ضع علامة صح أو خطأ أمام العبارة التالية: النيل أطول أنهار العالم")
        self.assertEqual(r.canonical_type, "TRUE_FALSE")
        self.assertFalse(r.needs_classification)

    def test_who_is_pattern(self):
        r = classify("من هو مؤسس الدولة الحديثة في مصر؟")
        self.assertEqual(r.canonical_type, "WHO_IS")

    def test_why_pattern(self):
        r = classify("بم تفسر أهمية نهر النيل بالنسبة لقدماء المصريين؟")
        self.assertEqual(r.canonical_type, "WHY")

    def test_map_pattern(self):
        r = classify("حدد على الخريطة موقع قارة إفريقيا")
        self.assertEqual(r.canonical_type, "MAP")

    def test_unrecognized_text_needs_classification(self):
        r = classify("نص غامض تمامًا لا يشبه أي نمط معروف 12345")
        self.assertEqual(r.canonical_type, "OTHER")
        self.assertTrue(r.needs_classification)
        self.assertLess(r.confidence, NEEDS_CLASSIFICATION_THRESHOLD)

    def test_explicit_legacy_hint_overrides_text_pattern_with_full_confidence(self):
        # النص نفسه غامض، لكن عمود "النوع" في ملف Excel صريح — يجب الثقة به كليًا
        r = classify("نص أي سؤال هنا", hinted_original_type="اختيار من متعدد")
        self.assertEqual(r.canonical_type, "MCQ")
        self.assertEqual(r.confidence, 1.0)
        self.assertFalse(r.needs_classification)
        self.assertEqual(r.original_question_type, "اختيار من متعدد")

    def test_unknown_legacy_hint_falls_back_to_text_analysis(self):
        r = classify("من هو أحمد عرابي؟", hinted_original_type="نوع غريب غير معروف")
        self.assertEqual(r.canonical_type, "WHO_IS")  # اعتمد على تحليل النص لأن الـhint غير معروف

    def test_original_question_type_always_preserved_in_result(self):
        r = classify("أي نص", hinted_original_type="نوع قديم كما كتبه المعلم")
        self.assertEqual(r.original_question_type, "نوع قديم كما كتبه المعلم")


if __name__ == "__main__":
    unittest.main(verbosity=2)
