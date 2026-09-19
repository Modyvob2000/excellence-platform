package com.excellence.platform.di

import android.content.Context
import androidx.room.Room
import com.excellence.platform.BuildConfig
import com.excellence.platform.data.local.AppDatabase
import com.excellence.platform.data.local.AuthInterceptor
import com.excellence.platform.data.local.MIGRATION_1_2
import com.excellence.platform.data.local.SessionManager
import com.excellence.platform.data.remote.*
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideSessionManager(@ApplicationContext context: Context): SessionManager =
        SessionManager(context)

    @Provides
    @Singleton
    fun provideOkHttpClient(authInterceptor: AuthInterceptor): OkHttpClient {
        val logging = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY
                    else HttpLoggingInterceptor.Level.NONE  // لا تُسجَّل التفاصيل في الإصدار النهائي
        }
        return OkHttpClient.Builder()
            .addInterceptor(authInterceptor)
            .addInterceptor(logging)
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient): Retrofit {
        val json = Json { ignoreUnknownKeys = true }
        return Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
    }

    @Provides
    @Singleton
    fun provideAuthApi(retrofit: Retrofit): AuthApi = retrofit.create(AuthApi::class.java)

    @Provides
    @Singleton
    fun provideContentApi(retrofit: Retrofit): ContentApi = retrofit.create(ContentApi::class.java)

    @Provides
    @Singleton
    fun provideQuestionsApi(retrofit: Retrofit): QuestionsApi = retrofit.create(QuestionsApi::class.java)

    @Provides
    @Singleton
    fun provideExamsApi(retrofit: Retrofit): ExamsApi = retrofit.create(ExamsApi::class.java)

    @Provides
    @Singleton
    fun provideResultsApi(retrofit: Retrofit): ResultsApi = retrofit.create(ResultsApi::class.java)

    @Provides
    @Singleton
    fun provideImportApi(retrofit: Retrofit): ImportApi = retrofit.create(ImportApi::class.java)

    @Provides
    @Singleton
    fun provideImportFileApi(retrofit: Retrofit): ImportFileApi = retrofit.create(ImportFileApi::class.java)

    @Provides
    @Singleton
    fun provideReviewApi(retrofit: Retrofit): ReviewApi = retrofit.create(ReviewApi::class.java)

    @Provides
    @Singleton
    fun provideAppDatabase(@ApplicationContext context: Context): AppDatabase =
        Room.databaseBuilder(context, AppDatabase::class.java, "excellence_platform.db")
            .addMigrations(MIGRATION_1_2)  // Migration حقيقية وآمنة v1->v2، لا فقد بيانات (انظر Migrations.kt)
            .build()

    @Provides
    fun provideQuestionDao(db: AppDatabase) = db.questionDao()

    @Provides
    fun provideLessonDao(db: AppDatabase) = db.lessonDao()

    @Provides
    fun providePendingAnswerDao(db: AppDatabase) = db.pendingAnswerDao()

    @Provides
    @Singleton
    fun provideQuestionRepository(
        impl: com.excellence.platform.data.repository.QuestionRepositoryImpl,
    ): com.excellence.platform.data.repository.QuestionRepository = impl
}

private fun String.toMediaType() = okhttp3.MediaType.parse(this)!!
