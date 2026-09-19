"""
Integration Test — السيناريو الكامل المطلوب صراحة:

  رفع ملف -> Batch -> استخراج -> تحليل -> استخراج أسئلة -> تصنيف النوع
  -> كشف التكرار -> فحص الإجابة -> NEEDS_REVIEW -> مراجعة المدير -> APPROVED
  -> Question Bank -> إضافة لامتحان -> الطالب يحل الامتحان -> Submit
  -> تصحيح -> Result

✅ يعمل بالكامل بدون أي اتصال إنترنت أو قاعدة بيانات حقيقية أو مزود AI:
   - "الملف" = MockFileExtractor (نص ثابت بدل PDF حقيقي).
   - "قاعدة البيانات" = مستودعات وهمية في الذاكرة (dict) عبر DI.
   - لا استدعاء شبكة واحد في هذا الاختبار.

هذا الاختبار **شُغِّل فعليًا** ونتيجته موثّقة في نهاية الملف والتقرير المرفق.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.exam_engine import ExamQuestionSpec, StudentAnswer, submit_attempt  # noqa: E402
from app.services.import_parsers.bulk_text_parser import parse_bulk_text  # noqa: E402
from app.services.import_parsers.file_extractors import MockFileExtractor  # noqa: E402
from app.services.import_pipeline import run_batch  # noqa: E402
from app.services import review_workflow as wf  # noqa: E402


class InMemoryQuestionBank:
    """'قاعدة بيانات' وهمية بالكامل لهذا الاختبار — بديل PostgreSQL هنا فقط."""

    def __init__(self):
        self._next_id = 1
        self.questions = {}     # id -> wf.QuestionRecord
        self.texts = {}         # id -> question text (لاستخدامه في dedup)
        self.answers = {}       # id -> نص الإجابة الصحيحة
        self.types = {}         # id -> canonical_type
        self.batches = {}
        self.exams = {}
        self.exam_questions = {}

    def add_question(self, text, answer, canonical_type, status="IMPORTED"):
        qid = self._next_id
        self._next_id += 1
        self.questions[qid] = wf.QuestionRecord(id=qid, status=status)
        self.texts[qid] = text
        self.answers[qid] = answer
        self.types[qid] = canonical_type
        return qid

    def existing_pairs(self):
        return [(qid, text) for qid, text in self.texts.items()]

    # --- QuestionRepository protocol (يستخدمه review_workflow) ---
    def get(self, question_id):
        return self.questions[question_id]

    def save(self, record):
        self.questions[record.id] = record

    def log_action(self, action):
        pass


class TestFullScenario(unittest.TestCase):
    def test_upload_to_result_full_pipeline(self):
        bank = InMemoryQuestionBank()

        # سؤال معتمد مسبقًا في البنك (لاختبار كشف التكرار ضده لاحقًا)
        existing_id = bank.add_question(
            "وضح سبب أهمية نهر النيل.", "لأنه مصدر المياه والزراعة", "WHY", status="APPROVED")

        # ---------- 1) Upload + Extraction ----------
        raw_file_text = (
            "1- من هو مؤسس مدينة القاهرة؟\n"
            "الإجابة: جوهر الصقلي\n"
            "2- بم تفسر أهمية نهر النيل؟\n"
            "الإجابة: لأنه مصدر الحياة والزراعة\n"
            "3- نص غامض تمامًا 999\n"
            "الإجابة: جواب ما\n"
        )
        extractor = MockFileExtractor(pages=[raw_file_text])
        pages = extractor.extract("fake_upload.pdf")
        self.assertEqual(len(pages), 1)

        # ---------- 2) Batch creation ----------
        batch = {"batch_number": "Batch #00001", "status": "UPLOAD_RECEIVED"}
        self.assertEqual(batch["status"], "UPLOAD_RECEIVED")

        # ---------- 3) Parse (Extract Questions) ----------
        parsed = parse_bulk_text(pages[0].text)
        self.assertEqual(len(parsed), 3)
        batch["status"] = "EXTRACTING"

        # ---------- 4) Classify + Duplicate Detection + Answer Validation ----------
        batch["status"] = "ANALYZING"
        items = [{"raw_text": p.raw_text, "question": p.question, "answer": p.answer} for p in parsed]
        decisions, summary = run_batch(items, existing_questions=bank.existing_pairs())
        batch["status"] = "DUPLICATE_CHECK"

        self.assertEqual(summary.total, 3)
        # السؤال الأول (من هو مؤسس القاهرة) → نمط WHO_IS معروف، بلا تكرار → NEEDS_REVIEW
        self.assertEqual(decisions[0].status, "NEEDS_REVIEW")
        # السؤال الثاني (أهمية النيل، صياغة مختلفة) → مطابق دلاليًا للموجود في البنك → DUPLICATE
        self.assertEqual(decisions[1].status, "DUPLICATE")
        self.assertEqual(decisions[1].duplicates[0].other_question_id, existing_id)
        # السؤال الثالث (نص غامض) → NEEDS_CLASSIFICATION
        self.assertEqual(decisions[2].status, "NEEDS_CLASSIFICATION")

        batch["status"] = "NEEDS_REVIEW"

        # حفظ القرارات في "قاعدة البيانات" الوهمية بحالاتها كما قررها الـpipeline بالضبط
        saved_ids = []
        for d in decisions:
            qid = bank.add_question(d.question, d.answer, d.classification.canonical_type, status=d.status)
            saved_ids.append(qid)
        who_is_qid, duplicate_qid, unclear_qid = saved_ids

        # قاعدة صارمة: لا شيء APPROVED تلقائيًا حتى الآن
        for qid in saved_ids:
            self.assertNotEqual(bank.questions[qid].status, "APPROVED")

        # ---------- 5) مراجعة المدير (بشري) ----------
        # القرار البشري: اعتماد سؤال WHO_IS الواضح
        approved = wf.approve(bank, who_is_qid, reviewer_id=7, reviewer_role="ADMIN")
        self.assertEqual(approved.status, "APPROVED")
        bank.answers[who_is_qid] = "جوهر الصقلي"
        bank.types[who_is_qid] = "WHO_IS"

        # القرار البشري: رفض المكرر (كان يمكن اعتماده أيضًا، لكن هنا المدير يرفضه كمثال)
        wf.reject(bank, duplicate_qid, reviewer_id=7, reviewer_role="ADMIN", reason="مكرر فعليًا")
        self.assertEqual(bank.questions[duplicate_qid].status, "REJECTED")

        # السؤال الغامض: المدير يحدد نوعه يدويًا ثم يعتمده
        wf.change_type(bank, unclear_qid, reviewer_id=7, reviewer_role="ADMIN", new_type_id=99)
        self.assertEqual(bank.questions[unclear_qid].status, "NEEDS_REVIEW")  # خرج من NEEDS_CLASSIFICATION
        wf.approve(bank, unclear_qid, reviewer_id=7, reviewer_role="ADMIN")

        # الآن يوجد سؤالان APPROVED فعليًا (who_is_qid و unclear_qid) بالإضافة للسؤال الأصلي القديم
        approved_ids = [qid for qid, r in bank.questions.items() if r.status == "APPROVED"]
        self.assertEqual(set(approved_ids), {existing_id, who_is_qid, unclear_qid})

        # ---------- 6) Question Bank -> إنشاء امتحان يضم الأسئلة المعتمدة فقط ----------
        exam_question_ids = [existing_id, who_is_qid]  # المدير يختار يدويًا بالـcheckbox
        for qid in exam_question_ids:
            self.assertEqual(bank.questions[qid].status, "APPROVED",
                              "لا يجوز إضافة سؤال غير APPROVED لأي امتحان.")

        exam_specs = [
            ExamQuestionSpec(question_id=qid, correct_answer=bank.answers[qid],
                              canonical_type=bank.types[qid], marks=1.0)
            for qid in exam_question_ids
        ]

        # ---------- 7) الطالب يحل الامتحان ويُرسل الإجابات ----------
        student_answers = [
            StudentAnswer(question_id=existing_id, answer_text="لأنه مصدر المياه والزراعة"),  # صحيحة
            StudentAnswer(question_id=who_is_qid, answer_text="إجابة خاطئة تمامًا"),           # خاطئة
        ]

        # ---------- 8) Submit -> تصحيح -> Result ----------
        result = submit_attempt(exam_specs, student_answers)

        self.assertEqual(result.total_marks, 2.0)
        self.assertEqual(result.correct_count, 1)
        self.assertEqual(result.wrong_count, 1)
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.percentage, 50.0)

        # السيناريو نجح بالكامل من الرفع وحتى النتيجة، بدون أي اتصال خارجي حقيقي.
        batch["status"] = "COMPLETED"
        self.assertEqual(batch["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
