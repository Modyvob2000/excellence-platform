package com.excellence.platform.data.remote

import kotlinx.serialization.Serializable
import retrofit2.http.*

// ============================================================
// DTOs — يطابقون schemas الـFastAPI (routers/*.py) تمامًا
// ============================================================

@Serializable
data class LoginRequest(val username: String, val password: String)

@Serializable
data class TokenResponse(val access_token: String, val token_type: String = "bearer", val role: String)

@Serializable
data class NodeOut(val id: Int, val name: String, val is_hidden: Boolean)

@Serializable
data class QuestionOut(
    val id: Int, val question: String, val answer: String?, val status: String,
    val approved: Boolean, val canonical_type: String?, val lesson_id: Int?,
    val choices: List<String> = emptyList(),
)

@Serializable
data class QuestionCreateRequest(
    val question: String, val lesson_id: Int, val answer: String? = null,
    val choices: List<String> = emptyList(), val original_question_type: String? = null,
)

@Serializable
data class ExamCreateRequest(
    val name: String, val question_ids: List<Int>, val duration_minutes: Int? = null,
    val shuffle_questions: Boolean = false, val shuffle_choices: Boolean = false,
    val allow_retake: Boolean = false, val is_training: Boolean = false,
)

@Serializable
data class ExamOut(val id: Int, val name: String, val question_ids: List<Int>,
                    val duration_minutes: Int?, val is_training: Boolean)

@Serializable
data class AttemptStartResponse(val attempt_id: Int)

@Serializable
data class SubmitAnswerRequest(val question_id: Int, val answer_text: String)

@Serializable
data class ResultOut(
    val score: Double, val total_marks: Double, val percentage: Double,
    val correct_count: Int, val wrong_count: Int, val needs_manual_grading_count: Int,
)

@Serializable
data class AttemptOut(val attempt_id: Int, val exam_id: Int, val score: Double,
                       val percentage: Double, val correct_count: Int, val wrong_count: Int)

@Serializable
data class BatchOut(
    val batch_number: String, val status: String, val total_questions: Int,
    val needs_review_count: Int, val duplicate_count: Int, val needs_classification_count: Int,
)

@Serializable
data class ReviewItemOut(
    val question_id: Int, val question: String, val answer: String?, val status: String,
    val original_question_type: String?, val source_type: String,
    val duplicate_of_question_id: Int?, val similarity_score: Double?,
)

@Serializable
data class BulkActionRequest(
    val question_ids: List<Int>, val reason: String? = null,
    val new_type_id: Int? = null, val new_lesson_id: Int? = null,
)

@Serializable
data class BulkActionResult(val succeeded: List<Int>, val failed: Map<String, String>)

// ============================================================
// Retrofit interfaces
// ============================================================

interface AuthApi {
    @POST("auth/login")
    suspend fun login(@Body request: LoginRequest): TokenResponse

    @POST("auth/register")
    suspend fun register(@Body request: LoginRequest): TokenResponse
}

interface ContentApi {
    @GET("content/grades")
    suspend fun grades(@Query("stage_id") stageId: Int? = null): List<NodeOut>

    @GET("content/subjects")
    suspend fun subjects(@Query("grade_id") gradeId: Int? = null): List<NodeOut>

    @GET("content/units")
    suspend fun units(@Query("subject_id") subjectId: Int? = null): List<NodeOut>

    @GET("content/lessons")
    suspend fun lessons(@Query("unit_id") unitId: Int? = null): List<NodeOut>
}

interface QuestionsApi {
    @POST("questions")
    suspend fun create(@Body request: QuestionCreateRequest): QuestionOut

    @GET("questions/{id}")
    suspend fun get(@Path("id") id: Int): QuestionOut

    @GET("questions")
    suspend fun list(
        @Query("lesson_id") lessonId: Int? = null,
        @Query("status") status: String? = null,
        @Query("canonical_type") type: String? = null,
    ): List<QuestionOut>

    @GET("questions/search/")
    suspend fun search(@Query("q") query: String): List<QuestionOut>

    @DELETE("questions/{id}")
    suspend fun softDelete(@Path("id") id: Int)

    @POST("questions/{id}/approve")
    suspend fun approve(@Path("id") id: Int)

    @POST("questions/{id}/reject")
    suspend fun reject(@Path("id") id: Int, @Query("reason") reason: String = "")

    @POST("questions/bulk/approve")
    suspend fun bulkApprove(@Body request: BulkActionRequest): BulkActionResult

    @POST("questions/bulk/reject")
    suspend fun bulkReject(@Body request: BulkActionRequest): BulkActionResult

    @POST("questions/bulk/delete")
    suspend fun bulkDelete(@Body request: BulkActionRequest): BulkActionResult

    @POST("questions/bulk/change_type")
    suspend fun bulkChangeType(@Body request: BulkActionRequest): BulkActionResult

    @POST("questions/bulk/change_lesson")
    suspend fun bulkChangeLesson(@Body request: BulkActionRequest): BulkActionResult
}

interface ExamsApi {
    @POST("exams")
    suspend fun create(@Body request: ExamCreateRequest): ExamOut

    @GET("exams/{id}/questions")
    suspend fun questionsForTaking(@Path("id") examId: Int): List<Int>

    @POST("exams/{id}/attempts")
    suspend fun beginAttempt(@Path("id") examId: Int): AttemptStartResponse

    @POST("exams/attempts/{attemptId}/answers")
    suspend fun submitAnswer(@Path("attemptId") attemptId: Int, @Body request: SubmitAnswerRequest)

    @POST("exams/attempts/{attemptId}/finish")
    suspend fun finish(@Path("attemptId") attemptId: Int): ResultOut
}

@Serializable
data class ExamReportOut(
    val exam_id: Int, val attempts_count: Int, val average_percentage: Double,
    val pass_rate: Double, val highest_percentage: Double, val lowest_percentage: Double,
)

interface ResultsApi {
    @GET("results/students/{studentId}/history")
    suspend fun history(@Path("studentId") studentId: Int): List<AttemptOut>

    @GET("results/exams/{examId}/report")
    suspend fun examReport(@Path("examId") examId: Int): ExamReportOut
}

interface ImportApi {
    @POST("import/bulk-text")
    suspend fun importBulkText(@Body body: Map<String, String>): BatchOut

    @GET("import/batches")
    suspend fun batches(): List<BatchOut>

    // رفع PDF/DOCX/XLSX/CSV يستخدم Multipart — انظر ImportFileUploader.kt
}

interface ReviewApi {
    @GET("review/queue")
    suspend fun queue(@Query("status") status: String? = null): List<ReviewItemOut>
}
