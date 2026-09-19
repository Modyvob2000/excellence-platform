import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.dedup import (  # noqa: E402
    DuplicateMatch, LocalTextSimilarityBackend, find_duplicates, normalize_text, tokenize,
)


class TestNormalizeText(unittest.TestCase):
    def test_removes_diacritics(self):
        self.assertEqual(normalize_text("الدَّرْسُ الأَوَّل"), normalize_text("الدرس الاول"))

    def test_unifies_alef_variants(self):
        self.assertEqual(normalize_text("أهمية إنشاء آثار"), normalize_text("اهميه انشاء اثار"))

    def test_strips_punctuation(self):
        self.assertEqual(normalize_text("ما هو نهر النيل؟!"), normalize_text("ما هو نهر النيل"))

    def test_empty_and_none_safe(self):
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")


class TestExactDuplicate(unittest.TestCase):
    def test_identical_text_is_exact_duplicate(self):
        existing = [(101, "ما هي عاصمة مصر؟")]
        result = find_duplicates("ما هي عاصمة مصر؟", existing)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].kind, "exact")
        self.assertEqual(result[0].similarity, 1.0)

    def test_diacritics_only_difference_is_still_exact(self):
        existing = [(101, "بِمَ تُفَسِّر أهمية نهر النيل؟")]
        result = find_duplicates("بم تفسر أهمية نهر النيل؟", existing)
        self.assertEqual(result[0].kind, "exact")

    def test_completely_different_text_no_match(self):
        existing = [(101, "متى بدأت الحرب العالمية الثانية؟")]
        result = find_duplicates("ما عاصمة اليابان؟", existing)
        self.assertEqual(result, [])


class TestSemanticDuplicate(unittest.TestCase):
    def test_user_example_rephrased_question_detected(self):
        # المثال الحرفي من طلب المستخدم:
        # "بم تفسر أهمية نهر النيل؟" و"وضح سبب أهمية نهر النيل." يجب اعتبارهما محتملَي التكرار
        existing = [(55, "بم تفسر أهمية نهر النيل؟")]
        result = find_duplicates("وضح سبب أهمية نهر النيل.", existing)
        self.assertEqual(len(result), 1, "لم يتم اكتشاف التشابه الدلالي بين الصياغتين")
        self.assertEqual(result[0].kind, "semantic")
        self.assertGreater(result[0].similarity, 0.5)

    def test_unrelated_question_not_flagged(self):
        existing = [(1, "ما سبب أهمية نهر النيل؟")]
        result = find_duplicates("كم عدد سكان القاهرة؟", existing)
        self.assertEqual(result, [])

    def test_never_deletes_or_mutates_input(self):
        existing = [(1, "سؤال أصلي"), (2, "سؤال أصلي")]
        before = list(existing)
        find_duplicates("سؤال أصلي", existing)
        self.assertEqual(existing, before, "الدالة يجب ألا تعدّل قائمة الأسئلة الموجودة إطلاقًا")

    def test_results_sorted_descending_by_similarity(self):
        existing = [
            (1, "ما هي عاصمة مصر الحالية؟"),
            (2, "ما هي عاصمة مصر؟"),
        ]
        result = find_duplicates("ما هي عاصمة مصر؟", existing, threshold=0.3)
        self.assertGreaterEqual(len(result), 1)
        sims = [m.similarity for m in result]
        self.assertEqual(sims, sorted(sims, reverse=True))

    def test_threshold_is_configurable(self):
        existing = [(1, "درس عن نهر النيل وأهميته")]
        candidate = "معلومات حول أهمية النيل"
        strict = find_duplicates(candidate, existing, threshold=0.99)
        loose = find_duplicates(candidate, existing, threshold=0.1)
        self.assertEqual(strict, [])
        self.assertGreaterEqual(len(loose), 1)


class TestTokenize(unittest.TestCase):
    def test_tokenize_splits_and_normalizes(self):
        self.assertEqual(tokenize("الدرس الأول"), ["الدرس", "الاول"])


class TestLocalBackendDirectly(unittest.TestCase):
    def test_identical_strings_similarity_one(self):
        backend = LocalTextSimilarityBackend()
        self.assertEqual(backend.similarity("نص واحد", "نص واحد"), 1.0)

    def test_empty_string_similarity_zero(self):
        backend = LocalTextSimilarityBackend()
        self.assertEqual(backend.similarity("", "أي نص"), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
