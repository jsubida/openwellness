package edu.openwellness.mobile

import android.app.Application
import edu.openwellness.mobile.di.initKoin
import org.koin.android.ext.koin.androidContext

class MobileApp : Application() {
    override fun onCreate() {
        super.onCreate()
        initKoin(
            baseUrl = BuildConfig.API_BASE_URL,
            debug = BuildConfig.DEBUG,
        ) {
            androidContext(this@MobileApp)
        }
    }
}
