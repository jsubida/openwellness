package edu.openwellness.mobile.core.domain.util

/**
 * Shared transport-level errors produced by the data layer.
 *
 * [Network.BAD_REQUEST] (HTTP 400) matters for this app's auth surface: the
 * verify endpoints return 400 for an invalid/expired OTP code, which the auth
 * repository maps to a uniform "invalid or expired code".
 */
sealed interface DataError : Error {
    enum class Network : DataError {
        BAD_REQUEST,
        REQUEST_TIMEOUT,
        UNAUTHORIZED,
        FORBIDDEN,
        NOT_FOUND,
        CONFLICT,
        TOO_MANY_REQUESTS,
        NO_INTERNET,
        PAYLOAD_TOO_LARGE,
        SERVER_ERROR,
        SERVICE_UNAVAILABLE,
        SERIALIZATION,
        UNKNOWN,
    }

    enum class Local : DataError {
        DISK_FULL,
        NOT_FOUND,
        UNKNOWN,
    }
}
