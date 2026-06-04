package edu.openwellness.mobile.di

import edu.openwellness.mobile.core.data.di.coreDataModule
import edu.openwellness.mobile.feature.auth.data.di.authDataModule
import edu.openwellness.mobile.feature.auth.presentation.di.authPresentationModule
import org.koin.core.KoinApplication
import org.koin.core.context.startKoin
import org.koin.dsl.KoinAppDeclaration

/**
 * Composition root for DI. [baseUrl] is threaded into [coreDataModule]'s
 * `ApiConfig`. The optional [config] lets each platform contribute extras before
 * modules load — Android passes `androidContext(...)` here.
 */
fun initKoin(
    baseUrl: String,
    debug: Boolean = false,
    config: KoinAppDeclaration? = null,
): KoinApplication = startKoin {
    config?.invoke(this)
    modules(
        coreDataModule(baseUrl = baseUrl, debug = debug),
        authDataModule,
        authPresentationModule,
    )
}
