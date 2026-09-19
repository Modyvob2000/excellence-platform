package com.excellence.platform.data.local

import androidx.room.*
import kotlinx.coroutines.flow.Flow

// ============================================================
// Type converters — Room لا يدعم List<String> مباشرة
// ============================================================

class Converters {
    @TypeConverter
    fun fromChoicesList(choices: List<String>): String = choices.joinToString("\u0001")

    @TypeConverter
    fun toChoicesList(raw: String): List<String> = if (raw.isEmpty()) emptyList() else raw.split("\u0001")
}

// ============================================================
// Entities — نسخة محلية مصغّرة تكفي للعرض والعمل بلا اتصال
// ============================================================

@Entity(tableName = "lessons_cache")
data class LessonEntity(
    @PrimaryKey val id: Int,
    val unitId: Int,
    val name: String,
    val lastSyncedAt: Long,
)

@Entity(tableName = "questions_cache")
data class QuestionEntity(
    @PrimaryKey val id: Int,
    val lessonId: Int?,
    val question: String,
    val answer: String?,
    val status: String,
    val approved: Boolean,
    val canonicalType: String?,
    val choices: List<String> = emptyList(),
    val lastSyncedAt: Long,
)

/** إجابة طالب أُدخلت أثناء انقطاع الإنترنت، بانتظار المزامنة (انظر SyncQueue.kt). */
@Entity(tableName = "pending_answers")
data class PendingAnswerEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val attemptId: Int,
    val questionId: Int,
    val answerText: String,
    val createdAt: Long,
    val synced: Boolean = false,
)

// ============================================================
// DAOs
// ============================================================

@Dao
interface LessonDao {
    @Query("SELECT * FROM lessons_cache WHERE unitId = :unitId")
    fun observeByUnit(unitId: Int): Flow<List<LessonEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(lessons: List<LessonEntity>)
}

@Dao
interface QuestionDao {
    @Query("SELECT * FROM questions_cache WHERE lessonId = :lessonId")
    fun observeByLesson(lessonId: Int): Flow<List<QuestionEntity>>

    @Query("SELECT * FROM questions_cache WHERE id = :id")
    suspend fun getById(id: Int): QuestionEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(questions: List<QuestionEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(question: QuestionEntity)
}

@Dao
interface PendingAnswerDao {
    @Insert
    suspend fun insert(answer: PendingAnswerEntity): Long

    @Query("SELECT * FROM pending_answers WHERE synced = 0 ORDER BY createdAt ASC")
    suspend fun getUnsynced(): List<PendingAnswerEntity>

    /** لاستعادة إجابات الطالب عند العودة لسؤال سابق أو إعادة فتح المحاولة بعد انقطاع/إغلاق التطبيق. */
    @Query("SELECT * FROM pending_answers WHERE attemptId = :attemptId ORDER BY createdAt ASC")
    suspend fun getForAttempt(attemptId: Int): List<PendingAnswerEntity>

    /** آخر إجابة محفوظة لسؤال بعينه ضمن نفس المحاولة (upsert منطقي عبر أحدث سجل). */
    @Query("SELECT * FROM pending_answers WHERE attemptId = :attemptId AND questionId = :questionId " +
           "ORDER BY createdAt DESC LIMIT 1")
    suspend fun getLatestForQuestion(attemptId: Int, questionId: Int): PendingAnswerEntity?

    @Update
    suspend fun update(answer: PendingAnswerEntity)

    @Query("DELETE FROM pending_answers WHERE synced = 1")
    suspend fun clearSynced()
}

@Database(
    entities = [LessonEntity::class, QuestionEntity::class, PendingAnswerEntity::class],
    version = 2,
    exportSchema = true,
)
@TypeConverters(Converters::class)
abstract class AppDatabase : RoomDatabase() {
    abstract fun lessonDao(): LessonDao
    abstract fun questionDao(): QuestionDao
    abstract fun pendingAnswerDao(): PendingAnswerDao
}
