package com.excellence.platform.data.sync

/**
 * ⚠️ هذا الملف لم يُشغَّل فعليًا في بيئة التطوير الحالية: لا يوجد Kotlin compiler
 * ولا Gradle/Android SDK هنا (تحقّقنا: `which kotlinc gradle` بلا نتيجة). الكود
 * مكتوب بمعيار JUnit4 عادي ولا يعتمد على إطار عمل Android (Robolectric/Instrumentation)،
 * لذا يُفترض أن يعمل بـ`./gradlew test` بمجرد توفر بيئة بها Android Studio/JDK كاملة.
 * لا يُدَّعى هنا أي تشغيل أو نجاح لم يحدث فعليًا.
 */
import com.excellence.platform.data.local.PendingAnswerDao
import com.excellence.platform.data.local.PendingAnswerEntity
import com.excellence.platform.data.remote.ExamsApi
import com.excellence.platform.data.remote.SubmitAnswerRequest
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

private class FakePendingAnswerDao : PendingAnswerDao {
    val storage = mutableListOf<PendingAnswerEntity>()
    override suspend fun insert(answer: PendingAnswerEntity): Long {
        val withId = answer.copy(id = storage.size + 1L)
        storage.add(withId)
        return withId.id
    }
    override suspend fun getUnsynced() = storage.filter { !it.synced }
    override suspend fun update(answer: PendingAnswerEntity) {
        val idx = storage.indexOfFirst { it.id == answer.id }
        if (idx >= 0) storage[idx] = answer
    }
    override suspend fun clearSynced() { storage.removeAll { it.synced } }
}

private class FakeExamsApi(
    private val failWith: Map<Int, Int> = emptyMap(),  // questionId -> HTTP code للفشل
) : ExamsApi by ExamsApiUnsupported() {
    val submittedAnswers = mutableListOf<Int>()
    override suspend fun submitAnswer(attemptId: Int, request: SubmitAnswerRequest) {
        failWith[request.question_id]?.let { code ->
            throw HttpException(Response.error<Unit>(code, okhttp3.ResponseBody.create(null, "")))
        }
        submittedAnswers.add(request.question_id)
    }
}

/** بقية دوال ExamsApi غير مستخدمة في هذا الاختبار — ترمي إن استُدعيت خطأ عن قصد. */
private class ExamsApiUnsupported : ExamsApi {
    override suspend fun create(request: com.excellence.platform.data.remote.ExamCreateRequest) =
        throw NotImplementedError()
    override suspend fun questionsForTaking(examId: Int) = throw NotImplementedError()
    override suspend fun beginAttempt(examId: Int) = throw NotImplementedError()
    override suspend fun submitAnswer(attemptId: Int, request: SubmitAnswerRequest) = throw NotImplementedError()
    override suspend fun finish(attemptId: Int) = throw NotImplementedError()
}

class SyncQueueTest {

    @Test
    fun `successful sync marks answer as synced and clears it`() = runTest {
        val dao = FakePendingAnswerDao()
        dao.insert(PendingAnswerEntity(attemptId = 1, questionId = 10, answerText = "القاهرة", createdAt = 0))
        val queue = SyncQueue(dao, FakeExamsApi())

        val outcome = queue.syncPendingAnswers()

        assertEquals(SyncQueue.SyncOutcome.Success(1), outcome)
        assertEquals(0, dao.storage.size)  // نُظِّف بعد النجاح
    }

    @Test
    fun `permanent conflict (409) is not retried forever and is cleared with failure recorded`() = runTest {
        val dao = FakePendingAnswerDao()
        dao.insert(PendingAnswerEntity(attemptId = 1, questionId = 20, answerText = "إجابة", createdAt = 0))
        val queue = SyncQueue(dao, FakeExamsApi(failWith = mapOf(20 to 409)))

        val outcome = queue.syncPendingAnswers()

        assertEquals(SyncQueue.SyncOutcome.PartialFailure(0, 1), outcome)
        assertEquals(0, dao.storage.size)  // لا تبقى عالقة للأبد رغم فشلها منطقيًا
    }

    @Test
    fun `nothing to sync returns NothingToSync without calling api`() = runTest {
        val dao = FakePendingAnswerDao()
        val api = FakeExamsApi()
        val queue = SyncQueue(dao, api)

        val outcome = queue.syncPendingAnswers()

        assertEquals(SyncQueue.SyncOutcome.NothingToSync, outcome)
        assertEquals(0, api.submittedAnswers.size)
    }
}
