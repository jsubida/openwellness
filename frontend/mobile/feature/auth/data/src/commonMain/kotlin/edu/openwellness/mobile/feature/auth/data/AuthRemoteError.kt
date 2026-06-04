package edu.openwellness.mobile.feature.auth.data

import edu.openwellness.mobile.core.domain.util.DataError
import edu.openwellness.mobile.core.domain.util.Error

/**
 * Data-layer-internal failure from the auth remote source: the transport-level
 * [network] error plus an optional server-authoritative [retryAfterSeconds]
 * (only populated for 429). The repository maps this onto the domain `AuthError`.
 *
 * Implements [Error] so it can be the typed-error arm of a `Result`.
 */
internal data class AuthRemoteError(
    val network: DataError.Network,
    val retryAfterSeconds: Long? = null,
) : Error
