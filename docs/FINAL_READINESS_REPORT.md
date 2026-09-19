# تقرير الجاهزية النهائي — منصة التميز التعليمية

تاريخ المراجعة: نهاية مرحلة "Final Hardening & Deployment Readiness".

## 1. المشاكل الحقيقية التي اكتُشفت وأُصلحت في هذه الجولة

### أ. Route Ordering Bug (حرج) — `backend/app/routers/questions.py`
**الوصف:** FastAPI/Starlette يطابق المسارات بترتيب التسجيل في الملف. مسار
`/{question_id}/approve` كان مُسجَّلًا **قبل** `/bulk/approve`، وبما أن
`{question_id}` بلا محدّد نوع صريح في نص المسار يُطابق هيكليًا أي segment
نصي (بما فيه الكلمة الحرفية "bulk")، فإن كل طلب إلى:
- `POST /questions/bulk/approve`
- `POST /questions/bulk/reject`

كان يُخطَف فعليًا إلى معالج السؤال الفردي `approve(question_id="bulk")` /
`reject(question_id="bulk")`، فيفشل بخطأ تحقق 422 (لأن "bulk" ليست رقمًا)
ولا يصل أبدًا لمنطق Bulk الصحيح. **هذا كان سيكسر بالكامل أزرار "اعتماد
المحدد" و"رفض المحدد" في كل من Android وAdmin Dashboard.**

**الإصلاح:** أُعيد ترتيب كل المسارات الحرفية الثابتة (`/bulk/*`, `/search/`)
لتُسجَّل **قبل** أي مسار بمُعامل (`/{question_id}...`) بنفس الفعل (method).
هذه هي الطريقة الصحيحة (وليست Workaround) — نفس القاعدة التي توصي بها وثائق
FastAPI نفسها لهذا النمط بالضبط.

**الوقاية من التكرار:** أُضيف `test_questions_router_route_ordering.py`
(9 اختبارات) يقرأ كل ملفات الراوترز عبر `ast` (بدون حاجة لتثبيت FastAPI)
ويُحاكي منطق مطابقة Starlette فعليًا، ليتحقق أن كل مسار حرفي يصل لمعالجه
الصحيح. شمل الاختبار فحصًا عامًا آليًا على **كل** راوترز المشروع (auth,
content, questions, exams, results, import, review, users, audit, search,
ai_generation) — النتيجة: **لا توجد أي مشكلة ترتيب أخرى في أي راوتر آخر.**

### ب. DTO Mismatch — `android/.../data/remote/ApiServices.kt`
`ResultsApi.examReport()` كان يُعلن نوع الإرجاع كـ`Map<String, Double>` بينما
الـbackend (`/results/exams/{id}/report`) يُرجع كائنًا بحقول مختلطة الأنواع
(`exam_id: int`, `attempts_count: int`, و4 حقول `float`). أُصلح بإضافة
`data class ExamReportOut` مطابق تمامًا لحقول `ExamReportOut` في
`routers/results.py`، بدل الاعتماد على تحويل ضمني هش لكل شيء إلى Double.

### ج. Room: `fallbackToDestructiveMigration` (خطر فقد بيانات) — أُصلح نهائيًا
كان الاعتماد على `fallbackToDestructiveMigration()` يعني أن أي ترقية إصدار
لقاعدة بيانات Room (v1→v2 بعد إضافة عمود `choices`) كانت ستُنفّذ عبر **حذف
كل الجداول وإعادة إنشائها**، أي **فقد كل إجابات الطلاب المحفوظة محليًا
(`pending_answers`) وكل الكاش المحلي (`questions_cache`, `lessons_cache`)**
لأي مستخدم يحدّث التطبيق أثناء انقطاع الاتصال — وهذا يتعارض مباشرة مع مبدأ
Offline-first نفسه.
**الإصلاح:** أُضيف `Migrations.kt` بـ`MIGRATION_1_2` حقيقية:
```sql
ALTER TABLE questions_cache ADD COLUMN choices TEXT NOT NULL DEFAULT ''
```
واستُبدل `.fallbackToDestructiveMigration()` بـ`.addMigrations(MIGRATION_1_2)`
في `AppModule.kt`. لا حذف لأي جدول، لا فقد لأي صف موجود.

## 2. مراجعات أُجريت ولم تكشف مشاكل (نتيجة إيجابية موثّقة، لا افتراض)

