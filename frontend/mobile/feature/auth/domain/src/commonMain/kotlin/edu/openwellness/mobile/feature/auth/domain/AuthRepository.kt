package edu.openwellness.mobile.feature.auth.domain

import edu.openwellness.mobile.core.domain.util.EmptyResult
import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.domain.model.AuthSession
import edu.openwellness.mobile.feature.auth.domain.model.SendCodeResult

/**
 * The auth contract the presentation layer depends on.
 *
 * Send methods are anti-enumeration: they resolve to [SendCodeResult] for any
 * eligible-or-not email. Verify methods persist the issued tokens on success
 * before returning the [AuthSession]. Refresh/revoke return [EmptyResult].
 */
interface AuthRepository {
    suspend fun sendLoginCode(email: String): Result<SendCodeResult, AuthError>

    suspend fun sendRegistrationCode(
        email: String,
        participant: String,
    ): Result<SendCodeResult, AuthError>

    suspend fun verifyLoginCode(
        email: String,
        code: String,
    ): Result<AuthSession, AuthError>

    suspend fun verifyRegistrationCode(
        email: String,
        code: String,
    ): Result<AuthSession, AuthError>

    /** Refresh the access token using the stored (rotating) refresh token. */
    suspend fun refresh(): EmptyResult<AuthError>

    /** Revoke the current session (the stored refresh token), then clear storage. */
    suspend fun revokeCurrent(): EmptyResult<AuthError>

    /** Revoke every session for the bearer-authenticated caller, then clear storage. */
    suspend fun revokeAll(): EmptyResult<AuthError>
}
