package com.excellence.platform.ui.screens.admin

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.navigation.NavHostController
import com.excellence.platform.data.local.SessionManager
import com.excellence.platform.navigation.Routes
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class AdminViewModel @Inject constructor(private val sessionManager: SessionManager) : ViewModel() {
    fun logout(onDone: () -> Unit) {
        viewModelScope.launch {
            sessionManager.clear()  // يمسح JWT محليًا فقط — لا سر آخر مخزَّن أصلًا
            onDone()
        }
    }
}

@Composable
fun AdminScreen(navController: NavHostController, viewModel: AdminViewModel = hiltViewModel()) {
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("لوحة الإدارة", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(16.dp))

        Button(onClick = { navController.navigate(Routes.IMPORT_CENTER) }, modifier = Modifier.fillMaxWidth()) {
            Text("مركز الاستيراد الذكي")
        }
        Spacer(Modifier.height(8.dp))
        Button(onClick = { navController.navigate(Routes.REVIEW) }, modifier = Modifier.fillMaxWidth()) {
            Text("مراجعة الأسئلة")
        }
        Spacer(Modifier.height(8.dp))
        Button(onClick = { navController.navigate(Routes.IMPORT_HISTORY) }, modifier = Modifier.fillMaxWidth()) {
            Text("سجل الاستيراد")
        }

        Spacer(Modifier.weight(1f))
        Divider()
        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = { viewModel.logout { navController.navigate(Routes.LOGIN) { popUpTo(0) } } },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("تسجيل الخروج") }
    }
}
