package com.excellence.platform.ui.screens.auth

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.excellence.platform.data.local.SessionManager
import com.excellence.platform.data.remote.AuthApi
import com.excellence.platform.data.remote.LoginRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed class LoginUiState {
    data object Idle : LoginUiState()
    data object Loading : LoginUiState()
    data class Error(val message: String) : LoginUiState()
    data object Success : LoginUiState()
}

@HiltViewModel
class LoginViewModel @Inject constructor(
    private val authApi: AuthApi,
    private val sessionManager: SessionManager,
) : ViewModel() {
    private val _state = MutableStateFlow<LoginUiState>(LoginUiState.Idle)
    val state: StateFlow<LoginUiState> = _state

    fun login(username: String, password: String) {
        if (username.isBlank() || password.isBlank()) {
            _state.value = LoginUiState.Error("الرجاء إدخال اسم المستخدم وكلمة المرور.")
            return
        }
        _state.value = LoginUiState.Loading
        viewModelScope.launch {
            try {
                val response = authApi.login(LoginRequest(username, password))
                sessionManager.save(response.access_token, response.role, username)
                _state.value = LoginUiState.Success
            } catch (e: Exception) {
                _state.value = LoginUiState.Error("فشل تسجيل الدخول — تحقق من البيانات أو الاتصال.")
            }
        }
    }
}

@Composable
fun LoginScreen(onLoggedIn: () -> Unit, viewModel: LoginViewModel = hiltViewModel()) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val state by viewModel.state.collectAsState()

    LaunchedEffect(state) {
        if (state is LoginUiState.Success) onLoggedIn()
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("منصة التميز التعليمية", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(24.dp))
        OutlinedTextField(value = username, onValueChange = { username = it },
                           label = { Text("اسم المستخدم") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(value = password, onValueChange = { password = it },
                           label = { Text("كلمة المرور") },
                           visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation(),
                           modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(16.dp))

        if (state is LoginUiState.Error) {
            Text((state as LoginUiState.Error).message, color = MaterialTheme.colorScheme.error)
            Spacer(Modifier.height(8.dp))
        }

        Button(onClick = { viewModel.login(username, password) },
               enabled = state !is LoginUiState.Loading, modifier = Modifier.fillMaxWidth()) {
            if (state is LoginUiState.Loading) CircularProgressIndicator(modifier = Modifier.size(20.dp))
            else Text("تسجيل الدخول")
        }
    }
}
