package edu.openwellness.mobile.core.data.auth

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import okio.Path.Companion.toPath
import org.koin.core.module.Module

internal const val AUTH_PREFS_FILE = "openwellness_auth.preferences_pb"

/**
 * Cross-platform DataStore creator. The caller supplies the absolute on-disk
 * path; the platform-specific way to compute that path lives in the actuals of
 * [platformCoreDataModule].
 */
fun createDataStore(producePath: () -> String): DataStore<Preferences> =
    PreferenceDataStoreFactory.createWithPath(
        produceFile = { producePath().toPath() },
    )

/**
 * Platform Koin module that binds the `DataStore<Preferences>`. This is the ONLY
 * place an Android `Context` is referenced (in the Android actual), keeping
 * commonMain Context-free.
 */
expect val platformCoreDataModule: Module
