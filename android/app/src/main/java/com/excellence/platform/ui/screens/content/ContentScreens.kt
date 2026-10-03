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

sealed class ListState {
    data object Loading : ListState()
    data class Loaded(val items: List<NodeOut>) : ListState()
    data class Error(val message: String) : ListState()
}

@HiltViewModel
class NodeListViewModel @Inject constructor(private val api: ContentApi) : ViewModel() {
    private val _state = MutableStateFlow<ListState>(ListState.Loading)
    val state: StateFlow<ListState> = _state

    fun loadSubjects(gradeId: Int) = load { api.subjects(gradeId) }
    fun loadUnits(subjectId: Int) = load { api.units(subjectId) }
    fun loadLessons(unitId: Int) = load { api.lessons(unitId) }

    private fun load(fetch: suspend () -> List<NodeOut>) {
        viewModelScope.launch {
            _state.value = ListState.Loading
            _state.value = try {
                ListState.Loaded(fetch())
            } catch (e: Exception) {
                ListState.Error("تعذّر تحميل القائمة — تحقق من الاتصال.")
            }
        }
    }
}

@Composable
private fun NodeListBody(state: ListState, onClick: (NodeOut) -> Unit) {
    when (state) {
        is ListState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        is ListState.Error -> Text(state.message, modifier = Modifier.padding(16.dp))
        is ListState.Loaded -> LazyColumn {
            items(state.items) { node ->
                ListItem(headlineContent = { Text(node.name) },
                          modifier = Modifier.clickable { onClick(node) })
                Divider()
            }
        }
    }
}

@Composable
fun SubjectsScreen(navController: NavHostController, gradeId: Int,
                    viewModel: NodeListViewModel = hiltViewModel()) {
    LaunchedEffect(gradeId) { viewModel.loadSubjects(gradeId) }
    val state by viewModel.state.collectAsState()
    Column(Modifier.fillMaxSize()) {
        Text("المواد", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(16.dp))
        NodeListBody(state) { navController.navigate(Routes.units(it.id)) }
    }
}

@Composable
fun UnitsScreen(navController: NavHostController, subjectId: Int,
                viewModel: NodeListViewModel = hiltViewModel()) {
    LaunchedEffect(subjectId) { viewModel.loadUnits(subjectId) }
    val state by viewModel.state.collectAsState()
    Column(Modifier.fillMaxSize()) {
        Text("الوحدات", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(16.dp))
        NodeListBody(state) { navController.navigate(Routes.lessons(it.id)) }
    }
}

@Composable
fun LessonsScreen(navController: NavHostController, unitId: Int,
                   viewModel: NodeListViewModel = hiltViewModel()) {
    LaunchedEffect(unitId) { viewModel.loadLessons(unitId) }
    val state by viewModel.state.collectAsState()
    Column(Modifier.fillMaxSize()) {
        Text("الدروس", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(16.dp))
        NodeListBody(state) { navController.navigate(Routes.questions(it.id)) }
    }
}
