#!/usr/bin/env python3
"""
Migration script — منصة التميز التعليمية
==========================================
يقرأ education.db الأصلية (بدون أي تعديل عليها) وينشئ نسخة منظمة جديدة
education_normalized.db بنفس الـschema الذي سيستخدمه الـbackend (SQLAlchemy)
سواء على SQLite (تطوير) أو PostgreSQL (إنتاج).

الاستخدام:
    python3 migrate.py --source /path/to/education.db --outdir ./migration_output

لا يحذف أي شيء من الأصل. ينشئ أولاً نسخة احتياطية JSON كاملة، ثم يبني القاعدة
الجديدة من الصفر (idempotent) في كل تشغيل.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

SOURCE_TABLES = [
    "grades", "subjects", "units", "lessons", "questions", "question_bank",
    "exams", "exam_questions", "fixed_exams", "fixed_exam_questions",
    "results", "ai_answers",
]

# توحيد أنواع الأسئلة القديمة إلى أكواد ثابتة (انظر docs/DATA_AUDIT.md بند د)
QUESTION_TYPE_MAP = {
    "اختيار من متعدد": ("mcq", "اختيار من متعدد"),
    "اختياري": ("mcq", "اختيار من متعدد"),
    "أكمل": ("fill_blank", "أكمل"),
    "مصطلح": ("term", "مصطلح"),
    "من يكون": ("who_is", "من يكون"),
    "خريطة": ("map", "خريطة"),
    "صح وخطأ": ("true_false", "صح أو خطأ"),
    "صح وغلط": ("true_false", "صح أو خطأ"),
    "العلاقة بين": ("relation", "العلاقة بين"),
    "ماذا يحدث إذا": ("what_if", "ماذا يحدث إذا"),
}
# أنواع مطلوبة في المواصفات وغير موجودة بعد كبيانات فعلية — تُضاف كأنواع متاحة فارغة
EXTRA_QUESTION_TYPES = [
    ("explain_why", "بم تفسر"),
    ("short_answer", "أسئلة قصيرة"),
    ("essay", "أسئلة مقالية"),
]

DUPLICATE_GRADE_NAME_CANONICAL_ID = 1  # "الصف الأول الإعدادي" (بالهمزة) هو المرجع الرسمي
DUPLICATE_GRADE_IDS = {4, 6}           # نفس الصف بإملاء/تكرار مختلف -> تُخفى لا تُحذف

NEW_SUBJECT_NAME = "الدراسات الاجتماعية"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def backup_source_as_json(src_conn, backup_path):
    data = {}
    for t in SOURCE_TABLES:
        try:
            cur = src_conn.execute(f"SELECT * FROM {t}")
            cols = [d[0] for d in cur.description]
            data[t] = [dict(zip(cols, row)) for row in cur.fetchall()]
        except sqlite3.OperationalError:
            data[t] = []
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {t: len(v) for t, v in data.items()}


def build_schema(dst):
    dst.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE roles (
        id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL
    );

    CREATE TABLE users (
        id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, full_name TEXT, role_id INTEGER NOT NULL,
        is_active INTEGER DEFAULT 1, created_at TEXT,
        FOREIGN KEY(role_id) REFERENCES roles(id)
    );

    CREATE TABLE education_stages (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, order_index INTEGER DEFAULT 0,
        is_hidden INTEGER DEFAULT 0
    );

    CREATE TABLE grades (
        id INTEGER PRIMARY KEY, stage_id INTEGER, name TEXT NOT NULL,
        order_index INTEGER DEFAULT 0, is_hidden INTEGER DEFAULT 0,
        legacy_source_id INTEGER,
        FOREIGN KEY(stage_id) REFERENCES education_stages(id)
    );

    CREATE TABLE subjects (
        id INTEGER PRIMARY KEY, grade_id INTEGER, name TEXT NOT NULL,
        is_hidden INTEGER DEFAULT 0, legacy_source_id INTEGER,
        FOREIGN KEY(grade_id) REFERENCES grades(id)
    );

    CREATE TABLE units (
        id INTEGER PRIMARY KEY, subject_id INTEGER, name TEXT NOT NULL,
        order_index INTEGER DEFAULT 0, is_hidden INTEGER DEFAULT 0,
        is_deleted INTEGER DEFAULT 0, deleted_at TEXT, legacy_source_id INTEGER,
        FOREIGN KEY(subject_id) REFERENCES subjects(id)
    );

    CREATE TABLE lessons (
        id INTEGER PRIMARY KEY, unit_id INTEGER, name TEXT NOT NULL,
        order_index INTEGER DEFAULT 0, is_hidden INTEGER DEFAULT 0,
        is_deleted INTEGER DEFAULT 0, deleted_at TEXT, needs_review INTEGER DEFAULT 0,
        legacy_source_id INTEGER,
        FOREIGN KEY(unit_id) REFERENCES units(id)
    );

    CREATE TABLE question_types (
        id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    );

    CREATE TABLE questions (
        id INTEGER PRIMARY KEY, lesson_id INTEGER, question_type_id INTEGER,
        original_question_type TEXT,
        question TEXT NOT NULL, answer TEXT, correction TEXT,
        choice_a TEXT, choice_b TEXT, choice_c TEXT, choice_d TEXT,
        points REAL DEFAULT 1, source TEXT, approved INTEGER DEFAULT 0,
        is_hidden INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0, deleted_at TEXT,
        created_by INTEGER, created_at TEXT, legacy_source_id INTEGER,
        FOREIGN KEY(lesson_id) REFERENCES lessons(id),
        FOREIGN KEY(question_type_id) REFERENCES question_types(id)
    );

    CREATE TABLE exams (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL,
        stage_id INTEGER, grade_id INTEGER, subject_id INTEGER, unit_id INTEGER, lesson_id INTEGER,
        duration_minutes INTEGER, total_marks REAL DEFAULT 0,
        shuffle_questions INTEGER DEFAULT 0, shuffle_choices INTEGER DEFAULT 0,
        allow_retake INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
        created_by INTEGER, created_at TEXT, legacy_source_table TEXT, legacy_source_id INTEGER
    );

    CREATE TABLE exam_questions (
        id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL, question_id INTEGER NOT NULL,
        question_order INTEGER, marks REAL DEFAULT 1,
        FOREIGN KEY(exam_id) REFERENCES exams(id),
        FOREIGN KEY(question_id) REFERENCES questions(id)
    );

    CREATE TABLE exam_attempts (
        id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL, student_user_id INTEGER,
        student_name_legacy TEXT, started_at TEXT, submitted_at TEXT,
        score REAL, percentage REAL, correct_count INTEGER, wrong_count INTEGER,
        duration_seconds INTEGER,
        FOREIGN KEY(exam_id) REFERENCES exams(id)
    );

    CREATE TABLE attempt_answers (
        id INTEGER PRIMARY KEY, attempt_id INTEGER NOT NULL, question_id INTEGER NOT NULL,
        student_answer TEXT, is_correct INTEGER,
        FOREIGN KEY(attempt_id) REFERENCES exam_attempts(id),
        FOREIGN KEY(question_id) REFERENCES questions(id)
    );

    CREATE TABLE ai_answers (
        id INTEGER PRIMARY KEY, question_id INTEGER, provider TEXT,
        answer_text TEXT, status TEXT, created_at TEXT,
        FOREIGN KEY(question_id) REFERENCES questions(id)
    );

    CREATE TABLE ai_settings (
        id INTEGER PRIMARY KEY, primary_provider TEXT NOT NULL,
        fallback_provider TEXT, updated_at TEXT
    );

    CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, entity TEXT,
        entity_id INTEGER, details_json TEXT, created_at TEXT
    );

    CREATE TABLE migration_notes (
        id INTEGER PRIMARY KEY, table_name TEXT, record_id INTEGER,
        note TEXT, created_at TEXT
    );
    """)


