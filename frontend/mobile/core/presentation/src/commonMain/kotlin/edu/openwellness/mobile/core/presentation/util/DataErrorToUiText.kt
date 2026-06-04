package edu.openwellness.mobile.core.presentation.util

import edu.openwellness.mobile.core.domain.util.DataError
import edu.openwellness.mobile.core.presentation.resources.Res
import edu.openwellness.mobile.core.presentation.resources.error_disk_full
import edu.openwellness.mobile.core.presentation.resources.error_no_internet
import edu.openwellness.mobile.core.presentation.resources.error_request_timeout
import edu.openwellness.mobile.core.presentation.resources.error_serialization
import edu.openwellness.mobile.core.presentation.resources.error_server
import edu.openwellness.mobile.core.presentation.resources.error_service_unavailable
import edu.openwellness.mobile.core.presentation.resources.error_too_many_requests
import edu.openwellness.mobile.core.presentation.resources.error_unauthorized
import edu.openwellness.mobile.core.presentation.resources.error_unknown

/** Shared mapping for transport errors displayed to the user. */
fun DataError.toUiText(): UiText {
    val resource = when (this) {
        DataError.Network.NO_INTERNET -> Res.string.error_no_internet
        DataError.Network.REQUEST_TIMEOUT -> Res.string.error_request_timeout
        DataError.Network.TOO_MANY_REQUESTS -> Res.string.error_too_many_requests
        DataError.Network.SERVER_ERROR -> Res.string.error_server
        DataError.Network.SERVICE_UNAVAILABLE -> Res.string.error_service_unavailable
        DataError.Network.UNAUTHORIZED, DataError.Network.FORBIDDEN -> Res.string.error_unauthorized
        DataError.Network.SERIALIZATION -> Res.string.error_serialization
        DataError.Local.DISK_FULL -> Res.string.error_disk_full
        else -> Res.string.error_unknown
    }
    return UiText.StringResourceText(resource)
}
