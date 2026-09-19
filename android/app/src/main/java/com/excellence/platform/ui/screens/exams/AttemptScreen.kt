package com.excellence.platform.ui.screens.exams

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.navigation.NavHostController
import com.excellence.platform.data.local.QuestionEntity
import com.excellence.platform.data.remote.ExamsApi
import com.excellence.platform.data.remote.SubmitAnswerRequest
import com.excellence.platform.data.repository.QuestionRepository
import com.excellence.platform.navigation.Routes
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * حالة الشاشة الكاملة لأداء امتحان: قائمة الأسئلة الكاملة (مُحمَّلة Offline-first عبر
 * QuestionRepository.getOrFetchQuestion)، الفهرس الحالي، وخريطة إجابات الطالب المحفوظة
 * محليًا (تُستعاد فورًا عند التنقل أو إعادة فتح الشاشة، حتى بدون اتصال).
 */
sealed class AttemptUiState {
    data object Loading : AttemptUiState()
    data class InProgress(
        val attemptId: Int,
        val questions: List<QuestionEntity>,   // بالترتيب النهائي (بعد أي عشوائية من السيرفر)
        val currentIndex: Int,
        val answers: Map<Int, String>,         // questionId -> إجابة الطالب الحالية
        val syncStatus: SyncStatus = SyncStatus.SAVED_LOCALLY,
    ) : AttemptUiState()
    data class Finished(val resultAttemptId: Int) : AttemptUiState()
    data class Error(val message: String) : AttemptUiState()
}

enum class SyncStatus { SAVED_LOCALLY, SENT_TO_SERVER, SEND_FAILED_WILL_RETRY }

@HiltViewModel
class AttemptViewModel @Inject constructor(
    private val examsApi: ExamsApi,
    private val questionRepository: QuestionRepository,
) : ViewModel() {
    private val _state = MutableStateFlow<AttemptUiState>(AttemptUiState.Loading)
    val state: StateFlow<AttemptUiState> = _state

    fun start(examId: Int) {
        viewModelScope.launch {
            _state.value = AttemptUiState.Loading
            try {
                val questionIds = examsApi.questionsForTaking(examId)
                val started = examsApi.beginAttempt(examId)

                // Offline-first: كل سؤال يُجلب من الكاش المحلي فورًا إن وُجد، وإلا من الشبكة.
                val questions = questionIds.mapNotNull { questionRepository.getOrFetchQuestion(it) }
                if (questions.isEmpty()) {
                    _state.value = AttemptUiState.Error(
                        "تعذّر تحميل أي سؤال — لا يوجد اتصال ولا نسخة محفوظة محليًا.")
                    return@launch
                }

                // استعادة أي إجابات محفوظة مسبقًا لهذه المحاولة (مفيد بعد إغلاق التطبيق فجأة أو انقطاع الاتصال)
                val savedAnswers = questionRepository.loadSavedAnswers(started.attempt_id)

                _state.value = AttemptUiState.InProgress(
                    attemptId = started.attempt_id, questions = questions,
                    currentIndex = 0, answers = savedAnswers)
            } catch (e: Exception) {
                _state.value = AttemptUiState.Error(
                    "تعذّر بدء المحاولة — تحقق من الاتصال أو صلاحية إعادة المحاولة.")
            }
        }
    }

    /**
     * حفظ إجابة السؤال الحالي: يُكتب فورًا في State (لا فقد عند التنقل) وفي
     * Room عبر queueAnswer (لا فقد عند إغلاق التطبيق/انقطاع الاتصال). محاولة
     * إرسال فورية للسيرفر إن كان متصلًا؛ فشلها لا يمنع الطالب من الاستمرار —
     * SyncQueue (retry/backoff) يتكفّل بها لاحقًا دون أي فقد للإجابة نفسها.
     */
    fun saveAnswer(questionId: Int, answerText: String) {
        val current = _state.value as? AttemptUiState.InProgress ?: return
        _state.value = current.copy(
            answers = current.answers + (questionId to answerText),
            syncStatus = SyncStatus.SAVED_LOCALLY,
        )
        viewModelScope.launch {
            questionRepository.queueAnswer(current.attemptId, questionId, answerText)
            try {
                examsApi.submitAnswer(current.attemptId, SubmitAnswerRequest(questionId, answerText))
                updateSyncStatus(SyncStatus.SENT_TO_SERVER)
            } catch (e: Exception) {
                // متروك لـSyncQueue (retry/backoff) — الإجابة محفوظة محليًا بالفعل، لا فقد بيانات.
                updateSyncStatus(SyncStatus.SEND_FAILED_WILL_RETRY)
            }
        }
    }

    private fun updateSyncStatus(status: SyncStatus) {
        val current = _state.value as? AttemptUiState.InProgress ?: return
        _state.value = current.copy(syncStatus = status)
    }

    fun goToNext() {
        val current = _state.value as? AttemptUiState.InProgress ?: return
        val nextIndex = current.currentIndex + 1
        if (nextIndex < current.questions.size) {
            _state.value = current.copy(currentIndex = nextIndex)
        } else {
            finish(current.attemptId)
        }
    }

    fun goToPrevious() {
        val current = _state.value as? AttemptUiState.InProgress ?: return
        if (current.currentIndex > 0) {
            _state.value = current.copy(currentIndex = current.currentIndex - 1)
        }
    }

    fun isLastQuestion(): Boolean {
        val current = _state.value as? AttemptUiState.InProgress ?: return false
        return current.currentIndex == current.questions.size - 1
    }

    private fun finish(attemptId: Int) {
        viewModelScope.launch {
            try {
                examsApi.finish(attemptId)
                _state.value = AttemptUiState.Finished(attemptId)
            } catch (e: Exception) {
                // الإجابات كلها محفوظة محليًا وسليمة؛ فقط طلب "الإنهاء" نفسه فشل شبكيًا.
                _state.value = AttemptUiState.Error(
                    "انتُهي من كل الأسئلة وحُفظت إجاباتك، لكن تعذّر إرسال الإنهاء الآن — " +
                    "سيُعاد تلقائيًا عند توفر الاتصال. يمكنك متابعة سجل محاولاتك لاحقًا.")
            }
        }
    }
}

