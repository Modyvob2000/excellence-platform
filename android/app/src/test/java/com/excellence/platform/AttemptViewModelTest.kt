package com.excellence.platform.ui.screens.exams

/**
 * ⚠️ لم يُشغَّل فعليًا في هذه البيئة (لا Kotlin compiler ولا Gradle/Android SDK هنا —
 * تحقّقنا مسبقًا بـ`which kotlinc gradle`). مكتوب بمعيار JUnit4 + kotlinx-coroutines-test
 * القياسي لاختبار ViewModel على JVM بدون Robolectric، ويُفترض أن يعمل بـ`./gradlew test`
 * بمجرد توفر بيئة كاملة. لا يُدَّعى هنا أي تشغيل أو نجاح لم يحدث فعليًا.
 */
import com.excellence.platform.data.local.QuestionEntity
import com.excellence.platform.data.remote.AttemptStartResponse
import com.excellence.platform.data.remote.ExamsApi
import com.excellence.platform.data.remote.ResultOut
import com.excellence.platform.data.remote.SubmitAnswerRequest
import com.excellence.platform.data.repository.QuestionRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

private class FakeExamsApi : ExamsApi {
    var shouldFailSubmit = false
    var shouldFailFinish = false
    val submitted = mutableListOf<Pair<Int, String>>()

    override suspend fun create(request: com.excellence.platform.data.remote.ExamCreateRequest) =
        throw NotImplementedError()

    override suspend fun questionsForTaking(examId: Int) = listOf(101, 102)

    override suspend fun beginAttempt(examId: Int) = AttemptStartResponse(attempt_id = 777)

    override suspend fun submitAnswer(attemptId: Int, request: SubmitAnswerRequest) {
        if (shouldFailSubmit) throw RuntimeException("network down")
        submitted.add(request.question_id to request.answer_text)
    }

    override suspend fun finish(attemptId: Int): ResultOut {
        if (shouldFailFinish) throw RuntimeException("network down")
        return ResultOut(score = 1.0, total_marks = 2.0, percentage = 50.0,
                          correct_count = 1, wrong_count = 1, needs_manual_grading_count = 0)
    }
}

private class FakeQuestionRepository(
    private val questions: Map<Int, QuestionEntity>,
    private var savedAnswers: Map<Int, String> = emptyMap(),
) : QuestionRepository {
    val queued = mutableListOf<Triple<Int, Int, String>>()

    override suspend fun getOrFetchQuestion(questionId: Int): QuestionEntity? = questions[questionId]

    override suspend fun queueAnswer(attemptId: Int, questionId: Int, answerText: String) {
        queued.add(Triple(attemptId, questionId, answerText))
    }

    override suspend fun loadSavedAnswers(attemptId: Int): Map<Int, String> = savedAnswers
}

private fun mkQuestion(id: Int, type: String, choices: List<String> = emptyList()) = QuestionEntity(
    id = id, lessonId = 1, question = "سؤال $id", answer = null, status = "APPROVED",
    approved = true, canonicalType = type, choices = choices, lastSyncedAt = 0L,
)

