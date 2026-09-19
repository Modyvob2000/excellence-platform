package com.excellence.platform.ui.screens.content

import androidx.compose.foundation.clickable
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
import androidx.navigation.NavHostController
import com.excellence.platform.data.remote.ContentApi
import com.excellence.platform.data.remote.NodeOut
import com.excellence.platform.navigation.Routes
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

private sealed class GradesState {
    data object Loading : GradesState()
    data class Loaded(val items: List<NodeOut>) : GradesState()
    data class Error(val message: String) : GradesState()
}

@HiltViewModel
class GradesViewModel @Inject constructor(private val api: ContentApi) : ViewModel() {
    private val _state = MutableStateFlow<GradesState>(GradesState.Loading)
    val state: StateFlow<GradesState> = _state

    init { load() }

    fun load() {
        viewModelScope.launch {
            _state.value = GradesState.Loading
            _state.value = try {
                GradesState.Loaded(api.grades())
            } catch (e: Exception) {
                GradesState.Error("تعذّر تحميل الصفوف — تحقق من الاتصال بالسيرفر.")
            }
        }
    }
}

/** أول شاشة محتوى بعد Home: تعرض كل المراحل/الصفوف العامة القابلة للتوسع (لا تفترض مادة بعينها). */
@Composable
fun GradesScreen(navController: NavHostController, viewModel: GradesViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsState()
    Column(Modifier.fillMaxSize()) {
        Text("الصفوف الدراسية", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(16.dp))
        when (val s = state) {
            is GradesState.Loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
            is GradesState.Error -> Column(Modifier.padding(16.dp)) {
                Text(s.message, color = MaterialTheme.colorScheme.error)
                Button(onClick = { viewModel.load() }) { Text("إعادة المحاولة") }
            }
            is GradesState.Loaded -> LazyColumn {
                items(s.items, key = { it.id }) { grade ->
                    ListItem(headlineContent = { Text(grade.name) },
                             modifier = Modifier.clickable { navController.navigate(Routes.subjects(grade.id)) })
                    Divider()
                }
            }
        }
    }
}
