package edu.openwellness.mobile.feature.auth.presentation

import edu.openwellness.mobile.core.domain.util.EmptyResult
import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.domain.AuthError
import edu.openwellness.mobile.feature.auth.domain.AuthRepository
import edu.openwellness.mobile.feature.auth.domain.model.AuthSession
import edu.openwellness.mobile.feature.auth.domain.model.AuthTokens
import edu.openwellness.mobile.feature.auth.domain.model.Principal
import edu.openwellness.mobile.feature.auth.domain.model.SendCodeResult

/** In-memory fake of [AuthRepository] for ViewModel tests. */
class FakeAuthRepository : AuthRepository {

    var sendResult: Result<SendCodeResult, AuthError> =
        Result.Success(SendCodeResult(expiresInSeconds = 900, resendAfterSeconds = 60, message = "ok"))
    var verifyResult: Result<AuthSession, AuthError> =
        Result.Success(
            AuthSession(
                tokens = AuthTokens("access", "refresh", "Bearer", 900),
                principal = Principal(userId = "u1", participant = null),
            ),
        )

    var sendCallCount = 0
    var verifyCallCount = 0
    var lastSendEmail: String? = null
    var lastSendParticipant: String? = null
    var lastVerifyCode: String? = null

    override suspend fun sendLoginCode(email: String): Result<SendCodeResult, AuthError> {
        sendCallCount++
        lastSendEmail = email
        return sendResult
    }

    override suspend fun sendRegistrationCode(
        email: String,
        participant: String,
    ): Result<SendCodeResult, AuthError> {
        sendCallCount++
        lastSendEmail = email
        lastSendParticipant = participant
        return sendResult
    }

    override suspend fun verifyLoginCode(email: String, code: String): Result<AuthSession, AuthError> {
        verifyCallCount++
        lastVerifyCode = code
        return verifyResult
    }

    override suspend fun verifyRegistrationCode(email: String, code: String): Result<AuthSession, AuthError> {
        verifyCallCount++
        lastVerifyCode = code
        return verifyResult
    }

    override suspend fun refresh(): EmptyResult<AuthError> = Result.Success(Unit)
    override suspend fun revokeCurrent(): EmptyResult<AuthError> = Result.Success(Unit)
    override suspend fun revokeAll(): EmptyResult<AuthError> = Result.Success(Unit)
}
