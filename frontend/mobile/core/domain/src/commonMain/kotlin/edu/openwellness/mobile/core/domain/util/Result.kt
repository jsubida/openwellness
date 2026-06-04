package edu.openwellness.mobile.core.domain.util

/**
 * Generic, typed success/failure wrapper used across every layer — data,
 * domain, presentation, and validation.
 *
 * NOTE: this shadows [kotlin.Result]. Always import this type explicitly
 * (`edu.openwellness.mobile.core.domain.util.Result`) at call sites.
 */
sealed interface Result<out D, out E : Error> {
    data class Success<out D>(val data: D) : Result<D, Nothing>

    // Fully-qualified bound so `Error` here is unambiguously the project marker
    // interface, never kotlin.Error.
    data class Error<out E : edu.openwellness.mobile.core.domain.util.Error>(
        val error: E,
    ) : Result<Nothing, E>
}

/** A [Result] that carries no success payload — only a typed error on failure. */
typealias EmptyResult<E> = Result<Unit, E>

inline fun <T, E : Error, R> Result<T, E>.map(
    map: (T) -> R,
): Result<R, E> {
    return when (this) {
        is Result.Error -> Result.Error(error)
        is Result.Success -> Result.Success(map(data))
    }
}

inline fun <T, E : Error> Result<T, E>.onSuccess(
    action: (T) -> Unit,
): Result<T, E> {
    return when (this) {
        is Result.Error -> this
        is Result.Success -> {
            action(data)
            this
        }
    }
}

inline fun <T, E : Error> Result<T, E>.onFailure(
    action: (E) -> Unit,
): Result<T, E> {
    return when (this) {
        is Result.Error -> {
            action(error)
            this
        }
        is Result.Success -> this
    }
}

fun <T, E : Error> Result<T, E>.asEmptyResult(): EmptyResult<E> {
    return map { }
}