@Composable
fun AttemptScreen(navController: NavHostController, examId: Int, viewModel: AttemptViewModel = hiltViewModel()) {
    LaunchedEffect(examId) { viewModel.start(examId) }
    val state by viewModel.state.collectAsState()

    when (val s = state) {
        is AttemptUiState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        is AttemptUiState.Error -> Column(Modifier.fillMaxSize().padding(16.dp)) {
            Text(s.message, color = MaterialTheme.colorScheme.error)
        }
        is AttemptUiState.Finished -> LaunchedEffect(s) {
            navController.navigate(Routes.result(s.resultAttemptId))
        }
        is AttemptUiState.InProgress -> AttemptBody(state = s, viewModel = viewModel)
    }
}

@Composable
private fun AttemptBody(state: AttemptUiState.InProgress, viewModel: AttemptViewModel) {
    val question = state.questions[state.currentIndex]
    val currentAnswer = state.answers[question.id] ?: ""

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("السؤال ${state.currentIndex + 1} من ${state.questions.size}",
                 style = MaterialTheme.typography.titleMedium)
            SyncStatusIndicator(state.syncStatus)
        }
        question.canonicalType?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
        }
        Spacer(Modifier.height(12.dp))
        Text(question.question, style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.height(16.dp))

        QuestionAnswerInput(
            question = question, currentAnswer = currentAnswer,
            onAnswerChange = { viewModel.saveAnswer(question.id, it) },
        )

        Spacer(Modifier.weight(1f))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            OutlinedButton(onClick = { viewModel.goToPrevious() }, enabled = state.currentIndex > 0) {
                Text("السابق")
            }
            Button(onClick = { viewModel.goToNext() }) {
                Text(if (viewModel.isLastQuestion()) "إنهاء الامتحان" else "التالي")
            }
        }
    }
}

@Composable
private fun SyncStatusIndicator(status: SyncStatus) {
    val (label, color) = when (status) {
        SyncStatus.SAVED_LOCALLY -> "محفوظة محليًا" to MaterialTheme.colorScheme.outline
        SyncStatus.SENT_TO_SERVER -> "أُرسلت للسيرفر" to MaterialTheme.colorScheme.primary
        SyncStatus.SEND_FAILED_WILL_RETRY -> "بانتظار الاتصال" to MaterialTheme.colorScheme.tertiary
    }
    Text(label, style = MaterialTheme.typography.labelSmall, color = color)
}

/** يعرض واجهة الإدخال المناسبة حسب canonical_type القادم فعليًا من الـBackend. */
@Composable
private fun QuestionAnswerInput(
    question: QuestionEntity, currentAnswer: String, onAnswerChange: (String) -> Unit,
) {
    when (question.canonicalType) {
        "MCQ" -> Column(Modifier.selectableGroup()) {
            question.choices.forEach { choice ->
                Row(
                    Modifier.fillMaxWidth()
                        .selectable(selected = currentAnswer == choice, onClick = { onAnswerChange(choice) }),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    RadioButton(selected = currentAnswer == choice, onClick = { onAnswerChange(choice) })
                    Text(choice, modifier = Modifier.padding(start = 8.dp))
                }
            }
        }

        "TRUE_FALSE" -> Column(Modifier.selectableGroup()) {
            listOf("صح", "خطأ").forEach { option ->
                Row(
                    Modifier.fillMaxWidth()
                        .selectable(selected = currentAnswer == option, onClick = { onAnswerChange(option) }),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    RadioButton(selected = currentAnswer == option, onClick = { onAnswerChange(option) })
                    Text(option, modifier = Modifier.padding(start = 8.dp))
                }
            }
        }

        // كل الأنواع الأخرى (TERM/WHO_IS/WHY/COMPLETE/MAP/RELATION/WHAT_HAPPENS/SHORT_ANSWER/ESSAY/OTHER):
        // إدخال نصي حر — بعضها يُصحَّح تلقائيًا بالتشابه وبعضها يحتاج مراجعة معلم يدويًا (exam_engine.py).
        else -> OutlinedTextField(
            value = currentAnswer, onValueChange = onAnswerChange,
            label = { Text("إجابتك") }, modifier = Modifier.fillMaxWidth(),
            minLines = if (question.canonicalType == "ESSAY") 5 else 1,
        )
    }
}
