package edu.openwellness.mobile.core.data.network

import io.ktor.client.engine.HttpClientEngine

/** Platform Ktor engine: OkHttp on Android, Darwin on iOS. Tests inject MockEngine. */
expect fun httpClientEngine(): HttpClientEngine
