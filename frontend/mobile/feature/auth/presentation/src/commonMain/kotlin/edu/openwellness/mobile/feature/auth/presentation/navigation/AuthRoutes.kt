package edu.openwellness.mobile.feature.auth.presentation.navigation

import kotlinx.serialization.Serializable

/** The auth feature's nested graph and its three screens. */
@Serializable
data object AuthGraphRoute

@Serializable
data object LandingRoute

@Serializable
data object LoginRoute

@Serializable
data object RegisterRoute
