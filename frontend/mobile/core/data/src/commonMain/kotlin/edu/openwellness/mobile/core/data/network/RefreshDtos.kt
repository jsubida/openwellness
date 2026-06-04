package edu.openwellness.mobile.core.data.network

import kotlinx.serialization.Serializable

/**
 * Refresh request/response wire shapes. They live in :core:data (not the auth
 * feature) because the HttpClient `Auth` block performs the refresh, and
 * :core:data cannot depend on a feature module.
 *
 * camelCase property names == wire keys, so no `@SerialName` is required.
 */
@Serializable
data class RefreshTokenRequestDto(
    val refreshToken: String,
)

@Serializable
data class RefreshResponseDto(
    val accessToken: String,
    val tokenType: String = "Bearer",
    val expiresInSeconds: Long,
    val refreshToken: String,
)
