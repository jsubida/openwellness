package edu.openwellness.mobile.core.data.auth

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import kotlinx.cinterop.ExperimentalForeignApi
import org.koin.core.module.Module
import org.koin.dsl.module
import platform.Foundation.NSDocumentDirectory
import platform.Foundation.NSFileManager
import platform.Foundation.NSURL
import platform.Foundation.NSUserDomainMask

/** iOS token DataStore rooted in the app's Documents directory. */
@OptIn(ExperimentalForeignApi::class)
fun createTokenDataStore(): DataStore<Preferences> = createDataStore {
    val documentDirectory: NSURL? = NSFileManager.defaultManager.URLForDirectory(
        directory = NSDocumentDirectory,
        inDomain = NSUserDomainMask,
        appropriateForURL = null,
        create = false,
        error = null,
    )
    requireNotNull(documentDirectory?.path) + "/$AUTH_PREFS_FILE"
}

actual val platformCoreDataModule: Module = module {
    single<DataStore<Preferences>> { createTokenDataStore() }
}
