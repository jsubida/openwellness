package edu.openwellness.mobile.feature.auth.domain.usecase

import edu.openwellness.mobile.core.domain.util.EmptyResult
import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.domain.AuthError

/**
 * Client-side email shape check (the server is authoritative). Trims first so a
 * trailing space from autofill doesn't fail an otherwise-valid address.
 */
class ValidateEmail {
    operator fun invoke(email: String): EmptyResult<AuthError> {
        val trimmed = email.trim()
        return if (trimmed.isNotBlank() && EMAIL_REGEX.matches(trimmed)) {
            Result.Success(Unit)
        } else {
            Result.Error(AuthError.InvalidEmail)
        }
    }

    private companion object {
        val EMAIL_REGEX = Regex("^[A-Za-z0-9+_.\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}$")
    }
}
