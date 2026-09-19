package com.excellence.platform.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject
import javax.inject.Singleton

private val Context.sessionDataStore by preferencesDataStore(name = "session")

/**
 * تخزين الجلسة (JWT + الدور) محليًا فقط. لا يوجد هنا ولا في أي مكان آخر بالتطبيق
 * أي مفتاح API لمزودي الذكاء الاصطناعي — تلك تبقى في Backend حصرًا (القاعدة الإلزامية).
 */
@Singleton
class SessionManager @Inject constructor(private val context: Context) {
    private object Keys {
        val TOKEN = stringPreferencesKey("jwt_token")
        val ROLE = stringPreferencesKey("user_role")
        val USER_ID = stringPreferencesKey("user_id")
    }

    val token: Flow<String?> = context.sessionDataStore.data.map { it[Keys.TOKEN] }
    val role: Flow<String?> = context.sessionDataStore.data.map { it[Keys.ROLE] }

    suspend fun currentToken(): String? = token.first()

    suspend fun save(token: String, role: String, userId: String) {
        context.sessionDataStore.edit { prefs ->
            prefs[Keys.TOKEN] = token
            prefs[Keys.ROLE] = role
            prefs[Keys.USER_ID] = userId
        }
    }

    suspend fun clear() {
        context.sessionDataStore.edit { it.clear() }
    }

    suspend fun isLoggedIn(): Boolean = currentToken() != null
}

/** يُلحق Authorization: Bearer <jwt> بكل طلب — الـtoken فقط، أبدًا مفتاح AI. */
class AuthInterceptor @Inject constructor(
    private val sessionManager: SessionManager,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val token = kotlinx.coroutines.runBlocking { sessionManager.currentToken() }
        val request = chain.request().newBuilder().apply {
            if (token != null) addHeader("Authorization", "Bearer $token")
        }.build()
        return chain.proceed(request)
    }
}
