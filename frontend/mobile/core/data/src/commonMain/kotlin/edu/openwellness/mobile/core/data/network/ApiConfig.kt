package edu.openwellness.mobile.core.data.network

/**
 * Injected network configuration (the multiplatform replacement for Android's
 * generated BuildConfig). [baseUrl] must end with a trailing slash, e.g.
 * `http://10.0.2.2:8000/v1/`, so AIP custom-method routes like
 * `auth:sendLoginCode` resolve under `/v1/`.
 */
data class ApiConfig(
    val baseUrl: String,
    val debug: Boolean,
)
