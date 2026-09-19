import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.audit_service import AuditEntry, entity_history, record, search_logs  # noqa: E402


class FakeAuditStore:
    def __init__(self):
        self._next_id = 1
        self._entries = []

    def insert(self, entry: AuditEntry) -> int:
        eid = self._next_id
        self._next_id += 1
        entry.id = eid
        self._entries.append(entry)
        return eid

    def query(self, user_id=None, action=None, entity=None, entity_id=None,
              result=None, since=None, until=None):
        results = self._entries
        if user_id is not None:
            results = [e for e in results if e.user_id == user_id]
        if action is not None:
            results = [e for e in results if e.action == action]
        if entity is not None:
            results = [e for e in results if e.entity == entity]
        if entity_id is not None:
            results = [e for e in results if e.entity_id == entity_id]
        if result is not None:
            results = [e for e in results if e.result == result]
        if since is not None:
            results = [e for e in results if e.created_at >= since]
        if until is not None:
            results = [e for e in results if e.created_at <= until]
        return results


class TestRecord(unittest.TestCase):
    def test_record_captures_all_fields(self):
        store = FakeAuditStore()
        entry = record(store, user_id=7, action="APPROVE", entity="question", entity_id=42,
                        reviewer_note="جيد")
        self.assertEqual(entry.user_id, 7)
        self.assertEqual(entry.action, "APPROVE")
        self.assertEqual(entry.entity, "question")
        self.assertEqual(entry.entity_id, 42)
        self.assertEqual(entry.result, "success")
        self.assertEqual(entry.details["reviewer_note"], "جيد")
        self.assertIsNotNone(entry.id)

    def test_record_failure_result(self):
        store = FakeAuditStore()
        entry = record(store, user_id=1, action="LOGIN", entity="user", entity_id=1,
                        result="failure", reason="كلمة مرور خاطئة")
        self.assertEqual(entry.result, "failure")


class TestSearchLogs(unittest.TestCase):
    def setUp(self):
        self.store = FakeAuditStore()
        record(self.store, 1, "APPROVE", "question", 10)
        record(self.store, 2, "REJECT", "question", 11)
        record(self.store, 1, "CHANGE_ROLE", "user", 5)

    def test_filter_by_user(self):
        results = search_logs(self.store, user_id=1)
        self.assertEqual(len(results), 2)

    def test_filter_by_action(self):
        results = search_logs(self.store, action="REJECT")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].entity_id, 11)

    def test_filter_by_entity(self):
        results = search_logs(self.store, entity="user")
        self.assertEqual(len(results), 1)

    def test_combined_filters(self):
        results = search_logs(self.store, user_id=1, entity="question")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].action, "APPROVE")

    def test_results_sorted_newest_first(self):
        results = search_logs(self.store)
        timestamps = [r.created_at for r in results]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_date_range_filter(self):
        store = FakeAuditStore()
        now = datetime.now()
        old_entry = record(store, 1, "APPROVE", "question", 1)
        old_entry.created_at = now - timedelta(days=10)
        recent_entry = record(store, 1, "APPROVE", "question", 2)
        recent_entry.created_at = now
        results = search_logs(store, since=now - timedelta(days=1))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].entity_id, 2)


class TestEntityHistory(unittest.TestCase):
    def test_history_for_specific_question_chronological(self):
        store = FakeAuditStore()
        record(store, 1, "CREATE", "question", 99)
        record(store, 2, "APPROVE", "question", 99)
        record(store, 3, "REJECT", "question", 100)  # سؤال مختلف
        history = entity_history(store, "question", 99)
        self.assertEqual(len(history), 2)
        self.assertEqual([h.action for h in history], ["CREATE", "APPROVE"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
