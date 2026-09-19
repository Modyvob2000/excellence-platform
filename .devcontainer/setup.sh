#!/usr/bin/env bash
# يُشغَّل تلقائيًا مرة واحدة عند إنشاء الـCodespace (postCreateCommand في devcontainer.json).
# لا يُعدِّل أي كود في المشروع — فقط يجهّز البيئة: يفكّ الزيب إن لزم،
# يثبّت اعتماديات Python، ويجهّز قاعدة بيانات PostgreSQL + pgvector.
set -e
cd /workspace

# ---------------------------------------------------------------------------
# 1) فكّ ExcellencePlatform_final.zip تلقائيًا إن لم يكن المشروع مفكوكًا بعد
# ---------------------------------------------------------------------------
if [ ! -d "backend" ] && [ -f "ExcellencePlatform_final.zip" ]; then
    echo ">>> فكّ ExcellencePlatform_final.zip ..."
    unzip -q ExcellencePlatform_final.zip -d .
fi

if [ ! -d "backend" ]; then
    echo "!!! تحذير: لم يوجد مجلد backend/ ولا ExcellencePlatform_final.zip في جذر المستودع."
    echo "    ارفع ExcellencePlatform_final.zip إلى جذر المستودع قبل إنشاء الـCodespace."
fi

# ---------------------------------------------------------------------------
# 2) تثبيت اعتماديات Backend (Python) — يحتاج إنترنت فعليًا، متوفر هنا
# ---------------------------------------------------------------------------
if [ -f "backend/requirements.txt" ]; then
    echo ">>> تثبيت اعتماديات Python..."
    pip install --user -r backend/requirements.txt
fi

# ---------------------------------------------------------------------------
# 3) انتظار جاهزية PostgreSQL (الحاوية db)، ثم تفعيل pgvector وتطبيق الـschema
#    مرة واحدة فقط — لا يُعيد إنشاء الجداول إن كانت موجودة بالفعل (IF NOT EXISTS)
# ---------------------------------------------------------------------------
echo ">>> انتظار PostgreSQL..."
for i in $(seq 1 30); do
    if PGPASSWORD=excellence pg_isready -h db -p 5432 -U excellence > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

echo ">>> تفعيل امتدادي pgcrypto و vector (pgvector)..."
PGPASSWORD=excellence psql -h db -U excellence -d excellence_platform -v ON_ERROR_STOP=0 \
    -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" \
    -c "CREATE EXTENSION IF NOT EXISTS vector;"

if [ -f "backend/db/schema_postgresql.sql" ]; then
    echo ">>> تطبيق backend/db/schema_postgresql.sql (مرة واحدة؛ يتجاهل الأخطاء إن كانت الجداول موجودة مسبقًا)..."
    PGPASSWORD=excellence psql -h db -U excellence -d excellence_platform \
        -f backend/db/schema_postgresql.sql || true
fi

# ---------------------------------------------------------------------------
# 4) تأكيد صريح لكل أداة مطلوبة — لا نجاح صامت
# ---------------------------------------------------------------------------
echo ""
echo "=================== ملخص جاهزية البيئة ==================="
python3 --version
java -version
psql --version
gradle --version | grep Gradle
sdkmanager --version
echo "============================================================"
echo ">>> البيئة جاهزة. راجع التعليمات لتشغيل Backend/Android."
