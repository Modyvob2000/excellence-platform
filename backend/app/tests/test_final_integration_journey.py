"""
Integration Test النهائي — الرحلة الكاملة المطلوبة صراحة:

  Login -> Content -> Import -> Extraction -> Classification -> Deduplication
  -> Review -> Approval -> Question Bank -> Exam Creation -> Student Attempt
  -> Result -> Admin Review -> Audit Log

✅ يعمل بالكامل بدون أي اتصال إنترنت أو قاعدة بيانات حقيقية: كل خطوة تستخدم
الوحدة المُختبرة فعليًا في ملفها الخاص (auth_core, import_pipeline,
review_workflow, exam_engine, audit_service) — هذا الاختبار يُثبت أنها تعمل
معًا بشكل صحيح كسيناريو واحد متصل، وليس فقط منفردة.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app import auth_core  # noqa: E402
from app.services import review_workflow as wf  # noqa: E402
from app.services.audit_service import entity_history, record, search_logs  # noqa: E402
from app.services.exam_engine import ExamQuestionSpec, StudentAnswer, submit_attempt  # noqa: E402
from app.services.import_parsers.bulk_text_parser import parse_bulk_text  # noqa: E402
from app.services.import_parsers.file_extractors import MockFileExtractor  # noqa: E402
from app.services.import_pipeline import run_batch  # noqa: E402


class InMemoryQuestionBank:
    def __init__(self):
        self._next_id = 1
        self.questions, self.texts, self.answers, self.types = {}, {}, {}, {}

    def add_question(self, text, answer, canonical_type, status="IMPORTED"):
        qid = self._next_id
        self._next_id += 1
        self.questions[qid] = wf.QuestionRecord(id=qid, status=status)
        self.texts[qid] = text
        self.answers[qid] = answer
        self.types[qid] = canonical_type
        return qid

    def existing_pairs(self):
        return list(self.texts.items())

    def get(self, question_id):
        return self.questions[question_id]

    def save(self, record_):
        self.questions[record_.id] = record_

    def log_action(self, action):
        pass


class InMemoryAuditStore:
    def __init__(self):
        self._next_id = 1
        self.entries = []

    def insert(self, entry):
        entry.id = self._next_id
        self._next_id += 1
        self.entries.append(entry)
        return entry.id

    def query(self, **filters):
        results = self.entries
        for key in ("user_id", "action", "entity", "entity_id", "result"):
            val = filters.get(key)
            if val is not None:
                results = [e for e in results if getattr(e, key) == val]
        return results


class TestFullJourneyIntegration(unittest.TestCase):
    def test_login_through_audit_log_full_journey(self):
        audit_store = InMemoryAuditStore()

        # ============ 1) Login (JWT + RBAC حقيقي عبر auth_core) ============
        os.environ["JWT_SECRET_KEY"] = "integration-test-secret"
        admin_password_hash = auth_core.hash_password("AdminPass123")
        self.assertTrue(auth_core.verify_password("AdminPass123", admin_password_hash))
        admin_token = auth_core.create_access_token(user_id=1, username="admin1", role="ADMIN",
                                                     secret_key=auth_core.get_secret_key())
        payload = auth_core.decode_access_token(admin_token, auth_core.get_secret_key())
        admin_id, admin_role = int(payload["sub"]), payload["role"]
        self.assertTrue(auth_core.can_manage_users(admin_role))
        record(audit_store, admin_id, "LOGIN", "user", admin_id)

        # ============ 2) Content (هيكل تعليمي مبسّط لهذا الاختبار) ============
        bank = InMemoryQuestionBank()
        lesson_id = 42  # يمثّل درسًا موجودًا فعليًا في الهيكل (grade->subject->unit->lesson)
        existing_id = bank.add_question("وضح سبب أهمية نهر النيل.", "لأنه مصدر الحياة", "WHY", status="APPROVED")

        # ============ 3) Import + Extraction (رفع ملف، استخراج نص فعلي منه) ============
        raw_text = (
            "1- من هو مؤسس مدينة القاهرة؟\n"
            "الإجابة: جوهر الصقلي\n"
            "2- بم تفسر أهمية نهر النيل؟\n"
            "الإجابة: لأنه مصدر الحياة\n"
        )
        pages = MockFileExtractor(pages=[raw_text]).extract("upload.pdf")
        parsed = parse_bulk_text(pages[0].text)
        self.assertEqual(len(parsed), 2)
        record(audit_store, admin_id, "IMPORT_BATCH", "import_batch", 1, total=len(parsed))

        # ============ 4) Classification + Deduplication (نفس المحرك، خطوة واحدة) ============
        items = [{"raw_text": p.raw_text, "question": p.question, "answer": p.answer} for p in parsed]
        decisions, summary = run_batch(items, existing_questions=bank.existing_pairs())
        self.assertEqual(decisions[0].status, "NEEDS_REVIEW")   # WHO_IS، بلا تكرار
        self.assertEqual(decisions[1].status, "DUPLICATE")      # مطابق دلاليًا للموجود مسبقًا
        for d in decisions:
            self.assertNotEqual(d.status, "APPROVED", "لا اعتماد تلقائي عند الاستيراد مهما كانت الحالة")

        saved_ids = [bank.add_question(d.question, d.answer, d.classification.canonical_type, status=d.status)
                     for d in decisions]
        who_is_id, duplicate_id = saved_ids

        # ============ 5) Review + Approval (قرار بشري فعلي عبر review_workflow المُختبر) ============
        wf.approve(bank, who_is_id, admin_id, admin_role)
        record(audit_store, admin_id, "APPROVE", "question", who_is_id)

        wf.reject(bank, duplicate_id, admin_id, admin_role, reason="مكرر بالفعل في البنك")
        record(audit_store, admin_id, "REJECT", "question", duplicate_id, reason="مكرر بالفعل في البنك")

        self.assertEqual(bank.questions[who_is_id].status, "APPROVED")
        self.assertEqual(bank.questions[duplicate_id].status, "REJECTED")

        # ============ 6) Question Bank -> Exam Creation (يدويًا بمعرفات محددة، أسئلة معتمدة فقط) ============
        exam_question_ids = [existing_id, who_is_id]
        for qid in exam_question_ids:
            self.assertEqual(bank.questions[qid].status, "APPROVED")
        exam_specs = [
            ExamQuestionSpec(question_id=qid, correct_answer=bank.answers[qid],
                              canonical_type=bank.types[qid], marks=1.0)
            for qid in exam_question_ids
        ]
        record(audit_store, admin_id, "CREATE_EXAM", "exam", 1, question_ids=exam_question_ids)

        # ============ 7) Student Attempt -> Result (نفس exam_engine المُختبر) ============
        student_answers = [
            StudentAnswer(existing_id, "لأنه مصدر الحياة"),   # صحيحة (تشابه قوي كافٍ)
            StudentAnswer(who_is_id, "إجابة خاطئة تمامًا"),    # خاطئة
        ]
        result = submit_attempt(exam_specs, student_answers)
        self.assertEqual(result.total_marks, 2.0)
        self.assertEqual(result.correct_count, 1)
        self.assertEqual(result.wrong_count, 1)
        self.assertEqual(result.percentage, 50.0)
        record(audit_store, admin_id, "STUDENT_ATTEMPT_SUBMITTED", "exam_attempt", 1, percentage=result.percentage)

        # ============ 8) Admin Review (مراجعة إدارية لاحقة: التراجع عن اعتماد ممكن دائمًا) ============
        wf.reject(bank, who_is_id, admin_id, admin_role, reason="مراجعة لاحقة: يحتاج توضيحًا إضافيًا")
        record(audit_store, admin_id, "REJECT", "question", who_is_id, reason="مراجعة إدارية لاحقة")
        self.assertEqual(bank.questions[who_is_id].status, "REJECTED")

        # ============ 9) Audit Log — كل خطوة حساسة مسجَّلة وقابلة للبحث والتتبع ============
        all_logs = search_logs(audit_store)
        self.assertEqual(len(all_logs), 7)  # LOGIN, IMPORT_BATCH, APPROVE, REJECT×2, CREATE_EXAM, ATTEMPT
        actions_logged = [e.action for e in all_logs]
        for expected in ("LOGIN", "IMPORT_BATCH", "APPROVE", "CREATE_EXAM", "STUDENT_ATTEMPT_SUBMITTED"):
            self.assertIn(expected, actions_logged)

        who_is_history = entity_history(audit_store, "question", who_is_id)
        self.assertEqual([h.action for h in who_is_history], ["APPROVE", "REJECT"])  # تسلسل زمني صحيح


if __name__ == "__main__":
    unittest.main(verbosity=2)
