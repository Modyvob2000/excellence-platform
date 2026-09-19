package com.excellence.platform.data.local

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

/**
 * v1 -> v2: أضاف عمود `choices` إلى questions_cache (كان مفقودًا في v1، أُضيف
 * لدعم عرض اختيارات MCQ في شاشة أداء الامتحان — Quiz Attempt).
 *
 * Migration حقيقية وآمنة: تُبقي كل الصفوف الموجودة فعليًا (lessons_cache،
 * questions_cache، pending_answers) بدون فقد أي بيانات محلية للمستخدم —
 * لا يوجد DROP TABLE ولا إعادة إنشاء، فقط ALTER TABLE ADD COLUMN بقيمة
 * افتراضية آمنة ('' فارغة، تعني "لا اختيارات محفوظة بعد" حتى يُعاد المزامنة
 * من السيرفر عبر refreshLesson/getOrFetchQuestion).
 *
 * ⚠️ لم تُشغَّل فعليًا في هذه البيئة (لا Android SDK/Gradle لتشغيل اختبار Room
 * migration حقيقي عبر MigrationTestHelper). الاستعلام السفلي (ALTER TABLE)
 * صياغة SQLite قياسية صحيحة ومباشرة، ويُوصى بتشغيل
 * androidx.room:room-testing (MigrationTestHelper) عند توفر بيئة كاملة
 * للتحقق النهائي قبل الإصدار (خطوة موثّقة في docs/FINAL_READINESS_REPORT.md).
 */
val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL("ALTER TABLE questions_cache ADD COLUMN choices TEXT NOT NULL DEFAULT ''")
    }
}
