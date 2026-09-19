# خطة الترحيل (Migration Plan)

## المبدأ
- المصدر: `education.db` الأصلية (لا تُعدَّل أبدًا، تُقرأ فقط).
- الوجهة (محلي/تطوير): `migration/education_normalized.db` (SQLite جديدة تمامًا).
- الوجهة (إنتاج): نفس الـSchema بالضبط لكن على PostgreSQL، عبر نفس نماذج SQLAlchemy المستخدمة في الـbackend (تغيير `DATABASE_URL` فقط، بدون تغيير كود).
- قبل أي كتابة: يُنشأ **نسخة احتياطية JSON كاملة** من كل الجداول الأصلية (`migration/backups/education_backup_<timestamp>.json`) — هذه هي آلية الاستعادة (Restore) المطلوبة.
- العملية بالكامل **Idempotent**: يمكن إعادة تشغيلها دون تكرار البيانات (تُنشئ ملف الوجهة من الصفر في كل مرة من المصدر فقط).

## البنية المستهدفة (الجداول الجديدة)

```
roles(id, code, name)
users(id, username, password_hash, full_name, role_id, is_active, created_at)

education_stages(id, name, order_index, is_hidden)          -- المرحلة الدراسية (جديد، عام)
grades(id, stage_id, name, order_index, is_hidden)           -- الصف
subjects(id, grade_id, name, is_hidden)                      -- المادة
units(id, subject_id, name, order_index, is_hidden, is_deleted, deleted_at)
lessons(id, unit_id, name, order_index, is_hidden, is_deleted, deleted_at, needs_review)

question_types(id, code, name, is_active)                    -- قابل للتوسع من لوحة التحكم
questions(id, lesson_id, question_type_id, question, answer, correction,
          choice_a, choice_b, choice_c, choice_d, points, source,
          approved, is_hidden, is_deleted, deleted_at, created_by, created_at)

exams(id, name, stage_id, grade_id, subject_id, unit_id, lesson_id,
      duration_minutes, total_marks, shuffle_questions, shuffle_choices,
      allow_retake, is_active, created_by, created_at)
exam_questions(id, exam_id, question_id, question_order, marks)

exam_attempts(id, exam_id, student_user_id, started_at, submitted_at,
              score, percentage, correct_count, wrong_count, duration_seconds)
attempt_answers(id, attempt_id, question_id, student_answer, is_correct)

ai_answers(id, question_id, provider, answer_text, status, created_at)   -- history/cache
ai_settings(id, primary_provider, fallback_provider, updated_at)         -- بدون أي مفتاح API هنا

audit_log(id, user_id, action, entity, entity_id, details_json, created_at)
migration_notes(id, table_name, record_id, note, created_at)             -- توثيق كل قرار تلقائي أثناء الترحيل
```

ملاحظات:
- كل "حذف" في النظام هو `is_deleted=1 / deleted_at=<وقت>` فقط (Soft delete)، أبدًا `DELETE FROM`.
- `is_hidden` منفصل عن `is_deleted`: الإخفاء لضبط الظهور للطلاب، الحذف المنطقي لسير عمل المراجعة والاسترجاع.
- لا يوجد أي عمود لتخزين مفاتيح AI في أي جدول يخص التطبيق — `ai_settings` يخزن فقط اسم المزود المختار، والمفاتيح الفعلية تُقرأ من متغيرات بيئة السيرفر (Environment Variables) فقط.

## خريطة الترحيل من القديم إلى الجديد

| من (قديم) | إلى (جديد) | التحويل |
|---|---|---|
| grades (6 صفوف، بها تكرار) | grades (مربوطة بـ education_stages) | دمج التكرار بالوسم فقط (is_hidden) كما في تقرير الفحص، بدون حذف |
| subjects (1 صف: عربى) | subjects | يبقى كما هو + يُضاف سجل حقيقي جديد "الدراسات الاجتماعية" |
| units (4، 3 منها orphan) | units | تُربط بمادة "الدراسات الاجتماعية" الجديدة |
| lessons (9، 1 orphan) | lessons | يُربط lesson id=2 بـ unit_id=2 مع `needs_review=1` |
| questions (159) | questions | question_type نصي → question_type_id عبر جدول question_types بعد التوحيد |
| question_bank (0) | (لا يُنقل) | فارغ، يبقى في الأصل فقط |
| exams / fixed_exams | exams (موحّدين في جدول واحد) | fixed_exams.subject/grade النصية تُربط بالـID الحقيقي إن أمكن، وإلا تُسجَّل ملاحظة في migration_notes |
| exam_questions / fixed_exam_questions | exam_questions | دمج مباشر |
| results | exam_attempts (مبسّط أوليًا) | student_name نصي مؤقتًا لحين ربط الطلاب بحسابات users حقيقية |
| ai_answers | ai_answers | نقل مباشر مع تسجيل provider='Gemini' كما هو مخزن |

## خطوات التنفيذ (بالترتيب)
1. تصدير نسخة JSON احتياطية كاملة من الأصل.
2. إنشاء الـSchema الجديد في `education_normalized.db`.
3. إدخال البيانات المرجعية الثابتة: roles، question_types، education_stages.
4. ترحيل grades → subjects → units → lessons مع إصلاحات الربط الموثقة.
5. ترحيل questions مع تحويل question_type إلى question_type_id.
6. ترحيل exams/fixed_exams → exams موحّد + exam_questions.
7. ترحيل results → exam_attempts.
8. ترحيل ai_answers كما هي.
9. كتابة كل قرار تلقائي تم اتخاذه في migration_notes (شفافية كاملة وقابلية للمراجعة اليدوية).
10. طباعة تقرير نهائي بعدد الصفوف المنقولة من كل جدول للتأكد من عدم فقدان أي بيانات.
