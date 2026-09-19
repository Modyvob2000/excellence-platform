package com.excellence.platform

import android.app.Application
import com.excellence.platform.data.sync.SyncWorker
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class ExcellenceApp : Application() {
    override fun onCreate() {
        super.onCreate()
        SyncWorker.schedulePeriodic(this)  // مزامنة دورية للإجابات المعلّقة كل 15 دقيقة عند توفر الاتصال
    }
}
