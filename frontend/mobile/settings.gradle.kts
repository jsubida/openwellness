rootProject.name = "OpenWellness"
enableFeaturePreview("TYPESAFE_PROJECT_ACCESSORS")

pluginManagement {
    repositories {
        google {
            mavenContent {
                includeGroupAndSubgroups("androidx")
                includeGroupAndSubgroups("com.android")
                includeGroupAndSubgroups("com.google")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        google {
            mavenContent {
                includeGroupAndSubgroups("androidx")
                includeGroupAndSubgroups("com.android")
                includeGroupAndSubgroups("com.google")
            }
        }
        mavenCentral()
    }
}

include(":androidApp")
include(":shared")

// Clean-Architecture modules (disk layout: core/<layer>, feature/auth/<layer>).
// Type-safe project accessors are enabled, so these resolve as
// projects.core.domain, projects.feature.auth.data, etc.
include(":core:domain")
include(":core:data")
include(":core:presentation")
include(":feature:auth:domain")
include(":feature:auth:data")
include(":feature:auth:presentation")