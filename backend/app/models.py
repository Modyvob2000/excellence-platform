"""
SQLAlchemy models — منصة التميز التعليمية
نفس البنية الموجودة في db/schema_postgresql.sql تمامًا، لكن معبَّرة كـORM
بحيث تعمل على SQLite (تطوير محلي بدون أي إعداد) وعلى PostgreSQL (إنتاج)
بتغيير DATABASE_URL فقط.

⚠️ ملاحظة صادقة: هذا الملف لم يتم تشغيله فعليًا في هذه البيئة لأن حزمة
SQLAlchemy غير مثبَّتة ولا يوجد اتصال إنترنت لتثبيتها هنا (راجع
backend/README.md قسم "ما لم يتم اختباره"). تم فحصه بـ`python3 -m py_compile`
للتأكد من خلوه من أخطاء صياغية فقط.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, JSON,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    code = Column(String(30), unique=True, nullable=False)  # SUPER_ADMIN/ADMIN/TEACHER/REVIEWER/STUDENT
    name = Column(String(100), nullable=False)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    role = relationship("Role")


class EducationStage(Base):
    __tablename__ = "education_stages"
    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    is_hidden = Column(Boolean, default=False, nullable=False)


class Grade(Base):
    __tablename__ = "grades"
    id = Column(Integer, primary_key=True)
    stage_id = Column(Integer, ForeignKey("education_stages.id"), nullable=False)
    name = Column(String(150), nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    is_hidden = Column(Boolean, default=False, nullable=False)
    legacy_source_id = Column(Integer)


class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    grade_id = Column(Integer, ForeignKey("grades.id"), nullable=False)
    name = Column(String(150), nullable=False)
    is_hidden = Column(Boolean, default=False, nullable=False)
    legacy_source_id = Column(Integer)


class Unit(Base):
    __tablename__ = "units"
    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    name = Column(String(255), nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    is_hidden = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    legacy_source_id = Column(Integer)


class Lesson(Base):
    __tablename__ = "lessons"
    id = Column(Integer, primary_key=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    name = Column(String(255), nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    is_hidden = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    needs_review = Column(Boolean, default=False, nullable=False)
    legacy_source_id = Column(Integer)


class QuestionType(Base):
    __tablename__ = "question_types"
    id = Column(Integer, primary_key=True)
    code = Column(String(40), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=False)
    question_type_id = Column(Integer, ForeignKey("question_types.id"))
    original_question_type = Column(String(100))
    question = Column(Text, nullable=False)
    answer = Column(Text)
    correction = Column(Text)
    points = Column(Numeric(5, 2), default=1, nullable=False)
    status = Column(String(30), default="NEEDS_REVIEW", nullable=False)
    approved = Column(Boolean, default=False, nullable=False)
    classification_confidence = Column(Numeric(4, 3))
    is_hidden = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)   # Soft delete فقط
    deleted_at = Column(DateTime(timezone=True))

    source_type = Column(String(20), default="LEGACY_DB", nullable=False)
    source_file_name = Column(String(500))
    source_page_number = Column(Integer)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"))
    ai_provider = Column(String(30))
    ai_model = Column(String(100))

    legacy_source_id = Column(Integer)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    choices = relationship("QuestionChoice", back_populates="question")


class QuestionChoice(Base):
    __tablename__ = "question_choices"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    choice_text = Column(Text, nullable=False)
    choice_order = Column(Integer, default=0, nullable=False)
    is_correct = Column(Boolean, default=False, nullable=False)

    question = relationship("Question", back_populates="choices")


class Exam(Base):
    __tablename__ = "exams"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    stage_id = Column(Integer, ForeignKey("education_stages.id"))
    grade_id = Column(Integer, ForeignKey("grades.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    unit_id = Column(Integer, ForeignKey("units.id"))
    lesson_id = Column(Integer, ForeignKey("lessons.id"))
    duration_minutes = Column(Integer)
    total_marks = Column(Numeric(6, 2), default=0, nullable=False)
    shuffle_questions = Column(Boolean, default=False, nullable=False)
    shuffle_choices = Column(Boolean, default=False, nullable=False)
    allow_retake = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    legacy_source_table = Column(String(50))
    legacy_source_id = Column(Integer)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = (UniqueConstraint("exam_id", "question_id"),)
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    question_order = Column(Integer, default=0, nullable=False)
    marks = Column(Numeric(5, 2), default=1, nullable=False)


class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    student_user_id = Column(Integer, ForeignKey("users.id"))
    student_name_legacy = Column(String(255))
    started_at = Column(DateTime(timezone=True))
    submitted_at = Column(DateTime(timezone=True))
    score = Column(Numeric(6, 2))
    percentage = Column(Numeric(5, 2))
    correct_count = Column(Integer)
    wrong_count = Column(Integer)
    duration_seconds = Column(Integer)


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"
    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, ForeignKey("exam_attempts.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    student_answer = Column(Text)
    is_correct = Column(Boolean)


class AIAnswer(Base):
    __tablename__ = "ai_answers"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"))
    provider = Column(String(30), nullable=False)
    model = Column(String(100))
    answer_text = Column(Text)
    status = Column(String(30))
    request_ms = Column(Integer)
    error = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class AISettings(Base):
    __tablename__ = "ai_settings"
    id = Column(Integer, primary_key=True)
    primary_provider = Column(String(30), nullable=False)
    fallback_provider = Column(String(30))
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    # لا يوجد أي عمود لمفاتيح API هنا عمدًا — المفاتيح من Environment Variables فقط.


class ImportFile(Base):
    __tablename__ = "import_files"
    id = Column(Integer, primary_key=True)
    file_name = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)
    storage_path = Column(String(1000), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id = Column(Integer, primary_key=True)
    batch_number = Column(String(30), unique=True, nullable=False)
    import_file_id = Column(Integer, ForeignKey("import_files.id"))
    status = Column(String(30), default="UPLOAD_RECEIVED", nullable=False)
    total_questions = Column(Integer, default=0, nullable=False)
    needs_review_count = Column(Integer, default=0, nullable=False)
    duplicate_count = Column(Integer, default=0, nullable=False)
    approved_count = Column(Integer, default=0, nullable=False)
    rejected_count = Column(Integer, default=0, nullable=False)
    needs_classification_count = Column(Integer, default=0, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)


class ImportedQuestion(Base):
    __tablename__ = "imported_questions"
    id = Column(Integer, primary_key=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"))
    raw_text = Column(Text, nullable=False)
    page_number = Column(Integer)
    duplicate_of_question_id = Column(Integer, ForeignKey("questions.id"))
    similarity_score = Column(Numeric(4, 3))
    status = Column(String(30), default="IMPORTED", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ReviewAction(Base):
    __tablename__ = "review_actions"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(30), nullable=False)
    before_json = Column(JSON)
    after_json = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100), nullable=False)
    entity = Column(String(100), nullable=False)
    entity_id = Column(Integer)
    details_json = Column(JSON)
    ip_address = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class MigrationNote(Base):
    __tablename__ = "migration_notes"
    id = Column(Integer, primary_key=True)
    table_name = Column(String(100))
    record_id = Column(Integer)
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
