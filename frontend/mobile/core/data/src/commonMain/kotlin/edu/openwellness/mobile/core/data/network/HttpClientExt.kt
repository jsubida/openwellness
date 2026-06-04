package edu.openwellness.mobile.core.data.network

import edu.openwellness.mobile.core.domain.util.DataError
import edu.openwellness.mobile.core.domain.util.Result
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.util.network.UnresolvedAddressException
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.SerializationException

/**
 * Generic safe-call helpers for slash-style routes (base URL is supplied by the
 * client's `defaultRequest`). The auth data source builds its own requests
 * because its routes contain a literal `:` (e.g. `auth:verifyLoginCode`), which
 * must be appended as a path segment rather than passed as a URL string.
 */
suspend inline fun <reified Response : Any> HttpClient.get(
    route: String,
    queryParameters: Map<String, Any?> = emptyMap(),
): Result<Response, DataError.Network> = safeCall {
    get(route) {
        queryParameters.forEach { (key, value) -> parameter(key, value) }
    }
}

suspend inline fun <reified Request, reified Response : Any> HttpClient.post(
    route: String,
    body: Request,
): Result<Response, DataError.Network> = safeCall {
    post(route) { setBody(body) }
}

suspend inline fun <reified T> safeCall(
    execute: () -> HttpResponse,
): Result<T, DataError.Network> {
    val response = try {
        execute()
    } catch (e: UnresolvedAddressException) {
        return Result.Error(DataError.Network.NO_INTERNET)
    } catch (e: SerializationException) {
        return Result.Error(DataError.Network.SERIALIZATION)
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        return Result.Error(DataError.Network.UNKNOWN)
    }
    return responseToResult(response)
}

suspend inline fun <reified T> responseToResult(
    response: HttpResponse,
): Result<T, DataError.Network> = mapStatusToResult(response.status.value) {
    response.body<T>()
}

/**
 * Status → typed result. 2xx runs [success]; otherwise maps via
 * [statusToNetworkError].
 */
inline fun <T> mapStatusToResult(
    status: Int,
    success: () -> T,
): Result<T, DataError.Network> =
    if (status in 200..299) {
        Result.Success(success())
    } else {
        Result.Error(statusToNetworkError(status))
    }

/**
 * Maps a non-2xx HTTP status to a [DataError.Network]. Includes 400/403/404/503
 * on top of the base skill set (auth verify returns 400 for invalid/expired
 * codes; the auth surface can emit 503 when its backing store is unavailable).
 */
fun statusToNetworkError(status: Int): DataError.Network = when (status) {
    400 -> DataError.Network.BAD_REQUEST
    401 -> DataError.Network.UNAUTHORIZED
    403 -> DataError.Network.FORBIDDEN
    404 -> DataError.Network.NOT_FOUND
    408 -> DataError.Network.REQUEST_TIMEOUT
    409 -> DataError.Network.CONFLICT
    413 -> DataError.Network.PAYLOAD_TOO_LARGE
    429 -> DataError.Network.TOO_MANY_REQUESTS
    503 -> DataError.Network.SERVICE_UNAVAILABLE
    in 500..599 -> DataError.Network.SERVER_ERROR
    else -> DataError.Network.UNKNOWN
}
