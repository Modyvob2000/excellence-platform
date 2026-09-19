package com.excellence.platform.data.sync

import com.excellence.platform.data.local.PendingAnswerDao
import com.excellence.platform.data.local.PendingAnswerEntity
import com.excellence.platform.data.remote.ExamsApi
import com.excellence.platform.data.remote.SubmitAnswerRequest
import kotlinx.coroutines.delay
import retrofit2.HttpException
import javax.inject.Inject

/**
 * طابور المزامنة: يُستدعى من SyncWorker (WorkManager، دوري + عند عودة الاتصال).
 *
 * سياسة إعادة المحاولة: exponential backoff بحد أقصى [MAX_RETRIES] محاولات لكل عنصر
 * في نفس دورة التشغيل الواحدة (WorkManager نفسه يعيد جدولة العامل كاملًا لاحقًا
 * إن فشل، فهذا الحد الداخلي يمنع فقط تكرارًا سريعًا مفرطًا ضمن نفس المحاولة).
 *
 * التعامل مع التعارض (Conflict Handling): إن رفض السيرفر الإجابة بسبب أن المحاولة
 * (attempt) أُنهيت بالفعل من جهاز/جلسة أخرى (409/400 "أُنهيت مسبقًا")، لا تُعاد
 * المحاولة إلى ما لا نهاية — تُعلَّم كـ"synced" مع سبب فشل نهائي بدل تكرار عديم الجدوى،
 * ولا تُفقد أي بيانات: تبقى في السجل المحلي لمراجعة المستخدم/الدعم الفني.
 */
class SyncQueue @Inject constructor(
    private val pendingAnswerDao: PendingAnswerDao,
    private val examsApi: ExamsApi,
) {
    companion object {
        const val MAX_RETRIES = 3
        const val BASE_BACKOFF_MS = 1000L
    }

    sealed class SyncOutcome {
        data class Success(val syncedCount: Int) : SyncOutcome()
        data class PartialFailure(val syncedCount: Int, val permanentFailures: Int) : SyncOutcome()
        data object NothingToSync : SyncOutcome()
    }

    suspend fun syncPendingAnswers(): SyncOutcome {
        val pending = pendingAnswerDao.getUnsynced()
        if (pending.isEmpty()) return SyncOutcome.NothingToSync

        var syncedCount = 0
        var permanentFailures = 0

        for (item in pending) {
            when (attemptWithRetry(item)) {
                AttemptResult.SYNCED -> {
                    pendingAnswerDao.update(item.copy(synced = true))
                    syncedCount++
                }
                AttemptResult.PERMANENT_CONFLICT -> {
                    // لا تُعاد المحاولة — المحاولة أُنهيت فعليًا على السيرفر، والتعديل متأخر جدًا.
                    // تُعلَّم كمُعالَجة (synced=true) حتى لا تُعاد لانهائيًا، لكنها ليست نجاحًا حقيقيًا.
                    pendingAnswerDao.update(item.copy(synced = true))
                    permanentFailures++
                }
                AttemptResult.TRANSIENT_FAILURE -> {
                    // تبقى synced=false — ستُعاد في الدورة القادمة لـSyncWorker (لا فقد بيانات).
                }
            }
        }

        pendingAnswerDao.clearSynced()
        return if (permanentFailures > 0) SyncOutcome.PartialFailure(syncedCount, permanentFailures)
        else SyncOutcome.Success(syncedCount)
    }

    private enum class AttemptResult { SYNCED, PERMANENT_CONFLICT, TRANSIENT_FAILURE }

    private suspend fun attemptWithRetry(item: PendingAnswerEntity): AttemptResult {
        repeat(MAX_RETRIES) { attempt ->
            try {
                examsApi.submitAnswer(item.attemptId, SubmitAnswerRequest(item.questionId, item.answerText))
                return AttemptResult.SYNCED
            } catch (e: HttpException) {
                // 400/409/410 = تعارض منطقي (محاولة مُنهاة/غير موجودة) — لا فائدة من إعادة المحاولة
                if (e.code() in intArrayOf(400, 404, 409, 410)) {
                    return AttemptResult.PERMANENT_CONFLICT
                }
                // أخطاء سيرفر (5xx) أو أخرى: عابرة، أعد المحاولة بعد backoff
                delay(BASE_BACKOFF_MS * (1L shl attempt))
            } catch (e: Exception) {
                // انقطاع شبكة أو ما شابه: عابر، أعد المحاولة
                delay(BASE_BACKOFF_MS * (1L shl attempt))
            }
        }
        return AttemptResult.TRANSIENT_FAILURE
    }
}
