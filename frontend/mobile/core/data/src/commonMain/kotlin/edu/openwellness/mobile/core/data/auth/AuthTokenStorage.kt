package edu.openwellness.mobile.core.data.auth

/**
 * Persistent storage for the access + (rotating) refresh token pair.
 *
 * The Ktor `Auth(bearer)` block is the single reader/writer in normal operation
 * (loadTokens / refreshTokens); the auth repository also writes on verify and
 * clears on revoke. Backed by multiplatform DataStore today; swapping to
 * Keystore/Keychain later is an implementation change only.
 */
interface AuthTokenStorage {
    suspend fun getAccessToken(): String?
    suspend fun getRefreshToken(): String?
    suspend fun saveTokens(accessToken: String, refreshToken: String)
    suspend fun clear()
}
