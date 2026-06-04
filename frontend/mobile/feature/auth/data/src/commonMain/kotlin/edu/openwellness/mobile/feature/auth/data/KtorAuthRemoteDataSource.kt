package edu.openwellness.mobile.feature.auth.data

import edu.openwellness.mobile.core.data.network.ApiConfig
import edu.openwellness.mobile.core.data.network.RefreshResponseDto
import edu.openwellness.mobile.core.data.network.RefreshTokenRequestDto
import edu.openwellness.mobile.core.data.network.statusToNetworkError
import edu.openwellness.mobile.core.domain.util.DataError
import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.data.dto.ErrorEnvelopeDto
import edu.openwellness.mobile.feature.auth.data.dto.RevokeResponseDto
import edu.openwellness.mobile.feature.auth.data.dto.RevokeTokenRequestDto
import edu.openwellness.mobile.feature.auth.data.dto.SendLoginCodeRequestDto
import edu.openwellness.mobile.feature.auth.data.dto.SendRegistrationCodeRequestDto
import edu.openwellness.mobile.feature.auth.data.dto.TokenResponseDto
import edu.openwellness.mobile.feature.auth.data.dto.UniformSendResponseDto
import edu.openwellness.mobile.feature.auth.data.dto.VerifyLoginCodeRequestDto
import edu.openwellness.mobile.feature.auth.data.dto.VerifyRegistrationCodeRequestDto
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.request.url
import io.ktor.client.statement.HttpResponse
import io.ktor.http.ContentType
import io.ktor.http.appendPathSegments
import io.ktor.http.contentType
import io.ktor.http.takeFrom
import io.ktor.util.network.UnresolvedAddressException
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.SerializationException

/**
 * One method per auth endpoint. Each builds `<baseUrl>/auth:<verb>` by appending
 * the verb as a PATH SEGMENT (the literal `:` must not be parsed as a URL
 * scheme), deserializes the success body, or parses the AIP-193 error envelope
 * (+ `Retry-After`) into an [AuthRemoteError].
 */
internal class KtorAuthRemoteDataSource(
    private val client: HttpClient,
    private val config: ApiConfig,
) {
    suspend fun sendLoginCode(
        email: String,
    ): Result<UniformSendResponseDto, AuthRemoteError> =
        execute("auth:sendLoginCode", SendLoginCodeRequestDto(email))

    suspend fun verifyLoginCode(
        email: String,
        code: String,
    ): Result<TokenResponseDto, AuthRemoteError> =
        execute("auth:verifyLoginCode", VerifyLoginCodeRequestDto(email, code))

    suspend fun sendRegistrationCode(
        email: String,
        participant: String,
    ): Result<UniformSendResponseDto, AuthRemoteError> =
        execute(
            "auth:sendRegistrationCode",
            SendRegistrationCodeRequestDto(email, participant),
        )

    suspend fun verifyRegistrationCode(
        email: String,
        code: String,
    ): Result<TokenResponseDto, AuthRemoteError> =
        execute(
            "auth:verifyRegistrationCode",
            VerifyRegistrationCodeRequestDto(email, code),
        )

    suspend fun refresh(
        refreshToken: String,
    ): Result<RefreshResponseDto, AuthRemoteError> =
        execute("auth:refreshToken", RefreshTokenRequestDto(refreshToken))

    suspend fun revokeCurrent(
        refreshToken: String,
    ): Result<RevokeResponseDto, AuthRemoteError> =
        execute("auth:revokeToken", RevokeTokenRequestDto(refreshToken = refreshToken))

    suspend fun revokeAll(): Result<RevokeResponseDto, AuthRemoteError> =
        execute("auth:revokeToken", RevokeTokenRequestDto(all = true))

    private suspend inline fun <reified Req : Any, reified Res> execute(
        verb: String,
        body: Req,
    ): Result<Res, AuthRemoteError> {
        val response: HttpResponse = try {
            client.post {
                url {
                    takeFrom(config.baseUrl)
                    appendPathSegments(verb)
                }
                contentType(ContentType.Application.Json)
                setBody(body)
            }
        } catch (e: UnresolvedAddressException) {
            return Result.Error(AuthRemoteError(DataError.Network.NO_INTERNET))
        } catch (e: SerializationException) {
            return Result.Error(AuthRemoteError(DataError.Network.SERIALIZATION))
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            return Result.Error(AuthRemoteError(DataError.Network.UNKNOWN))
        }
        return handleResponse(response)
    }

    private suspend inline fun <reified Res> handleResponse(
        response: HttpResponse,
    ): Result<Res, AuthRemoteError> {
        val status = response.status.value
        if (status in 200..299) {
            return try {
                Result.Success(response.body<Res>())
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                Result.Error(AuthRemoteError(DataError.Network.SERIALIZATION))
            }
        }
        val network = statusToNetworkError(status)
        val retryAfter = if (status == 429) parseRetryAfterSeconds(response) else null
        return Result.Error(AuthRemoteError(network = network, retryAfterSeconds = retryAfter))
    }

    /** Prefer the body's `details[0].retry_after_secs`, then `Retry-After`, then default. */
    private suspend fun parseRetryAfterSeconds(response: HttpResponse): Long {
        val fromBody = try {
            response.body<ErrorEnvelopeDto>().error.details
                .firstNotNullOfOrNull { it.retryAfterSecs }
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            null
        }
        if (fromBody != null) return fromBody

        response.headers["Retry-After"]?.toLongOrNull()?.let { return it }

        return DEFAULT_RETRY_AFTER_SECONDS
    }

    private companion object {
        const val DEFAULT_RETRY_AFTER_SECONDS = 60L
    }
}
