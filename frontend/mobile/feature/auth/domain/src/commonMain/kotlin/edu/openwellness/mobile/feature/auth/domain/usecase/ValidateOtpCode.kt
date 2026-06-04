package edu.openwellness.mobile.feature.auth.domain.usecase

import edu.openwellness.mobile.core.domain.util.EmptyResult
import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.domain.AuthError

/** The OTP must be exactly six digits, matching the backend's `^\d{6}$` rule. */
class ValidateOtpCode {
    operator fun invoke(code: String): EmptyResult<AuthError> {
        return if (OTP_REGEX.matches(code)) {
            Result.Success(Unit)
        } else {
            Result.Error(AuthError.InvalidCode)
        }
    }

    private companion object {
        val OTP_REGEX = Regex("^\\d{6}$")
    }
}
