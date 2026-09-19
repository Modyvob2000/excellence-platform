package com.excellence.platform.ui.screens.importcenter

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.excellence.platform.data.remote.BatchOut
import com.excellence.platform.data.remote.ImportApi
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ImportCenterViewModel @Inject constructor(private val importApi: ImportApi) : ViewModel() {
    private val _lastBatch = MutableStateFlow<BatchOut?>(null)
    val lastBatch: StateFlow<BatchOut?> = _lastBatch
    var isSubmitting by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    /** "استخراج من مصدر" فقط — هذا المسار لا يخترع أي سؤال، ينقل النص كما وضعه المستخدم بالضبط للـbackend. */
    fun importBulkText(text: String) {
        if (text.isBlank()) {
            error = "الصق نص الأسئلة أولًا."
            return
        }
        viewModelScope.launch {
            isSubmitting = true
            error = null
            try {
                _lastBatch.value = importApi.importBulkText(mapOf("text" to text, "lesson_id" to "0"))
            } catch (e: Exception) {
                error = "فشل رفع الدفعة — تحقق من الاتصال بالسيرفر."
            }
            isSubmitting = false
        }
    }
}

@Composable
fun ImportCenterScreen(viewModel: ImportCenterViewModel = hiltViewModel()) {
    var text by remember { mutableStateOf("") }
    val lastBatch by viewModel.lastBatch.collectAsState()

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("مركز الاستيراد الذكي", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(16.dp))
        Text("لصق مجموعة أسئلة (استخراج من مصدر — لا توليد بالذكاء الاصطناعي هنا)")
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = text, onValueChange = { text = it }, modifier = Modifier.fillMaxWidth().height(200.dp),
                           label = { Text("الصق نص الأسئلة هنا") })
        Spacer(Modifier.height(8.dp))
        viewModel.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(onClick = { viewModel.importBulkText(text) }, enabled = !viewModel.isSubmitting,
               modifier = Modifier.fillMaxWidth()) {
            if (viewModel.isSubmitting) CircularProgressIndicator(Modifier.size(20.dp)) else Text("استيراد")
        }
        lastBatch?.let { batch ->
            Spacer(Modifier.height(16.dp))
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("الدفعة: ${batch.batch_number}", style = MaterialTheme.typography.titleMedium)
                    Text("الإجمالي: ${batch.total_questions}")
                    Text("بحاجة لمراجعة: ${batch.needs_review_count}")
                    Text("مكرر محتمل: ${batch.duplicate_count}")
                    Text("بحاجة تصنيف: ${batch.needs_classification_count}")
                }
            }
        }
    }
}
