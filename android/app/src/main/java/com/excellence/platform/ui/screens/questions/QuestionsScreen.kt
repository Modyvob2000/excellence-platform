package com.excellence.platform.ui.screens.questions

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.excellence.platform.data.local.QuestionEntity
import com.excellence.platform.data.repository.QuestionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class QuestionsViewModel @Inject constructor(
    private val repository: QuestionRepository,
) : ViewModel() {
    private var currentLessonId: Int = -1
    lateinit var questions: StateFlow<List<QuestionEntity>>
        private set

    var isRefreshing by mutableStateOf(false)
        private set
    var refreshError by mutableStateOf<String?>(null)
        private set

    fun bind(lessonId: Int) {
        if (currentLessonId == lessonId) return
        currentLessonId = lessonId
        // Offline-first: يُصدر فورًا من Room؛ لا ننتظر الشبكة لعرض شيء متوفر محليًا مسبقًا.
        questions = repository.observeByLesson(lessonId)
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
        refresh(lessonId)
    }

    fun refresh(lessonId: Int = currentLessonId) {
        viewModelScope.launch {
            isRefreshing = true
            refreshError = repository.refreshLesson(lessonId).exceptionOrNull()
                ?.let { "تعذّر التحديث من السيرفر — يُعرض آخر نسخة محفوظة محليًا." }
            isRefreshing = false
        }
    }
}

/** يعرض الأسئلة المعتمدة فقط للطالب (approved=true)؛ المعلم/المراجع يرى الكل عبر شاشة المراجعة المنفصلة. */
@Composable
fun QuestionsScreen(lessonId: Int, viewModel: QuestionsViewModel = hiltViewModel()) {
    LaunchedEffect(lessonId) { viewModel.bind(lessonId) }
    val questions by viewModel.questions.collectAsState()
    val approvedOnly = questions.filter { it.approved }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("بنك الأسئلة", style = MaterialTheme.typography.headlineSmall)
            if (viewModel.isRefreshing) CircularProgressIndicator(Modifier.size(20.dp))
        }
        viewModel.refreshError?.let {
            Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(horizontal = 16.dp))
        }
        if (approvedOnly.isEmpty() && !viewModel.isRefreshing) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("لا توجد أسئلة معتمدة لهذا الدرس بعد.")
            }
        } else {
            LazyColumn {
                items(approvedOnly, key = { it.id }) { q ->
                    Card(Modifier.fillMaxWidth().padding(8.dp)) {
                        Column(Modifier.padding(12.dp)) {
                            Text(q.question, style = MaterialTheme.typography.bodyLarge)
                            q.canonicalType?.let {
                                Text(it, style = MaterialTheme.typography.labelSmall,
                                     color = MaterialTheme.colorScheme.primary)
                            }
                        }
                    }
                }
            }
        }
    }
}
