package edu.openwellness.mobile.feature.auth.data.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// --------------------------------------------------------------------------- //
// Requests. camelCase property names == wire keys (the backend uses a camelCase
// alias generator), so no @SerialName is needed.
// --------------------------------------------------------------------------- //
@Serializable
data class SendLoginCodeRequestDto(
    val email: String,
)

@Serializable
data class VerifyLoginCodeRequestDto(
    val email: String,
    val code: String,
)

@Serializable
data class SendRegistrationCodeRequestDto(
    val email: String,
    val participant: String,
)

@Serializable
data class VerifyRegistrationCodeRequestDto(
    val email: String,
    val code: String,
)

/**
 * Revoke body. `explicitNulls = false` (set on the client Json) drops a null
 * [refreshToken] from the wire, so `all = true` sends just `{"all":true}`.
 */
@Serializable
data class RevokeTokenRequestDto(
    val refreshToken: String? = null,
    val all: Boolean = false,
)

// --------------------------------------------------------------------------- //
// Responses
// --------------------------------------------------------------------------- //
@Serializable
data class UniformSendResponseDto(
    val status: String = "OK",
    val message: String,
    val expiresInSeconds: Long,
    val resendAfterSeconds: Long,
)

@Serializable
data class PrincipalDto(
    val userId: String,
    val participant: String? = null,
)

@Serializable
data class TokenResponseDto(
    val accessToken: String,
    val tokenType: String = "Bearer",
    val expiresInSeconds: Long,
    val refreshToken: String,
    val principal: PrincipalDto,
)

@Serializable
data class RevokeResponseDto(
    val status: String = "OK",
)

// --------------------------------------------------------------------------- //
// AIP-193 error envelope: { "error": { code, status, message, details } }
// --------------------------------------------------------------------------- //
@Serializable
data class ErrorEnvelopeDto(
    val error: ApiErrorDto,
)

@Serializable
data class ApiErrorDto(
    val code: Int,
    val status: String,
    val message: String,
    val details: List<ErrorDetailDto> = emptyList(),
)

/**
 * A single error detail. Only [retryAfterSecs] is read (from the 429 envelope);
 * all other detail shapes (e.g. validation errors) deserialize with this field
 * null thanks to `ignoreUnknownKeys`. This is the ONE snake_case wire key.
 */
@Serializable
data class ErrorDetailDto(
    @SerialName("retry_after_secs") val retryAfterSecs: Long? = null,
)
