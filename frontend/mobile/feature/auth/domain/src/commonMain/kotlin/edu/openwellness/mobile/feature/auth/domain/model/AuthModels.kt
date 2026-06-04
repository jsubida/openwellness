package edu.openwellness.mobile.feature.auth.domain.model

/**
 * A freshly issued credential pair.
 *
 * [refreshToken] is a rotating opaque token: every successful refresh returns a
 * NEW refresh token and the old one is invalidated server-side, so the latest
 * pair must always be persisted together.
 */
data class AuthTokens(
    val accessToken: String,
    val refreshToken: String,
    val tokenType: String,
    val expiresInSeconds: Long,
)

/**
 * The authenticated caller's identity.
 *
 * [participant] is the AIP resource name `participants/{pid}` and is nullable —
 * a logged-in user is not necessarily bound to a participant.
 */
data class Principal(
    val userId: String,
    val participant: String?,
)

/** A verified session: the issued tokens plus the resolved principal. */
data class AuthSession(
    val tokens: AuthTokens,
    val principal: Principal,
)

/**
 * The uniform, anti-enumeration result of a send-code request. Identical
 * regardless of whether the account/participant actually exists.
 *
 * [resendAfterSeconds] seeds the client's resend cooldown.
 */
data class SendCodeResult(
    val expiresInSeconds: Long,
    val resendAfterSeconds: Long,
    val message: String,
)
