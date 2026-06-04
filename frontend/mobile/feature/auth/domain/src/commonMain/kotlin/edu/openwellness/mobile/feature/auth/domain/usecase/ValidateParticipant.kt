package edu.openwellness.mobile.feature.auth.domain.usecase

import edu.openwellness.mobile.core.domain.util.EmptyResult
import edu.openwellness.mobile.core.domain.util.Result
import edu.openwellness.mobile.feature.auth.domain.AuthError

/**
 * The participant must be non-blank. Accepts either an AIP resource name
 * (`participants/<id>`) or a bare `<id>`; the backend normalizes, so the client
 * only needs to confirm something meaningful was entered after stripping the
 * optional `participants/` prefix.
 */
class ValidateParticipant {
    operator fun invoke(participant: String): EmptyResult<AuthError> {
        val normalized = participant.trim().removePrefix("participants/").trim()
        return if (normalized.isNotBlank()) {
            Result.Success(Unit)
        } else {
            Result.Error(AuthError.EmptyParticipant)
        }
    }
}
