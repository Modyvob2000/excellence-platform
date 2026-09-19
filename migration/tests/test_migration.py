#!/usr/bin/env python3
"""
اختبارات حقيقية قابلة للتشغيل لسكربت الترحيل (stdlib فقط، لا تحتاج تثبيت أي حزمة).

التشغيل:
    python3 -m unittest migration.tests.test_migration -v
أو مباشرة:
    python3 migration/tests/test_migration.py
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
MIGRATION_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, MIGRATION_DIR)
import migrate  # noqa: E402

SOURCE_DB = os.environ.get(
    "EDUCATION_DB_PATH",
    os.path.join(MIGRATION_DIR, "source_copy", "education.db"),
)


@unittest.skipUnless(os.path.exists(SOURCE_DB), f"education.db غير موجود في {SOURCE_DB}")
class TestMigration(unittest.TestCase):
    """اختبارات Migration: row counts, foreign keys, orphan records, data integrity."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="migration_test_")
        cls.src_checksum_before = cls._checksum(SOURCE_DB)
        cls.ok = migrate.migrate(SOURCE_DB, cls.tmpdir)
        cls.dst_path = os.path.join(cls.tmpdir, "education_normalized.db")
        cls.src_checksum_after = cls._checksum(SOURCE_DB)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    @staticmethod
    def _checksum(path):
        import hashlib
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _src(self):
        c = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        return c

    def _dst(self):
        c = sqlite3.connect(self.dst_path)
        c.row_factory = sqlite3.Row
        return c

    # 1) الأصل لم يُعدَّل إطلاقًا (أهم قاعدة في المشروع)
    def test_source_file_untouched(self):
        self.assertEqual(self.src_checksum_before, self.src_checksum_after,
                          "تم تعديل education.db الأصلية أثناء الترحيل! هذا يخالف القاعدة الإلزامية.")

    # 2) الترحيل نجح والفحوصات الداخلية مرت
    def test_migration_reported_success(self):
        self.assertTrue(self.ok, "migrate() أبلغ عن فشل أحد فحوصات السلامة الداخلية.")

    # 3) row counts: لا فقد لأي محتوى تعليمي أساسي
    def test_row_counts_preserved(self):
        src, dst = self._src(), self._dst()
        for table in ["grades", "units", "lessons", "questions", "ai_answers"]:
            with self.subTest(table=table):
                src_count = src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                dst_count = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                self.assertEqual(src_count, dst_count, f"فقد بيانات في {table}")

    # 4) subjects: الأصلية محفوظة + مادة جديدة واحدة مُضافة وموثقة
    def test_subjects_original_preserved_plus_one_new(self):
        src, dst = self._src(), self._dst()
        src_count = src.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        dst_count = dst.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        self.assertEqual(dst_count, src_count + 1)
        names = [r[0] for r in dst.execute("SELECT name FROM subjects")]
        self.assertIn("الدراسات الاجتماعية", names)

    # 5) لا orphan records في الجداول الجديدة (كل FK مربوط فعليًا)
    def test_no_orphan_units(self):
        dst = self._dst()
        n = dst.execute("SELECT COUNT(*) FROM units WHERE subject_id IS NULL").fetchone()[0]
        self.assertEqual(n, 0)

    def test_no_orphan_lessons(self):
        dst = self._dst()
        n = dst.execute("SELECT COUNT(*) FROM lessons WHERE unit_id IS NULL").fetchone()[0]
        self.assertEqual(n, 0)

    def test_no_orphan_questions(self):
        dst = self._dst()
        n = dst.execute(
            "SELECT COUNT(*) FROM questions q LEFT JOIN lessons l ON q.lesson_id=l.id "
            "WHERE l.id IS NULL").fetchone()[0]
        self.assertEqual(n, 0)

    # 6) لا سؤال بلا تصنيف نوع
    def test_all_questions_classified(self):
        dst = self._dst()
        n = dst.execute("SELECT COUNT(*) FROM questions WHERE question_type_id IS NULL").fetchone()[0]
        self.assertEqual(n, 0)

    # 7) original_question_type محفوظ حرفيًا كما طُلب صراحة
    def test_original_question_type_preserved(self):
        src, dst = self._src(), self._dst()
        src_rows = {r["id"]: r["question_type"] for r in src.execute("SELECT id,question_type FROM questions")}
        dst_rows = {r["id"]: r["original_question_type"]
                    for r in dst.execute("SELECT id,original_question_type FROM questions")}
        self.assertEqual(src_rows, dst_rows)

    # 8) الأنواع المطلوبة في المواصفات وغير الموجودة بالبيانات أُضيفت كأنواع متاحة
    def test_extra_required_question_types_exist(self):
        dst = self._dst()
        codes = {r[0] for r in dst.execute("SELECT code FROM question_types")}
        for code, _name in migrate.EXTRA_QUESTION_TYPES:
            self.assertIn(code, codes)

    # 9) لا اعتماد تلقائي: approved تُنقل كما هي حرفيًا، لا يُغيَّرها الترحيل أبدًا
    def test_approved_flag_not_altered(self):
        src, dst = self._src(), self._dst()
        src_rows = {r["id"]: r["approved"] for r in src.execute("SELECT id,approved FROM questions")}
        dst_rows = {r["id"]: r["approved"] for r in dst.execute("SELECT id,approved FROM questions")}
        self.assertEqual(src_rows, dst_rows)

    # 10) الروابط المكسورة أصلاً في المصدر (exam_questions/fixed_exam_questions) موثّقة بالكامل
    #     في migration_notes ومحفوظة في النسخة الاحتياطية JSON، وليست مفقودة بصمت
    def test_dangling_links_fully_documented(self):
        dst = self._dst()
        src = self._src()
        src_links = (src.execute("SELECT COUNT(*) FROM exam_questions").fetchone()[0]
                     + src.execute("SELECT COUNT(*) FROM fixed_exam_questions").fetchone()[0])
        dst_links = dst.execute("SELECT COUNT(*) FROM exam_questions").fetchone()[0]
        documented = dst.execute(
            "SELECT COUNT(*) FROM migration_notes WHERE note LIKE '%مرجع مكسور%'").fetchone()[0]
        self.assertEqual(src_links - dst_links, documented,
                          "يوجد فارق في عدد روابط الامتحانات غير مُفسَّر بملاحظة موثقة.")

    # 11) لا حذف نهائي: كل الجداول الأصلية موجودة كاملة في النسخة الاحتياطية JSON
    def test_json_backup_contains_every_table(self):
        import glob
        import json
        backups = glob.glob(os.path.join(self.tmpdir, "backups", "*.json"))
        self.assertTrue(backups, "لم يتم إنشاء أي نسخة احتياطية JSON.")
        with open(backups[0], encoding="utf-8") as f:
            data = json.load(f)
        for t in migrate.SOURCE_TABLES:
            self.assertIn(t, data)
        # عدد صفوف questions في النسخة الاحتياطية = عدد صفوف questions في المصدر
        src = self._src()
        self.assertEqual(len(data["questions"]),
                          src.execute("SELECT COUNT(*) FROM questions").fetchone()[0])

    # 12) الترحيل Idempotent: تشغيله مرتين متتاليتين يعطي نفس النتائج بالضبط
    def test_migration_is_idempotent(self):
        tmp2 = tempfile.mkdtemp(prefix="migration_test2_")
        try:
            migrate.migrate(SOURCE_DB, tmp2)
            dst2 = sqlite3.connect(os.path.join(tmp2, "education_normalized.db"))
            dst1 = self._dst()
            for table in ["grades", "units", "lessons", "questions", "subjects", "exams",
                          "exam_questions", "question_types"]:
                c1 = dst1.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                c2 = dst2.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                self.assertEqual(c1, c2, f"نتيجة غير ثابتة (non-idempotent) في {table}")
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