| المجال | نتيجة الفحص |
|---|---|
| DTOs Backend↔Android الأخرى (`QuestionOut`, `ExamOut`, `ResultOut`, `TokenResponse`, `NodeOut`, `BatchOut`, `ReviewItemOut`, `AttemptOut`, `BulkActionIn/Result`) | تطابق حرفي في أسماء/أنواع الحقول |
| مسارات Retrofit (Android) مقابل مسارات FastAPI الفعلية | تطابق كامل، بما فيها أسماء query params |
| مسارات Admin Dashboard (fetch calls) مقابل الـbackend | تطابق كامل |
| RBAC (`require_roles`, `auth_core.has_role_at_least`) | منطق صحيح: `SUPER_ADMIN` يتجاوز أي قيد أدوار، غيره يُرفض بـ403 إن لم يكن ضمن المسموح |
| Imports في كل ملفات `app/routers/*.py` | لا استيراد ناقص لأي اسم مُستخدَم |
| DI في Android (Hilt) | `QuestionRepository` (interface) مربوطة بـ`QuestionRepositoryImpl` عبر `@Provides` في `AppModule` بعد إعادة الهيكلة |
| Navigation graph | كل المسارات المُعرَّفة في `Routes` لها `composable()` مقابل، ولا توجد شاشة بلا مسار |

## 3. الاختبارات — النتائج الفعلية

```
Backend (unittest):  188 / 188  PASS
Migration:            14 /  14  PASS
─────────────────────────────────
الإجمالي:            202 / 202  PASS
```
الأمر الذي شُغِّل فعليًا: `python3 -m unittest discover -s app/tests` و
`python3 -m unittest migration.tests.test_migration`. لا ادّعاء بدون تنفيذ.

الاختبارات الجديدة في هذه الجولة: **9** (`test_questions_router_route_ordering.py`)
— جميعها PASS، وهي التي أثبتت الإصلاح وتمنع تكرار نفس الخطأ مستقبلًا.

Admin Dashboard: الـJavaScript المضمَّن **تحقّقت صحته الصياغية فعليًا** عبر
`node --check` (Node.js متوفر في هذه البيئة) — هذا تحقق حقيقي وليس افتراضًا،
لكنه فحص صياغة فقط وليس تشغيلًا فعليًا ضد سيرفر حي.

`education.db` الأصلي: **md5 مطابق تمامًا قبل وبعد** كل هذه المراجعة —
`45c9bbb78eb645e62b36ffcdac2055b7` — لم يُلمَس إطلاقًا.

## 4. ما لم يُختبر فعليًا، وسبب ذلك بالتحديد

| العنصر | السبب |
|---|---|
| تشغيل FastAPI عبر HTTP حقيقي (`uvicorn`) | لا اتصال إنترنت لتثبيت `fastapi`/`uvicorn`/`sqlalchemy`/`psycopg2` في هذه البيئة (تحقَّق بمحاولة `pip install` فعلية سابقًا، فشلت لعدم وجود اتصال) |
| PostgreSQL حقيقي (تنفيذ `schema_postgresql.sql`) | لا خادم PostgreSQL متاح، ولا اتصال لتثبيت أي عميل |
| Android Build (`./gradlew build` أو فتح المشروع في Android Studio) | لا Android SDK ولا Gradle ولا `kotlinc` في هذه البيئة (تحقَّق بـ`which kotlinc gradle` بلا نتيجة؛ فقط `java` موجود) |
| اختبارات Kotlin (`SyncQueueTest.kt`, `AttemptViewModelTest.kt`) | نفس السبب أعلاه — لا مترجم Kotlin لتشغيل `./gradlew test` |
| Room `MigrationTestHelper` لاختبار `MIGRATION_1_2` فعليًا على قاعدة بيانات SQLite حقيقية عبر Room | يحتاج `androidx.room:room-testing` + بيئة Android/JVM بها Room مثبَّتة؛ غير متاح هنا. الاستعلام SQL نفسه (`ALTER TABLE ... ADD COLUMN`) صياغة SQLite قياسية صحيحة تمت مراجعتها يدويًا |
| Admin Dashboard ضد سيرفر حي فعليًا (تسجيل دخول حقيقي، جلب بيانات فعلية) | يتطلب backend يعمل فعليًا، وهو غير مُشغَّل هنا للسبب أعلاه |
| استدعاءات Gemini/OpenAI/Claude الفعلية (`ai_gateway`) | لا اتصال إنترنت، ولا مفاتيح API متاحة في هذه البيئة (والتصميم أصلًا يمنع وضعها هنا) |

كل ما سبق **مكتوب بالكامل وصحيح صياغيًا** (تحقَّق بـ`py_compile` لكل ملف
Python، و`node --check` لجافاسكريبت الداشبورد)، لكن التحقق الصياغي **ليس
بديلًا عن Build/Run حقيقي** ولا يُدَّعى أنه كذلك.

## 5. المتطلبات اللازمة للتشغيل الحقيقي

