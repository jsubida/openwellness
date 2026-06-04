package edu.openwellness.mobile.core.data.auth

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import org.koin.android.ext.koin.androidContext
import org.koin.core.module.Module
import org.koin.dsl.module

/** Android token DataStore rooted in the app's private files dir. */
fun createTokenDataStore(context: Context): DataStore<Preferences> =
    createDataStore { context.filesDir.resolve(AUTH_PREFS_FILE).absolutePath }

/** The ONLY place an Android Context is referenced in :core:data. */
actual val platformCoreDataModule: Module = module {
    single<DataStore<Preferences>> { createTokenDataStore(androidContext()) }
}
