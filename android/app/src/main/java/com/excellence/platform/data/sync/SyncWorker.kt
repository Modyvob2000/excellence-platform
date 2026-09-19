package com.excellence.platform.data.sync

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.*
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.concurrent.TimeUnit

@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val syncQueue: SyncQueue,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        return try {
            when (syncQueue.syncPendingAnswers()) {
                is SyncQueue.SyncOutcome.Success, is SyncQueue.SyncOutcome.NothingToSync -> Result.success()
                is SyncQueue.SyncOutcome.PartialFailure -> Result.success()  // مُعالَج، السبب مُسجَّل محليًا
            }
        } catch (e: Exception) {
            Result.retry()  // WorkManager يعيد الجدولة تلقائيًا بسياسة backoff الخاصة به
        }
    }

    companion object {
        private const val UNIQUE_WORK_NAME = "excellence_platform_sync"

        fun schedulePeriodic(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                UNIQUE_WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, request)
        }

        /** يُستدعى فورًا عند رصد عودة الاتصال بدل انتظار الدورة الزمنية. */
        fun triggerImmediateSync(context: Context) {
            val constraints = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
            val request = OneTimeWorkRequestBuilder<SyncWorker>().setConstraints(constraints).build()
            WorkManager.getInstance(context).enqueue(request)
        }
    }
}