@OptIn(ExperimentalCoroutinesApi::class)
class AttemptViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setUp() { Dispatchers.setMain(dispatcher) }

    @After
    fun tearDown() { Dispatchers.resetMain() }

    @Test
    fun `start loads questions and restores saved answers`() = runTest {
        val questions = mapOf(101 to mkQuestion(101, "MCQ", listOf("أ", "ب")), 102 to mkQuestion(102, "TRUE_FALSE"))
        val repo = FakeQuestionRepository(questions, savedAnswers = mapOf(101 to "أ"))
        val vm = AttemptViewModel(FakeExamsApi(), repo)

        vm.start(examId = 5)
        dispatcher.scheduler.advanceUntilIdle()

        val state = vm.state.value as AttemptUiState.InProgress
        assertEquals(2, state.questions.size)
        assertEquals("أ", state.answers[101])   // الإجابة المحفوظة مسبقًا استُعيدت فعليًا
    }

    @Test
    fun `saving an answer updates state immediately and queues locally`() = runTest {
        val questions = mapOf(101 to mkQuestion(101, "MCQ", listOf("أ", "ب")))
        val repo = FakeQuestionRepository(questions)
        val vm = AttemptViewModel(FakeExamsApi(), repo)
        vm.start(examId = 5)
        dispatcher.scheduler.advanceUntilIdle()

        vm.saveAnswer(101, "ب")
        // التحديث في State فوري (متزامن) قبل أي انتظار للـcoroutine الشبكي
        val stateRightAfter = vm.state.value as AttemptUiState.InProgress
        assertEquals("ب", stateRightAfter.answers[101])

        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, repo.queued.size)  // حُفظت محليًا في Room عبر queueAnswer
    }

    @Test
    fun `network failure while saving does not lose the answer`() = runTest {
        val questions = mapOf(101 to mkQuestion(101, "MCQ", listOf("أ", "ب")))
        val repo = FakeQuestionRepository(questions)
        val api = FakeExamsApi().apply { shouldFailSubmit = true }
        val vm = AttemptViewModel(api, repo)
        vm.start(examId = 5)
        dispatcher.scheduler.advanceUntilIdle()

        vm.saveAnswer(101, "ب")
        dispatcher.scheduler.advanceUntilIdle()

        val state = vm.state.value as AttemptUiState.InProgress
        assertEquals("ب", state.answers[101])              // الإجابة موجودة رغم فشل الإرسال
        assertEquals(1, repo.queued.size)                    // محفوظة محليًا لإعادة المحاولة عبر SyncQueue
        assertEquals(SyncStatus.SEND_FAILED_WILL_RETRY, state.syncStatus)
    }

    @Test
    fun `navigation moves forward and backward without losing answers`() = runTest {
        val questions = mapOf(101 to mkQuestion(101, "MCQ", listOf("أ")), 102 to mkQuestion(102, "TRUE_FALSE"))
        val repo = FakeQuestionRepository(questions)
        val vm = AttemptViewModel(FakeExamsApi(), repo)
        vm.start(examId = 5)
        dispatcher.scheduler.advanceUntilIdle()

        vm.saveAnswer(101, "أ")
        dispatcher.scheduler.advanceUntilIdle()
        vm.goToNext()
        var state = vm.state.value as AttemptUiState.InProgress
        assertEquals(1, state.currentIndex)

        vm.goToPrevious()
        state = vm.state.value as AttemptUiState.InProgress
        assertEquals(0, state.currentIndex)
        assertEquals("أ", state.answers[101])  // الإجابة السابقة لم تُفقد بالتنقل
    }

    @Test
    fun `finishing on last question transitions to Finished state`() = runTest {
        val questions = mapOf(101 to mkQuestion(101, "MCQ", listOf("أ")))
        val repo = FakeQuestionRepository(questions)
        val vm = AttemptViewModel(FakeExamsApi(), repo)
        vm.start(examId = 5)
        dispatcher.scheduler.advanceUntilIdle()

        vm.saveAnswer(101, "أ")
        dispatcher.scheduler.advanceUntilIdle()
        vm.goToNext()  // آخر سؤال -> ينهي المحاولة
        dispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.state.value is AttemptUiState.Finished)
    }

    @Test
    fun `finish failure keeps answers safe and reports retry message`() = runTest {
        val questions = mapOf(101 to mkQuestion(101, "TRUE_FALSE"))
        val repo = FakeQuestionRepository(questions)
        val api = FakeExamsApi().apply { shouldFailFinish = true }
        val vm = AttemptViewModel(api, repo)
        vm.start(examId = 5)
        dispatcher.scheduler.advanceUntilIdle()

        vm.saveAnswer(101, "صح")
        dispatcher.scheduler.advanceUntilIdle()
        vm.goToNext()
        dispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.state.value is AttemptUiState.Error)
        assertEquals(1, repo.queued.size)  // الإجابة لا تزال محفوظة رغم فشل الإنهاء
    }

    @Test
    fun `empty question list surfaces a clear offline error instead of crashing`() = runTest {
        val repo = FakeQuestionRepository(emptyMap())
        val vm = AttemptViewModel(FakeExamsApi(), repo)
        vm.start(examId = 5)
        dispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.state.value is AttemptUiState.Error)
    }
}
