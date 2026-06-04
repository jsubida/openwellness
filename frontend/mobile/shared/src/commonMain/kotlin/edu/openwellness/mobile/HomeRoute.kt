package edu.openwellness.mobile

import kotlinx.serialization.Serializable

/** Post-auth destination. Lives in :shared so the auth feature stays unaware of it. */
@Serializable
data object HomeRoute
