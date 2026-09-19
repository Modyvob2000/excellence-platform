# Backend — منصة التميز التعليمية

## التشغيل المحلي
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ثم عدّل القيم
export $(cat .env | xargs)
uvicorn app.main:app --reload
```
افتراضيًا `DATABASE_URL` يشير لـSQLite محلي (`sqlite:///./dev.db`) إن لم تضبط PostgreSQL — نفس الكود يعمل على الاثنين بدون تعديل.

## النشر (اقتراح عملي بدون خادم محدد لديك)
- **Railway** أو **Render**: يدعمان PostgreSQL مُدارًا مجانًا/رخيصًا + نشر FastAPI مباشرة من GitHub بدون إعداد يدوي لسيرفر.
- اضبط متغيرات البيئة (`DATABASE_URL`, `JWT_SECRET_KEY`, ومفاتيح AI) من لوحة تحكم الاستضافة نفسها — **لا تُدرَج أبدًا في الكود أو في تطبيق Android**.

## ما تم اختباره فعليًا في هذه البيئة (بدون إنترنت ولا حزم مثبَّتة)
| الملف | الاختبار | النتيجة |
|---|---|---|
| `app/auth_core.py` | `app/tests/test_auth_core.py` — 18 اختبار (تشفير كلمة المرور، JWT، RBAC) | ✅ 18/18 PASS |
| `app/ai_gateway/__init__.py` | `app/tests/test_ai_gateway.py` — 6 اختبارات (اختيار المزود، fallback، فشل الاثنين) | ✅ 6/6 PASS |
| `app/models.py`, `app/database.py`, `app/main.py`, `app/routers/auth.py` | `python3 -m py_compile` (فحص صياغي فقط) | ✅ لا أخطاء صياغية |
| `db/schema_postgresql.sql` | مراجعة يدوية فقط | ⚠️ لم يُشغَّل على خادم PostgreSQL حقيقي |

## ما لم يتم اختباره وسبب ذلك بوضوح
بيئة التطوير المتاحة لي هنا **بلا اتصال إنترنت** (لا يمكن `pip install fastapi/sqlalchemy/psycopg2` ولا الاتصال بأي خادم PostgreSQL أو استدعاء Gemini/OpenAI/Claude فعليًا). لذلك:
- تشغيل السيرفر فعليًا عبر `uvicorn` والتحقق من استجابة `/health` و`/auth/register` و`/auth/login` عبر HTTP حقيقي — **لم يُشغَّل**.
- تنفيذ `db/schema_postgresql.sql` على خادم PostgreSQL حقيقي والتأكد من عدم وجود أخطاء DDL — **لم يُشغَّل**.
- استدعاءات Gemini/OpenAI/Claude الفعلية داخل `ai_gateway` (حاليًا `TODO` صريح في كل مزود) — **لم تُنفَّذ ولم تُختبر**؛ منطق الاختيار والـfallback حوله مُختبر بمحاكاة (mocks) فقط.

**الخطوة العملية:** عند تشغيلك للمشروع على جهازك (بإنترنت)، نفّذ:
```bash
pip install -r requirements.txt
python3 -m pytest app/tests/ -v            # يعيد نفس النتائج المختبرة هنا + يضيف اختبارات API الحقيقية
psql -f ../db/schema_postgresql.sql your_database
```
وأخبرني بالنتيجة لأصلح أي خطأ يظهر فورًا.
