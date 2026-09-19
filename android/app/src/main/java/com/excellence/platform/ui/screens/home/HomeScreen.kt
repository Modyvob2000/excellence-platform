package com.excellence.platform.ui.screens.home

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.navigation.NavHostController
import com.excellence.platform.data.local.SessionManager
import com.excellence.platform.navigation.Routes
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(val sessionManager: SessionManager) : ViewModel()

/** القائمة الرئيسية تختلف حسب الدور — الطالب يرى المحتوى فقط، الإداري يرى أدوات إضافية. */
@Composable
fun HomeScreen(navController: NavHostController, viewModel: HomeViewModel = hiltViewModel()) {
    val role by viewModel.sessionManager.role.collectAsState(initial = null)

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("الرئيسية", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(16.dp))

        Button(onClick = { navController.navigate(Routes.GRADES) }, modifier = Modifier.fillMaxWidth()) {
            Text("المواد الدراسية")
        }
        Spacer(Modifier.height(8.dp))
        Button(onClick = { navController.navigate(Routes.HISTORY) }, modifier = Modifier.fillMaxWidth()) {
            Text("سجل محاولاتي")
        }

        if (role in listOf("TEACHER", "ADMIN", "SUPER_ADMIN", "REVIEWER")) {
            Spacer(Modifier.height(24.dp))
            Text("أدوات الإدارة", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            Button(onClick = { navController.navigate(Routes.IMPORT_CENTER) }, modifier = Modifier.fillMaxWidth()) {
                Text("مركز الاستيراد الذكي")
            }
            Spacer(Modifier.height(8.dp))
            Button(onClick = { navController.navigate(Routes.REVIEW) }, modifier = Modifier.fillMaxWidth()) {
                Text("مراجعة الأسئلة")
            }
        }
        if (role in listOf("ADMIN", "SUPER_ADMIN")) {
            Spacer(Modifier.height(8.dp))
            Button(onClick = { navController.navigate(Routes.ADMIN) }, modifier = Modifier.fillMaxWidth()) {
                Text("لوحة الإدارة")
            }
        }
    }
}
