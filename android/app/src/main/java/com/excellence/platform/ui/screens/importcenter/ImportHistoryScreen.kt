package com.excellence.platform.ui.screens.importcenter

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
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
class ImportHistoryViewModel @Inject constructor(private val importApi: ImportApi) : ViewModel() {
    private val _batches = MutableStateFlow<List<BatchOut>>(emptyList())
    val batches: StateFlow<List<BatchOut>> = _batches
    var error by mutableStateOf<String?>(null)
        private set

    init {
        viewModelScope.launch {
            try {
                _batches.value = importApi.batches()
            } catch (e: Exception) {
                error = "تعذّر تحميل سجل الاستيراد."
            }
        }
    }
}

@Composable
fun ImportHistoryScreen(viewModel: ImportHistoryViewModel = hiltViewModel()) {
    val batches by viewModel.batches.collectAsState()
    Column(Modifier.fillMaxSize()) {
        Text("سجل عمليات الاستيراد", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(16.dp))
        viewModel.error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(16.dp)) }
        LazyColumn {
            items(batches, key = { it.batch_number }) { b ->
                ListItem(
                    headlineContent = { Text(b.batch_number) },
                    supportingContent = { Text("${b.status} — إجمالي ${b.total_questions}, مراجعة ${b.needs_review_count}, تكرار ${b.duplicate_count}") },
                )
                Divider()
            }
        }
    }
}
