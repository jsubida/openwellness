package edu.openwellness.mobile

import edu.openwellness.mobile.di.initKoin

/**
 * iOS DI entry point, called from `iOSApp.swift`'s `init`. [baseUrl] comes from
 * the iOS build config (default `http://localhost:8000/v1/`).
 */
fun doInitKoin(baseUrl: String) {
    initKoin(baseUrl = baseUrl)
}