def seed_reference_data(dst, log):  # noqa: C901
    now = utcnow()
    roles = [("admin", "مدير النظام"), ("teacher", "مدرس"),
             ("reviewer", "مراجع محتوى"), ("student", "طالب")]
    dst.executemany("INSERT INTO roles(code,name) VALUES(?,?)", roles)

    dst.execute("INSERT INTO education_stages(id,name,order_index) VALUES (1,?,1)",
                ("المرحلة الإعدادية",))
    dst.execute("INSERT INTO education_stages(id,name,order_index) VALUES (2,?,2)",
                ("المرحلة الثانوية",))

    qtype_id_map = {}
    next_id = 1
    seen_codes = {}
    for raw, (code, name) in QUESTION_TYPE_MAP.items():
        if code not in seen_codes:
            dst.execute("INSERT INTO question_types(id,code,name) VALUES (?,?,?)",
                        (next_id, code, name))
            seen_codes[code] = next_id
            next_id += 1
        qtype_id_map[raw] = seen_codes[code]
    for code, name in EXTRA_QUESTION_TYPES:
        dst.execute("INSERT INTO question_types(id,code,name) VALUES (?,?,?)",
                    (next_id, code, name))
        next_id += 1

    dst.execute("INSERT INTO ai_settings(id,primary_provider,fallback_provider,updated_at) "
                "VALUES (1,'gemini','openai',?)", (now,))
    log(None, None, "تمت إضافة roles/education_stages/question_types/ai_settings المرجعية.")
    return qtype_id_map


