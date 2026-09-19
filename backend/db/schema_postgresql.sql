-- ============================================================
-- منصة التميز التعليمية — PostgreSQL Schema (Phase 2)
-- ============================================================
-- ملاحظة: هذا الملف تصميم SQL خام؛ التنفيذ الفعلي والاعتماد عبر
-- SQLAlchemy models في app/models.py (نفس البنية بالضبط) بحيث يعمل
-- الكود على SQLite في التطوير المحلي وعلى PostgreSQL في الإنتاج
-- بدون تغيير كود، فقط عبر متغير DATABASE_URL.
-- لم يتم تشغيل هذا الملف فعليًا على خادم PostgreSQL حقيقي داخل بيئة
-- التطوير الحالية (لا يوجد اتصال إنترنت/خادم متاح لي هنا) — راجع
-- README.md قسم "ما لم يتم اختباره" للتفاصيل.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- لتوليد UUID عند الحاجة
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector للبحث الدلالي (Phase 9)

-- ---------- المستخدمون والصلاحيات ----------

CREATE TABLE roles (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(30) UNIQUE NOT NULL,   -- SUPER_ADMIN / ADMIN / TEACHER / REVIEWER / STUDENT
    name        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(100) UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    role_id         INTEGER NOT NULL REFERENCES roles(id),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_role ON users(role_id);

-- ---------- الهيكل التعليمي ----------

CREATE TABLE education_stages (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    is_hidden   BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE grades (
    id                SERIAL PRIMARY KEY,
    stage_id          INTEGER NOT NULL REFERENCES education_stages(id),
    name              VARCHAR(150) NOT NULL,
    order_index       INTEGER NOT NULL DEFAULT 0,
    is_hidden         BOOLEAN NOT NULL DEFAULT false,
    legacy_source_id  INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_grades_stage ON grades(stage_id);

CREATE TABLE subjects (
    id                SERIAL PRIMARY KEY,
    grade_id          INTEGER NOT NULL REFERENCES grades(id),
    name              VARCHAR(150) NOT NULL,
    is_hidden         BOOLEAN NOT NULL DEFAULT false,
    legacy_source_id  INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_subjects_grade ON subjects(grade_id);

CREATE TABLE units (
    id                SERIAL PRIMARY KEY,
    subject_id        INTEGER NOT NULL REFERENCES subjects(id),
    name              VARCHAR(255) NOT NULL,
    order_index       INTEGER NOT NULL DEFAULT 0,
    is_hidden         BOOLEAN NOT NULL DEFAULT false,
    is_deleted        BOOLEAN NOT NULL DEFAULT false,
    deleted_at        TIMESTAMPTZ,
    legacy_source_id  INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_units_subject ON units(subject_id);

CREATE TABLE lessons (
    id                SERIAL PRIMARY KEY,
    unit_id           INTEGER NOT NULL REFERENCES units(id),
    name              VARCHAR(255) NOT NULL,
    order_index       INTEGER NOT NULL DEFAULT 0,
    is_hidden         BOOLEAN NOT NULL DEFAULT false,
    is_deleted        BOOLEAN NOT NULL DEFAULT false,
    deleted_at        TIMESTAMPTZ,
    needs_review      BOOLEAN NOT NULL DEFAULT false,
    legacy_source_id  INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_lessons_unit ON lessons(unit_id);

-- ---------- الأسئلة ----------

CREATE TABLE question_types (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(40) UNIQUE NOT NULL,  -- MCQ, TRUE_FALSE, FILL_BLANK, TERM, WHO_IS, MAP,
                                               -- RELATION, WHAT_IF, EXPLAIN_WHY, SHORT_ANSWER, ESSAY, OTHER
    name        VARCHAR(100) NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT true
);

CREATE TYPE question_status AS ENUM (
    'IMPORTED', 'NEEDS_REVIEW', 'NEEDS_CLASSIFICATION', 'DUPLICATE', 'APPROVED', 'REJECTED'
);
CREATE TYPE source_type AS ENUM ('PDF', 'WORD', 'EXCEL', 'TEXT', 'AI_GENERATED', 'MANUAL', 'LEGACY_DB');

CREATE TABLE questions (
    id                      SERIAL PRIMARY KEY,
    lesson_id               INTEGER NOT NULL REFERENCES lessons(id),
    question_type_id        INTEGER REFERENCES question_types(id),
    original_question_type  VARCHAR(100),              -- القيمة الخام قبل التوحيد (يُحتفظ بها دائمًا)
    question                TEXT NOT NULL,
    answer                  TEXT,
    correction              TEXT,
    points                  NUMERIC(5,2) NOT NULL DEFAULT 1,
    status                  question_status NOT NULL DEFAULT 'NEEDS_REVIEW',
    approved                BOOLEAN NOT NULL DEFAULT false,   -- محتفظ به توافقًا مع البيانات القديمة
    classification_confidence NUMERIC(4,3),             -- ثقة تصنيف النوع (AI)، NULL = يدوي/غير محسوب
    is_hidden               BOOLEAN NOT NULL DEFAULT false,
    is_deleted              BOOLEAN NOT NULL DEFAULT false,   -- Soft delete فقط، أبدًا DELETE حقيقي
    deleted_at              TIMESTAMPTZ,

    -- Source metadata (Phase 23)
    source_type             source_type NOT NULL DEFAULT 'LEGACY_DB',
    source_file_name        VARCHAR(500),
    source_page_number      INTEGER,
    import_batch_id         INTEGER,      -- FK يُضاف بعد إنشاء import_batches أدناه
    ai_provider             VARCHAR(30),
    ai_model                VARCHAR(100),

    legacy_source_id        INTEGER,
    created_by              INTEGER REFERENCES users(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- للبحث الدلالي (Phase 9 / 24)
    embedding               vector(768)
);
CREATE INDEX idx_questions_lesson ON questions(lesson_id);
CREATE INDEX idx_questions_status ON questions(status);
CREATE INDEX idx_questions_approved ON questions(approved) WHERE approved = true;
CREATE INDEX idx_questions_embedding ON questions USING ivfflat (embedding vector_cosine_ops);

-- الاختيارات كجدول منفصل (بدل أعمدة choice_a..d) — قابل للتوسع لأي عدد اختيارات
CREATE TABLE question_choices (
    id            SERIAL PRIMARY KEY,
    question_id   INTEGER NOT NULL REFERENCES questions(id),
    choice_text   TEXT NOT NULL,
    choice_order  INTEGER NOT NULL DEFAULT 0,
    is_correct    BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX idx_choices_question ON question_choices(question_id);

-- بنك أسئلة عام إضافي (منفصل عن questions التشغيلية) — placeholder قابل للتفعيل لاحقًا
CREATE TABLE question_bank (
    id          SERIAL PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    tag         VARCHAR(100),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- الامتحانات ----------

CREATE TABLE exams (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    stage_id            INTEGER REFERENCES education_stages(id),
    grade_id            INTEGER REFERENCES grades(id),
    subject_id          INTEGER REFERENCES subjects(id),
    unit_id             INTEGER REFERENCES units(id),
    lesson_id           INTEGER REFERENCES lessons(id),
    duration_minutes    INTEGER,
    total_marks         NUMERIC(6,2) NOT NULL DEFAULT 0,
    shuffle_questions   BOOLEAN NOT NULL DEFAULT false,
    shuffle_choices     BOOLEAN NOT NULL DEFAULT false,
    allow_retake        BOOLEAN NOT NULL DEFAULT false,
    is_active           BOOLEAN NOT NULL DEFAULT true,
    legacy_source_table VARCHAR(50),
    legacy_source_id    INTEGER,
    created_by          INTEGER REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE exam_questions (
    id              SERIAL PRIMARY KEY,
    exam_id         INTEGER NOT NULL REFERENCES exams(id),
    question_id     INTEGER NOT NULL REFERENCES questions(id),
    question_order  INTEGER NOT NULL DEFAULT 0,
    marks           NUMERIC(5,2) NOT NULL DEFAULT 1,
    UNIQUE(exam_id, question_id)
);
CREATE INDEX idx_examq_exam ON exam_questions(exam_id);

CREATE TABLE exam_attempts (
    id                  SERIAL PRIMARY KEY,
    exam_id             INTEGER NOT NULL REFERENCES exams(id),
    student_user_id     INTEGER REFERENCES users(id),
    student_name_legacy VARCHAR(255),
    started_at          TIMESTAMPTZ,
    submitted_at        TIMESTAMPTZ,
    score               NUMERIC(6,2),
    percentage          NUMERIC(5,2),
    correct_count       INTEGER,
    wrong_count         INTEGER,
    duration_seconds    INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_attempts_exam ON exam_attempts(exam_id);
CREATE INDEX idx_attempts_student ON exam_attempts(student_user_id);

CREATE TABLE attempt_answers (
    id            SERIAL PRIMARY KEY,
    attempt_id    INTEGER NOT NULL REFERENCES exam_attempts(id),
    question_id   INTEGER NOT NULL REFERENCES questions(id),
    student_answer TEXT,
    is_correct    BOOLEAN
);
CREATE INDEX idx_attempt_answers_attempt ON attempt_answers(attempt_id);

-- Results (تُبقى كجدول تجميعي متوافق مع البيانات القديمة، exam_attempts هو المصدر الأساسي الجديد)
CREATE TABLE results (
    id            SERIAL PRIMARY KEY,
    exam_attempt_id INTEGER NOT NULL REFERENCES exam_attempts(id),
    subject_id    INTEGER REFERENCES subjects(id),
    lesson_id     INTEGER REFERENCES lessons(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- الذكاء الاصطناعي ----------

CREATE TABLE ai_answers (
    id            SERIAL PRIMARY KEY,
    question_id   INTEGER REFERENCES questions(id),
    provider      VARCHAR(30) NOT NULL,
    model         VARCHAR(100),
    answer_text   TEXT,
    status        VARCHAR(30),
    request_ms    INTEGER,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ai_answers_question ON ai_answers(question_id);

CREATE TABLE ai_settings (
    id                  SERIAL PRIMARY KEY,
    primary_provider    VARCHAR(30) NOT NULL,
    fallback_provider   VARCHAR(30),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- ملاحظة: لا يوجد أي عمود لمفاتيح API هنا عمدًا. المفاتيح تُقرأ فقط من
-- Environment Variables على السيرفر (GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY).

-- ---------- مركز الاستيراد الذكي ----------

CREATE TYPE batch_status AS ENUM (
    'UPLOAD_RECEIVED', 'PROCESSING', 'EXTRACTING', 'ANALYZING',
    'DUPLICATE_CHECK', 'NEEDS_REVIEW', 'COMPLETED', 'FAILED'
);

CREATE TABLE import_files (
    id            SERIAL PRIMARY KEY,
    file_name     VARCHAR(500) NOT NULL,
    file_type     VARCHAR(20) NOT NULL,   -- PDF/WORD/EXCEL/CSV/TEXT
    storage_path  VARCHAR(1000) NOT NULL,
    uploaded_by   INTEGER REFERENCES users(id),
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE import_batches (
    id                  SERIAL PRIMARY KEY,
    batch_number        VARCHAR(30) UNIQUE NOT NULL,   -- مثال: Batch #00025
    import_file_id      INTEGER REFERENCES import_files(id),
    status              batch_status NOT NULL DEFAULT 'UPLOAD_RECEIVED',
    total_questions     INTEGER NOT NULL DEFAULT 0,
    needs_review_count  INTEGER NOT NULL DEFAULT 0,
    duplicate_count     INTEGER NOT NULL DEFAULT 0,
    approved_count      INTEGER NOT NULL DEFAULT 0,
    rejected_count      INTEGER NOT NULL DEFAULT 0,
    needs_classification_count INTEGER NOT NULL DEFAULT 0,
    created_by          INTEGER REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    error_message       TEXT
);

CREATE TABLE imported_questions (
    id                SERIAL PRIMARY KEY,
    import_batch_id   INTEGER NOT NULL REFERENCES import_batches(id),
    question_id       INTEGER REFERENCES questions(id),   -- يُملأ بعد إنشاء السؤال الفعلي في questions
    raw_text          TEXT NOT NULL,
    page_number       INTEGER,
    duplicate_of_question_id INTEGER REFERENCES questions(id),
    similarity_score  NUMERIC(4,3),
    status            question_status NOT NULL DEFAULT 'IMPORTED',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_imported_q_batch ON imported_questions(import_batch_id);

ALTER TABLE questions
    ADD CONSTRAINT fk_questions_import_batch
    FOREIGN KEY (import_batch_id) REFERENCES import_batches(id);

CREATE TABLE review_actions (
    id            SERIAL PRIMARY KEY,
    question_id   INTEGER NOT NULL REFERENCES questions(id),
    reviewer_id   INTEGER REFERENCES users(id),
    action        VARCHAR(30) NOT NULL,  -- APPROVE/REJECT/EDIT/CHANGE_TYPE/CHANGE_LESSON/SKIP/DELETE
    before_json   JSONB,
    after_json    JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_review_actions_question ON review_actions(question_id);

-- ---------- تدقيق شامل ----------

CREATE TABLE audit_logs (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER REFERENCES users(id),
    action        VARCHAR(100) NOT NULL,
    entity        VARCHAR(100) NOT NULL,
    entity_id     INTEGER,
    details_json  JSONB,
    ip_address    VARCHAR(64),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_entity ON audit_logs(entity, entity_id);

CREATE TABLE migration_notes (
    id            SERIAL PRIMARY KEY,
    table_name    VARCHAR(100),
    record_id     INTEGER,
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
