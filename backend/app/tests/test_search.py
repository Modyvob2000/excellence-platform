import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.search import rank_by_relevance  # noqa: E402


class TestSmartSearch(unittest.TestCase):
    def test_exact_keyword_match_ranks_highest(self):
        candidates = [
            (1, "أهمية نهر النيل في حياة قدماء المصريين"),
            (2, "موقع قارة إفريقيا والكشوف الجغرافية"),
        ]
        results = rank_by_relevance("نهر النيل", candidates)
        self.assertEqual(results[0][0], 1)

    def test_semantic_style_query_finds_related_content_without_literal_match(self):
        # المثال الحرفي من طلب المستخدم: "أسئلة أسباب قيام الحضارات القديمة"
        candidates = [
            (1, "لماذا نشأت الحضارة المصرية القديمة على ضفاف النيل"),
            (2, "قواعد اللغة الإنجليزية للمبتدئين"),
        ]
        results = rank_by_relevance("أسباب قيام الحضارات القديمة", candidates)
        result_ids = [r[0] for r in results]
        self.assertIn(1, result_ids)
        self.assertNotIn(2, result_ids)

    def test_empty_query_returns_empty(self):
        self.assertEqual(rank_by_relevance("", [(1, "أي نص")]), [])

    def test_limit_respected(self):
        candidates = [(i, "نص متكرر عن نهر النيل") for i in range(50)]
        results = rank_by_relevance("نهر النيل", candidates, limit=5)
        self.assertLessEqual(len(results), 5)

    def test_results_sorted_descending(self):
        candidates = [(1, "نهر النيل مهم جدًا جدًا"), (2, "شيء آخر تمامًا لا علاقة له")]
        results = rank_by_relevance("نهر النيل", candidates)
        scores = [s for _, s in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_unrelated_query_returns_no_results(self):
        candidates = [(1, "درس عن الكيمياء العضوية")]
        results = rank_by_relevance("كرة القدم في أوروبا", candidates)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