- **Backend:** Python 3.11+, `pip install -r backend/requirements.txt`, PostgreSQL 14+ (أو SQLite للتطوير السريع بدون إعداد)، إنترنت لتثبيت الحزم.
- **Android:** Android Studio (Koala أو أحدث)، JDK 17، Android SDK (compileSdk 34، minSdk 24)، إنترنت لتنزيل Gradle wrapper والاعتماديات.
- **PostgreSQL:** خادم PostgreSQL 14+ مع امتدادي `pgcrypto` و`vector` (pgvector) للبحث الدلالي المستقبلي.
- **Admin Dashboard:** أي متصفح حديث + الـbackend يعمل ويُتاح على نفس الشبكة (CORS مفتوح حاليًا `allow_origins=["*"]` للتطوير فقط — **يجب تقييده قبل الإنتاج**، كما هو موثّق بـTODO في `main.py`).

## 6. خطوات Build/تشغيل فعلية (للتنفيذ خارج هذه البيئة)

### Backend
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # عدّل DATABASE_URL و JWT_SECRET_KEY ومفاتيح AI
export $(cat .env | xargs)
uvicorn app.main:app --reload
# تحقق: curl http://localhost:8000/health
```

### PostgreSQL
```bash
createdb excellence_platform
psql excellence_platform -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
psql excellence_platform -c "CREATE EXTENSION IF NOT EXISTS vector;"   # يحتاج pgvector مثبَّتة على الخادم
psql excellence_platform -f db/schema_postgresql.sql
# اضبط DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/excellence_platform في .env
```
ثم نفّذ `migration/migrate.py` (أو منطقًا مكافئًا) لترحيل بيانات `education.db`
الأصلية إلى الجداول الجديدة، تمامًا كما في Phase 1 (لا حاجة لإعادة تنفيذه إن
كانت `education_normalized.db` المُولَّدة مسبقًا كافية للاستيراد اليدوي).

### Android
```bash
cd android
# افتح المجلد في Android Studio (File > Open)، اسمح بـGradle Sync
# أو من سطر الأوامر بعد تثبيت Android SDK:
./gradlew assembleDebug
./gradlew test          # يشغّل SyncQueueTest و AttemptViewModelTest فعليًا
```
اضبط `API_BASE_URL` في `app/build.gradle.kts` (افتراضيًا `http://10.0.2.2:8000/`
للمحاكي مع backend محلي) أو مرّر عنوانًا حقيقيًا عبر متغير بيئة/بناء منفصل
لكل بيئة (dev/staging/prod).

### ربط Android بالـBackend
1. شغّل الـbackend (أعلاه) وتأكد من `curl http://<host>:8000/health`.
2. عدّل `API_BASE_URL` في `app/build.gradle.kts` (buildType المناسب).
3. سجّل مستخدمًا أول عبر `POST /auth/register` (أو مباشرة من شاشة تسجيل الدخول إن فُعِّلت واجهة تسجيل).
4. شغّل التطبيق على المحاكي/جهاز حقيقي على نفس الشبكة.

### Admin Dashboard
```bash
# لا حاجة لأي بناء — ملف واحد ثابت:
open admin-dashboard/index.html   # أو افتحه مباشرة في أي متصفح
```
في شاشة الدخول، أدخل عنوان الـbackend الفعلي (حقل "عنوان السيرفر") ثم سجّل
الدخول بحساب أُنشئ مسبقًا بدور `ADMIN` أو `SUPER_ADMIN` للوصول لكل الأقسام.

## 7. مشاكل/TODOs متبقية (موثّقة، وليست معيقة للتسليم الحالي)

- CORS في `main.py` مفتوح للجميع (`*`) — للتطوير فقط، يجب تقييده قبل الإنتاج.
- `SqlAlchemyExamStore` في `routers/exams.py`: منطق `count_attempts`/`allow_retake` يعتمد على `submitted_at IS NOT NULL` فقط — سيناريوهات إلغاء محاولة منتصفة (abandoned attempts) غير مُعالجة بعد.
- استدعاءات Gemini/OpenAI/Claude الفعلية في `ai_gateway/__init__.py` لا تزال `NotImplementedError` صريحة (موثّق من البداية) — تحتاج SDK كل مزود + مفاتيح حقيقية عند التفعيل.
- Room: يُنصح بإضافة `androidx.room:room-testing` وتشغيل `MigrationTestHelper` فعليًا أول مرة تتوفر فيها بيئة Android كاملة، قبل أي إصدار إنتاجي، للتحقق النهائي من `MIGRATION_1_2` على قاعدة بيانات SQLite حقيقية (وليس فقط المراجعة اليدوية للـSQL الحالية).
- لا يوجد حاليًا Refresh Token — الجلسة تنتهي بعد 8 ساعات (`auth_core.JWT_DEFAULT_EXPIRY_SECONDS`) ويحتاج المستخدم لتسجيل الدخول من جديد؛ مقبول للنسخة الحالية، مذكور كتحسين مستقبلي.