def migrate(src_path, outdir):
    os.makedirs(outdir, exist_ok=True)
    dst_path = os.path.join(outdir, "education_normalized.db")
    if os.path.exists(dst_path):
        os.remove(dst_path)  # إعادة بناء الوجهة فقط، الأصل غير ملموس إطلاقًا

    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    backup_path = os.path.join(outdir, "backups",
                                f"education_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    counts = backup_source_as_json(src, backup_path)
    print(f"[1/9] نسخة احتياطية JSON كاملة: {backup_path}")
    for t, c in counts.items():
        print(f"      - {t}: {c} صف")

    dst = sqlite3.connect(dst_path)
    dst.execute("PRAGMA foreign_keys = ON")
    build_schema(dst)
    print("[2/9] تم إنشاء الـSchema الجديد.")

    notes = []
    def log(table, record_id, note):
        notes.append((table, record_id, note, utcnow()))

    qtype_id_map = seed_reference_data(dst, log)
    print("[3/9] تم إدخال البيانات المرجعية (roles/stages/question_types).")

    # --- grades ---
    src_grades = src.execute("SELECT * FROM grades").fetchall()
    for g in src_grades:
        stage_id = 2 if "ثانوى" in g["name"] or "ثانوي" in g["name"] else 1
        is_hidden = 1 if g["id"] in DUPLICATE_GRADE_IDS else 0
        dst.execute(
            "INSERT INTO grades(id,stage_id,name,order_index,is_hidden,legacy_source_id) "
            "VALUES (?,?,?,?,?,?)",
            (g["id"], stage_id, g["name"], g["id"], is_hidden, g["id"]))
        if is_hidden:
            log("grades", g["id"],
                f"سجل مكرر لنفس الصف رقم {DUPLICATE_GRADE_NAME_CANONICAL_ID}، تم إخفاؤه وليس حذفه.")
    print(f"[4/9] grades: تم ترحيل {len(src_grades)} صف.")

    # --- subjects (الأصلية + المادة الجديدة الحقيقية) ---
    src_subjects = src.execute("SELECT * FROM subjects").fetchall()
    for s in src_subjects:
        dst.execute("INSERT INTO subjects(id,grade_id,name,legacy_source_id) VALUES (?,?,?,?)",
                    (s["id"], s["grade_id"], s["name"], s["id"]))
    new_subject_id = (max((s["id"] for s in src_subjects), default=0) + 1)
    dst.execute("INSERT INTO subjects(id,grade_id,name) VALUES (?,?,?)",
                (new_subject_id, DUPLICATE_GRADE_NAME_CANONICAL_ID, NEW_SUBJECT_NAME))
    log("subjects", new_subject_id,
        "تم إنشاء سجل مادة حقيقي 'الدراسات الاجتماعية' لأن كل المحتوى الحالي (وحدات/دروس/أسئلة) "
        "كان بدون مادة مطابقة في البيانات الأصلية.")
    print(f"[5/9] subjects: تم ترحيل {len(src_subjects)} + إضافة مادة جديدة id={new_subject_id}.")

    # --- units (تُربط كلها بالمادة الجديدة لأنها كانت orphan) ---
    src_units = src.execute("SELECT * FROM units").fetchall()
    for u in src_units:
        subject_id = u["subject_id"] if u["subject_id"] is not None else new_subject_id
        dst.execute("INSERT INTO units(id,subject_id,name,order_index,legacy_source_id) "
                    "VALUES (?,?,?,?,?)", (u["id"], subject_id, u["name"], u["id"], u["id"]))
        if u["subject_id"] is None:
            log("units", u["id"], f"subject_id كان NULL، تم ربطه بـ'{NEW_SUBJECT_NAME}' (id={new_subject_id}).")
    print(f"[6/9] units: تم ترحيل {len(src_units)} صف.")

    # --- lessons ---
    src_lessons = src.execute("SELECT * FROM lessons").fetchall()
    for l in src_lessons:
        unit_id = l["unit_id"]
        needs_review = 0
        if unit_id is None:
            unit_id = 2  # أقرب وحدة مطابقة للمحتوى (انظر DATA_AUDIT.md بند ب)
            needs_review = 1
            log("lessons", l["id"],
                "unit_id كان NULL. تم ربطه مؤقتًا بالوحدة id=2 (أقرب تطابق بالمحتوى) "
                "ووُسم needs_review=1 لمراجعة المعلم/الإداري قبل الاعتماد.")
        dst.execute("INSERT INTO lessons(id,unit_id,name,order_index,needs_review,legacy_source_id) "
                    "VALUES (?,?,?,?,?,?)", (l["id"], unit_id, l["name"], l["id"], needs_review, l["id"]))
    print(f"[7/9] lessons: تم ترحيل {len(src_lessons)} صف.")

    # --- questions ---
    src_questions = src.execute("SELECT * FROM questions").fetchall()
    for q in src_questions:
        qtype_id = qtype_id_map.get(q["question_type"])
        if qtype_id is None:
            log("questions", q["id"], f"نوع سؤال غير معروف: '{q['question_type']}', ترك بدون تصنيف.")
        dst.execute(
            "INSERT INTO questions(id,lesson_id,question_type_id,original_question_type,question,"
            "answer,correction,choice_a,choice_b,choice_c,choice_d,source,approved,legacy_source_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (q["id"], q["lesson_id"], qtype_id, q["question_type"], q["question"], q["answer"],
             q["correction"], q["choice_a"], q["choice_b"], q["choice_c"], q["choice_d"],
             q["source"], q["approved"], q["id"]))
    print(f"[8/9] questions: تم ترحيل {len(src_questions)} صف.")

    # --- exams + fixed_exams -> exams موحّد ---
    for e in src.execute("SELECT * FROM exams").fetchall():
        dst.execute(
            "INSERT INTO exams(id,name,lesson_id,total_marks,legacy_source_table,legacy_source_id) "
            "VALUES (?,?,?,?, 'exams', ?)",
            (e["id"], e["name"], e["lesson_id"], e["total_marks"], e["id"]))
    for eq in src.execute("SELECT * FROM exam_questions").fetchall():
        exists = dst.execute("SELECT 1 FROM questions WHERE id=?", (eq["question_id"],)).fetchone()
        if not exists:
            log("exam_questions", eq["id"],
                f"مرجع مكسور أصلاً في المصدر: exam_questions.id={eq['id']} يشير إلى question_id="
                f"{eq['question_id']} غير الموجود في questions (questions تبدأ من id=4 في المصدر الأصلي). "
                "السطر محفوظ بالكامل في النسخة الاحتياطية JSON، ولم يُنقل إلى الجدول الجديد لأنه كان "
                "سيكسر سلامة البيانات. يحتاج قرار يدوي من الإداري (حذف الربط أو استبداله بسؤال صحيح).")
            continue
        dst.execute("INSERT INTO exam_questions(id,exam_id,question_id) VALUES (?,?,?)",
                    (eq["id"], eq["exam_id"], eq["question_id"]))

    fixed_exam_id_offset = 1000  # لتفادي تصادم IDs مع جدول exams الأصلي
    for fe in src.execute("SELECT * FROM fixed_exams").fetchall():
        new_id = fixed_exam_id_offset + fe["id"]
        dst.execute(
            "INSERT INTO exams(id,name,duration_minutes,total_marks,legacy_source_table,legacy_source_id) "
            "VALUES (?,?,?,?, 'fixed_exams', ?)",
            (new_id, fe["exam_name"], fe["duration_minutes"], fe["total_marks"], fe["id"]))
        log("exams", new_id,
            f"جاء من fixed_exams (grade='{fe['grade']}', subject='{fe['subject']}' كانت نصًا حرًا بدون FK؛ "
            "تحتاج ربط يدوي بالـIDs الحقيقية من لوحة التحكم).")
    for feq in src.execute("SELECT * FROM fixed_exam_questions").fetchall():
        exists = dst.execute("SELECT 1 FROM questions WHERE id=?", (feq["question_id"],)).fetchone()
        if not exists:
            log("fixed_exam_questions", feq["id"],
                f"مرجع مكسور: question_id={feq['question_id']} غير موجود. محفوظ في النسخة الاحتياطية فقط.")
            continue
        dst.execute(
            "INSERT INTO exam_questions(id,exam_id,question_id,question_order,marks) "
            "VALUES (?,?,?,?,?)",
            (feq["id"] + 500, fixed_exam_id_offset + feq["exam_id"], feq["question_id"],
             feq["question_order"], feq["marks"]))
    print("[9/9] exams/fixed_exams -> exams موحّد + exam_questions.")

    # --- results -> exam_attempts (مبسّط، الطالب نصي مؤقتًا) ---
    for r in src.execute("SELECT * FROM results").fetchall():
        dst.execute(
            "INSERT INTO exam_attempts(id,exam_id,student_name_legacy,score) VALUES (?,?,?,?)",
            (r["id"], r["exam_id"], r["student_name"], r["score"]))

    # --- ai_answers ---
    for a in src.execute("SELECT * FROM ai_answers").fetchall():
        dst.execute(
            "INSERT INTO ai_answers(id,question_id,provider,answer_text,status,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (a["id"], a["question_id"], a["source"], a["ai_answer"], a["status"], a["created_at"]))

    for note in notes:
        dst.execute("INSERT INTO migration_notes(table_name,record_id,note,created_at) VALUES (?,?,?,?)", note)

    dst.commit()

    print("\n=== تقرير التحقق النهائي (عدد الصفوف في الوجهة) ===")
    dest_counts = {}
    for t in ["roles", "education_stages", "grades", "subjects", "units", "lessons",
              "question_types", "questions", "exams", "exam_questions", "exam_attempts",
              "ai_answers", "migration_notes"]:
        c = dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        dest_counts[t] = c
        print(f"  {t}: {c}")

    print("\n=== Integrity Checks ===")
    checks_passed = True

    def check(label, condition, detail=""):
        nonlocal checks_passed
        status = "PASS" if condition else "FAIL"
        if not condition:
            checks_passed = False
        print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))

    # 1) لا فقدان في الجداول التعليمية الأساسية (لازم تساوي تام مع المصدر)
    check("grades: 6 -> 6 (بدون فقد، التكرار وُسم لا حُذف)", counts["grades"] == dest_counts["grades"])
    check("units: 4 -> 4", counts["units"] == dest_counts["units"])
    check("lessons: 9 -> 9", counts["lessons"] == dest_counts["lessons"])
    check("questions: 159 -> 159 (لا حذف ولا اختراع محتوى)",
          counts["questions"] == dest_counts["questions"])
    check("subjects: 1 -> 2 (+1 مادة جديدة موثقة في migration_notes)",
          dest_counts["subjects"] == counts["subjects"] + 1)
    check("ai_answers: 10 -> 10", counts["ai_answers"] == dest_counts["ai_answers"])

    # 2) لا orphan FK غير موثّق في الجداول الجديدة
    orphan_units = dst.execute(
        "SELECT COUNT(*) FROM units WHERE subject_id IS NULL").fetchone()[0]
    check("units: لا يوجد subject_id فارغ بعد الترحيل", orphan_units == 0)

    orphan_lessons = dst.execute(
        "SELECT COUNT(*) FROM lessons WHERE unit_id IS NULL").fetchone()[0]
    check("lessons: لا يوجد unit_id فارغ بعد الترحيل", orphan_lessons == 0)

    orphan_questions = dst.execute(
        "SELECT COUNT(*) FROM questions q LEFT JOIN lessons l ON q.lesson_id=l.id "
        "WHERE l.id IS NULL").fetchone()[0]
    check("questions: كل سؤال مرتبط بدرس موجود فعليًا", orphan_questions == 0)

    unclassified = dst.execute(
        "SELECT COUNT(*) FROM questions WHERE question_type_id IS NULL").fetchone()[0]
    check("questions: كل الأسئلة مصنّفة (question_type_id)", unclassified == 0)

    dangling_notes = dst.execute(
        "SELECT COUNT(*) FROM migration_notes WHERE note LIKE '%مرجع مكسور%'").fetchone()[0]
    print(f"  [INFO] عدد الروابط المكسورة أصلاً في المصدر (exam_questions/fixed_exam_questions) "
          f"المُوثَّقة وغير المنقولة كربط فعلي: {dangling_notes} — محفوظة كاملة في النسخة الاحتياطية JSON.")

    # 3) حساب صريح لفارق exam_questions (يجب أن يُفسَّر بالكامل، لا يُترك بدون توضيح)
    src_link_total = counts["exam_questions"] + counts["fixed_exam_questions"]
    dest_link_total = dest_counts["exam_questions"]
    explained_gap = dangling_notes
    check(
        f"exam_questions: الفارق ({src_link_total} أصل -> {dest_link_total} منقول) "
        f"مفسَّر بالكامل بروابط مكسورة موثّقة ({explained_gap})",
        src_link_total - dest_link_total == explained_gap
    )

    print(f"\n>>> النتيجة الإجمالية: {'PASS — لم يُفقد أي محتوى تعليمي' if checks_passed else 'FAIL — راجع الفحوصات أعلاه'}")

    src.close()
    dst.close()
    print(f"\nتم إنشاء القاعدة الجديدة بنجاح: {dst_path}")
    print(f"النسخة الاحتياطية الكاملة: {backup_path}")
    print("الأصل (education.db) لم يتم لمسه إطلاقًا.")
    return checks_passed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--outdir", default="./migration_output")
    args = ap.parse_args()
    if not os.path.exists(args.source):
        print(f"الملف غير موجود: {args.source}", file=sys.stderr)
        sys.exit(1)
    ok = migrate(args.source, args.outdir)
    sys.exit(0 if ok else 2)
