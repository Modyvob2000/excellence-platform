package com.excellence.platform.ui.screens.admin

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.excellence.platform.data.remote.QuestionsApi
import com.excellence.platform.data.remote.ReviewApi
import com.excellence.platform.data.remote.ReviewItemOut
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ReviewViewModel @Inject constructor(
    private val reviewApi: ReviewApi,
    private val questionsApi: QuestionsApi,
) : ViewModel() {
    private val _items = MutableStateFlow<List<ReviewItemOut>>(emptyList())
    val items: StateFlow<List<ReviewItemOut>> = _items
    var error by mutableStateOf<String?>(null)
        private set

    fun load() {
        viewModelScope.launch {
            try {
                _items.value = reviewApi.queue()
            } catch (e: Exception) {
                error = "تعذّر تحميل قائمة المراجعة."
            }
        }
    }

    /** اعتماد فردي — القرار البشري النهائي دائمًا، لا اعتماد تلقائي في أي مكان بالتطبيق. */
    fun approve(questionId: Int) = viewModelScope.launch {
        try {
            questionsApi.approve(questionId)
            load()
        } catch (e: Exception) {
            error = "فشل الاعتماد — حاول مجددًا."
        }
    }

    fun reject(questionId: Int) = viewModelScope.launch {
        try {
            questionsApi.reject(questionId)
            load()
        } catch (e: Exception) {
            error = "فشل الرفض — حاول مجددًا."
        }
    }
}

@Composable
fun ReviewScreen(viewModel: ReviewViewModel = hiltViewModel()) {
    LaunchedEffect(Unit) { viewModel.load() }
    val items by viewModel.items.collectAsState()

    Column(Modifier.fillMaxSize()) {
        Text("الأسئلة قيد المراجعة", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(16.dp))
        viewModel.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(16.dp)) }
        LazyColumn {
            items(items, key = { it.question_id }) { item ->
                Card(Modifier.fillMaxWidth().padding(8.dp)) {
                    Column(Modifier.padding(12.dp)) {
                        Text(item.question, style = MaterialTheme.typography.bodyLarge)
                        Text("الحالة: ${item.status}", style = MaterialTheme.typography.labelSmall)
                        if (item.duplicate_of_question_id != null) {
                            Text("مكرر محتمل للسؤال #${item.duplicate_of_question_id} " +
                                 "(تشابه ${((item.similarity_score ?: 0.0) * 100).toInt()}%)",
                                 color = MaterialTheme.colorScheme.tertiary,
                                 style = MaterialTheme.typography.labelSmall)
                        }
                        Row(Modifier.padding(top = 8.dp)) {
                            Button(onClick = { viewModel.approve(item.question_id) }) { Text("اعتماد") }
                            Spacer(Modifier.width(8.dp))
                            OutlinedButton(onClick = { viewModel.reject(item.question_id) }) { Text("رفض") }
                        }
                    }
                }
            }
        }
    }
}
