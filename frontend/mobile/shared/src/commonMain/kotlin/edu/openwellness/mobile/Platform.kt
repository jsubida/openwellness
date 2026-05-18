package edu.openwellness.mobile

interface Platform {
    val name: String
}

expect fun getPlatform(): Platform