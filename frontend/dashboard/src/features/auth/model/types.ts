// Mirrors AuthModels.kt (feature/auth/domain/model/AuthModels.kt)

/**
 * A freshly issued credential pair.
 *
 * refreshToken is a rotating opaque token: every successful refresh returns a
 * NEW refresh token and the old one is invalidated server-side, so the latest
 * pair must always be persisted together.
 */
export interface AuthTokens {
  accessToken: string
  refreshToken: string
  tokenType: string
  expiresInSeconds: number
}

/**
 * The authenticated caller's identity.
 *
 * participant is the AIP resource name `participants/{pid}` and is nullable —
 * a logged-in user is not necessarily bound to a participant.
 */
export interface Principal {
  userId: string
  participant: string | null
}

/** A verified session: the issued tokens plus the resolved principal. */
export interface AuthSession {
  tokens: AuthTokens
  principal: Principal
}

/**
 * The uniform, anti-enumeration result of a send-code request. Identical
 * regardless of whether the account/participant actually exists.
 *
 * resendAfterSeconds seeds the client's resend cooldown.
 */
export interface SendCodeResult {
  expiresInSeconds: number
  resendAfterSeconds: number
  /** Server's human-readable status hint. Uniform regardless of whether the email exists (anti-enumeration) — not required UI copy. */
  message: string
}
