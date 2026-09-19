package com.excellence.platform.data.repository

import com.excellence.platform.data.local.PendingAnswerDao
import com.excellence.platform.data.local.PendingAnswerEntity
import com.excellence.platform.data.local.QuestionDao
import com.excellence.platform.data.local.QuestionEntity
import com.excellence.platform.data.remote.QuestionOut
import com.excellence.platform.data.remote.QuestionsApi
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * واجهة قابلة للاستبدال (DI) — تسمح باختبار أي ViewModel يعتمد عليها بمخزن
 * وهمي في الذاكرة (انظر AttemptViewModelTest.kt) دون Room أو Retrofit حقيقيين.
 */
interface QuestionRepository {
    fun observeByLesson(lessonId: Int): Flow<List<QuestionEntity>>
    suspend fun refreshLesson(lessonId: Int): Result<Unit>
    suspend fun getOrFetchQuestion(questionId: Int): QuestionEntity?
    suspend fun queueAnswer(attemptId: Int, questionId: Int, answerText: String)
    suspend fun loadSavedAnswers(attemptId: Int): Map<Int, String>
}

/**
 * Offline-first: الواجهة تقرأ دائمًا من Room (observeByLesson يُصدر فورًا من الكاش
 * المحلي)، وتحاول في الخلفية جلب نسخة أحدث من الـAPI وتحديث الكاش — لا تنتظر
 * الشبكة أبدًا لعرض شيء للمستخدم إن كان متوفرًا محليًا مسبقًا.
 */
@Singleton
class QuestionRepositoryImpl @Inject constructor(
    private val questionDao: QuestionDao,
    private val pendingAnswerDao: PendingAnswerDao,
    private val api: QuestionsApi,
) : QuestionRepository {

    override fun observeByLesson(lessonId: Int): Flow<List<QuestionEntity>> =
        questionDao.observeByLesson(lessonId)

    /** يُستدعى عند توفر الاتصال لتحديث الكاش المحلي — فشل الشبكة هنا لا يكسر الشاشة أبدًا. */
    override suspend fun refreshLesson(lessonId: Int): Result<Unit> = try {
        val remote = api.list(lessonId = lessonId)
        questionDao.upsertAll(remote.map { it.toEntity() })
        Result.success(Unit)
    } catch (e: Exception) {
        Result.failure(e)  // الشاشة تستمر بعرض الكاش القديم — لا كسر لتجربة عدم الاتصال
    }

    /**
     * Offline-first لسؤال بعينه (تُستخدم في شاشة أداء الامتحان): يُرجع النسخة
     * المحلية فورًا إن وُجدت، وإلا يحاول الجلب من الشبكة وتخزينه للاستخدام
     * القادم دون اتصال. إن فشلت الشبكة ولا توجد نسخة محلية، تُرجع null بدل
     * كسر الشاشة بخطأ غير معالج.
     */
    override suspend fun getOrFetchQuestion(questionId: Int): QuestionEntity? {
        questionDao.getById(questionId)?.let { return it }
        return try {
            val remote = api.get(questionId).toEntity()
            questionDao.upsert(remote)
            remote
        } catch (e: Exception) {
            null
        }
    }

    /**
     * حفظ إجابة الطالب: يُخزَّن محليًا في pending_answers فورًا (لا فقد بيانات إن
     * انقطع الاتصال أثناء الحل)، وSyncQueue يتكفّل بالإرسال الفعلي لاحقًا.
     */
    override suspend fun queueAnswer(attemptId: Int, questionId: Int, answerText: String) {
        pendingAnswerDao.insert(
            PendingAnswerEntity(attemptId = attemptId, questionId = questionId,
                                 answerText = answerText, createdAt = System.currentTimeMillis()))
    }

    /** لاستعادة كل إجابات الطالب عند العودة لسؤال أو إعادة فتح شاشة المحاولة (offline أو بعد إعادة تشغيل). */
    override suspend fun loadSavedAnswers(attemptId: Int): Map<Int, String> {
        return pendingAnswerDao.getForAttempt(attemptId)
            .groupBy { it.questionId }
            .mapValues { (_, entries) -> entries.maxBy { it.createdAt }.answerText }
    }

    private fun QuestionOut.toEntity() = QuestionEntity(
        id = id, lessonId = lesson_id, question = question, answer = answer, status = status,
        approved = approved, canonicalType = canonical_type, choices = choices,
        lastSyncedAt = System.currentTimeMillis(),
    )
}
