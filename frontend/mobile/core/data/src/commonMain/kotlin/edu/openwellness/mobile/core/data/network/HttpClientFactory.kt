package edu.openwellness.mobile.core.data.network

import edu.openwellness.mobile.core.data.auth.AuthTokenStorage
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.authProviders
import io.ktor.client.plugins.auth.providers.BearerAuthProvider
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.pluginOrNull
import io.ktor.client.plugins.logging.LogLevel
import io.ktor.client.plugins.logging.Logging
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.request.url
import io.ktor.http.ContentType
import io.ktor.http.appendPathSegments
import io.ktor.http.contentType
import io.ktor.http.takeFrom
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

/**
 * Builds the app's authenticated [HttpClient]. Token persistence is centralized
 * here in the `Auth(bearer)` block; the engine is injected so tests can swap in
 * a MockEngine.
 *
 * - Logging is capped at [LogLevel.HEADERS] — auth bodies (OTP codes, tokens)
 *   are NEVER logged.
 * - `refreshTokens` performs a rotating refresh over a SEPARATE plain client
 *   ([refreshClient], with NO Auth plugin) — that isolation is the recursion
 *   guard (a refresh can never itself trigger a refresh). On success it persists
 *   the NEW pair before returning; on 401 it clears storage (family revoked).
 */
object HttpClientFactory {

    fun create(
        engine: HttpClientEngine,
        config: ApiConfig,
        tokenStorage: AuthTokenStorage,
        refreshClient: HttpClient,
    ): HttpClient = HttpClient(engine) {
        install(ContentNegotiation) {
            json(jsonConfig())
        }
        install(Logging) {
            level = if (config.debug) LogLevel.HEADERS else LogLevel.NONE
        }
        defaultRequest {
            url(config.baseUrl)
        }
        install(Auth) {
            bearer {
                // Attach the access token preemptively. The backend's 401s carry
                // no WWW-Authenticate challenge, so a reactive scheme would never
                // retry authenticated calls (e.g. revoke all=true).
                sendWithoutRequest { true }

                loadTokens {
                    val access = tokenStorage.getAccessToken()
                    val refresh = tokenStorage.getRefreshToken()
                    if (access != null && refresh != null) {
                        BearerTokens(accessToken = access, refreshToken = refresh)
                    } else {
                        null
                    }
                }

                refreshTokens {
                    val storedRefresh = tokenStorage.getRefreshToken()
                        ?: return@refreshTokens null

                    val response = refreshClient.post {
                        url {
                            takeFrom(config.baseUrl)
                            appendPathSegments("auth:refreshToken")
                        }
                        contentType(ContentType.Application.Json)
                        setBody(RefreshTokenRequestDto(refreshToken = storedRefresh))
                    }

                    if (response.status.value in 200..299) {
                        val body = response.body<RefreshResponseDto>()
                        // Persist the ROTATED pair before returning; a stale stored
                        // refresh would mean a hard logout on next use.
                        tokenStorage.saveTokens(
                            accessToken = body.accessToken,
                            refreshToken = body.refreshToken,
                        )
                        BearerTokens(
                            accessToken = body.accessToken,
                            refreshToken = body.refreshToken,
                        )
                    } else {
                        if (response.status.value == 401) {
                            tokenStorage.clear()
                        }
                        null
                    }
                }
            }
        }
    }

    /**
     * Clears the in-memory bearer-token cache so the next request re-reads
     * storage via `loadTokens`. Call after the repository persists new tokens
     * (verify) or clears them (revoke) out-of-band from the Auth plugin.
     */
    fun clearBearerCache(client: HttpClient) {
        if (client.pluginOrNull(Auth) == null) return
        client.authProviders
            .filterIsInstance<BearerAuthProvider>()
            .forEach { it.clearToken() }
    }

    fun jsonConfig(): Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }
}
