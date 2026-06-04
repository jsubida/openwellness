package edu.openwellness.mobile.core.data.di

import edu.openwellness.mobile.core.data.auth.AuthTokenStorage
import edu.openwellness.mobile.core.data.auth.DataStoreAuthTokenStorage
import edu.openwellness.mobile.core.data.auth.platformCoreDataModule
import edu.openwellness.mobile.core.data.network.ApiConfig
import edu.openwellness.mobile.core.data.network.HttpClientFactory
import edu.openwellness.mobile.core.data.network.httpClientEngine
import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.serialization.kotlinx.json.json
import org.koin.core.module.Module
import org.koin.core.qualifier.named
import org.koin.dsl.module

/** Qualifier for the plain refresh client (no Auth plugin → no refresh recursion). */
val RefreshClientQualifier = named("refreshClient")

/**
 * Core data graph. [baseUrl] is threaded in from the platform entry point
 * (Android BuildConfig / iOS config) so no URL is hardcoded in source.
 */
fun coreDataModule(baseUrl: String, debug: Boolean = false): Module = module {
    includes(platformCoreDataModule)

    single { ApiConfig(baseUrl = baseUrl, debug = debug) }
    single<HttpClientEngine> { httpClientEngine() }
    single<AuthTokenStorage> { DataStoreAuthTokenStorage(get()) }

    single(RefreshClientQualifier) {
        val config = get<ApiConfig>()
        HttpClient(get<HttpClientEngine>()) {
            install(ContentNegotiation) { json(HttpClientFactory.jsonConfig()) }
            defaultRequest { url(config.baseUrl) }
        }
    }

    single {
        HttpClientFactory.create(
            engine = get(),
            config = get(),
            tokenStorage = get(),
            refreshClient = get(RefreshClientQualifier),
        )
    }
}
