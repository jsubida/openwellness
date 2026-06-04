package edu.openwellness.mobile.core.domain.util

/**
 * Marker supertype for every typed error carried by [Result].
 *
 * Layer- and feature-specific error types (e.g. `DataError`, `AuthError`,
 * validation enums) implement this so a single generic [Result] can represent
 * typed failures anywhere in the app.
 */
interface Error
