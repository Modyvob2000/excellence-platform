import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.results_service import (  # noqa: E402
    AttemptSummary, build_exam_report, student_average_percentage, student_history,
)


def mk(attempt_id, exam_id, student_id, percentage, when=None):
    return AttemptSummary(
        attempt_id=attempt_id, exam_id=exam_id, student_id=student_id,
        score=percentage / 10, total_marks=10, percentage=percentage,
        correct_count=int(percentage // 10), wrong_count=10 - int(percentage // 10),
        submitted_at=when or datetime.now(),
    )


class TestStudentHistory(unittest.TestCase):
    def test_filters_by_student_and_sorts_newest_first(self):
        now = datetime.now()
        attempts = [
            mk(1, 10, 5, 60, when=now - timedelta(days=2)),
            mk(2, 11, 5, 80, when=now - timedelta(days=1)),
            mk(3, 10, 9, 40, when=now),  # طالب آخر
        ]
        history = student_history(attempts, student_id=5)
        self.assertEqual([a.attempt_id for a in history], [2, 1])

    def test_empty_history_for_unknown_student(self):
        self.assertEqual(student_history([mk(1, 1, 1, 50)], student_id=999), [])


class TestExamReport(unittest.TestCase):
    def test_report_aggregates_correctly(self):
        attempts = [mk(1, 100, 1, 90), mk(2, 100, 2, 40), mk(3, 100, 3, 60)]
        report = build_exam_report(attempts, exam_id=100)
        self.assertEqual(report.attempts_count, 3)
        self.assertAlmostEqual(report.average_percentage, (90 + 40 + 60) / 3, places=2)
        self.assertEqual(report.highest_percentage, 90)
        self.assertEqual(report.lowest_percentage, 40)
        self.assertAlmostEqual(report.pass_rate, 2 / 3 * 100, places=2)  # 90 و60 ناجحان، 40 راسب

    def test_report_for_exam_with_no_attempts(self):
        report = build_exam_report([], exam_id=999)
        self.assertEqual(report.attempts_count, 0)
        self.assertEqual(report.average_percentage, 0.0)

    def test_report_ignores_other_exams(self):
        attempts = [mk(1, 1, 1, 90), mk(2, 2, 1, 10)]
        report = build_exam_report(attempts, exam_id=1)
        self.assertEqual(report.attempts_count, 1)
        self.assertEqual(report.average_percentage, 90)


class TestStudentAverage(unittest.TestCase):
    def test_average_across_multiple_exams(self):
        attempts = [mk(1, 1, 5, 100), mk(2, 2, 5, 50)]
        self.assertEqual(student_average_percentage(attempts, student_id=5), 75.0)

    def test_zero_for_student_with_no_attempts(self):
        self.assertEqual(student_average_percentage([], student_id=5), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
