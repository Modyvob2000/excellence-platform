package com.excellence.platform.ui.screens.results

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.excellence.platform.data.local.SessionManager
import com.excellence.platform.data.remote.AttemptOut
import com.excellence.platform.data.remote.ExamsApi
import com.excellence.platform.data.remote.ResultOut
import com.excellence.platform.data.remote.ResultsApi
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

// ---------------------------------------------------------------------------
// Result — نتيجة محاولة واحدة فور إنهائها
// ---------------------------------------------------------------------------

@HiltViewModel
class ResultViewModel @Inject constructor(private val examsApi: ExamsApi) : ViewModel() {
    private val _result = MutableStateFlow<ResultOut?>(null)
    val result: StateFlow<ResultOut?> = _result
    var error by mutableStateOf<String?>(null)
        private set

    fun load(attemptId: Int) {
        viewModelScope.launch {
            try {
                _result.value = examsApi.finish(attemptId)  // idempotent على السيرفر لمحاولة مُنهاة فعلاً
            } catch (e: Exception) {
                error = "تعذّر جلب النتيجة — ستظهر لاحقًا في سجل المحاولات عند توفر الاتصال."
            }
        }
    }
}

@Composable
fun ResultScreen(attemptId: Int, viewModel: ResultViewModel = hiltViewModel()) {
    LaunchedEffect(attemptId) { viewModel.load(attemptId) }
    val result by viewModel.result.collectAsState()

    Column(Modifier.fillMaxSize().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("النتيجة", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(24.dp))
        when {
            viewModel.error != null -> Text(viewModel.error!!, color = MaterialTheme.colorScheme.error)
            result == null -> CircularProgressIndicator()
            else -> {
                val r = result!!
                Text("${r.percentage}%", style = MaterialTheme.typography.displayMedium)
                Spacer(Modifier.height(8.dp))
                Text("الدرجة: ${r.score} من ${r.total_marks}")
                Text("إجابات صحيحة: ${r.correct_count}  —  إجابات خاطئة: ${r.wrong_count}")
                if (r.needs_manual_grading_count > 0) {
                    Spacer(Modifier.height(8.dp))
                    Text("${r.needs_manual_grading_count} سؤال بانتظار تصحيح المعلم يدويًا",
                         color = MaterialTheme.colorScheme.tertiary)
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// History — سجل كل محاولات الطالب
// ---------------------------------------------------------------------------

@HiltViewModel
class HistoryViewModel @Inject constructor(
    private val resultsApi: ResultsApi,
    private val sessionManager: SessionManager,
) : ViewModel() {
    private val _attempts = MutableStateFlow<List<AttemptOut>>(emptyList())
    val attempts: StateFlow<List<AttemptOut>> = _attempts
    var error by mutableStateOf<String?>(null)
        private set

    fun load(studentId: Int) {
        viewModelScope.launch {
            try {
                _attempts.value = resultsApi.history(studentId)
            } catch (e: Exception) {
                error = "تعذّر تحميل السجل — تحقق من الاتصال."
            }
        }
    }
}

@Composable
fun HistoryScreen(viewModel: HistoryViewModel = hiltViewModel()) {
    // ملاحظة: student_id الحقيقي يُستخرج من JWT (claim "sub") عبر SessionManager في
    // نسخة الإنتاج الكاملة؛ هنا placeholder بسيط 0 لتوضيح مسار الاستدعاء.
    LaunchedEffect(Unit) { viewModel.load(0) }
    val attempts by viewModel.attempts.collectAsState()

    Column(Modifier.fillMaxSize()) {
        Text("سجل المحاولات", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(16.dp))
        viewModel.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(16.dp)) }
        LazyColumn {
            items(attempts, key = { it.attempt_id }) { attempt ->
                ListItem(
                    headlineContent = { Text("امتحان #${attempt.exam_id}") },
                    supportingContent = { Text("${attempt.percentage}% — صحيح: ${attempt.correct_count}, خطأ: ${attempt.wrong_count}") },
                )
                Divider()
            }
        }
    }
}
