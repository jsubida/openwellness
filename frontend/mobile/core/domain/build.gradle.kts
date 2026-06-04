import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// :core:domain — innermost layer. Pure Kotlin contracts (Result/Error/DataError).
// Depends on NOTHING but the standard library + coroutines. No Compose/Ktor/serialization.
// This file maps 1:1 onto a future `domain-module` convention plugin.
plugins {
    alias(libs.plugins.kotlinMultiplatform)
    alias(libs.plugins.androidMultiplatformLibrary)
}

kotlin {
    androidLibrary {
        namespace = "edu.openwellness.mobile.core.domain"
        compileSdk = libs.versions.android.compileSdk.get().toInt()
        minSdk = libs.versions.android.minSdk.get().toInt()

        compilerOptions {
            jvmTarget = JvmTarget.JVM_11
        }
        withHostTest {}
    }

    iosArm64()
    iosSimulatorArm64()

    sourceSets {
        commonMain.dependencies {
            implementation(libs.kotlinx.coroutines.core)
        }
        commonTest.dependencies {
            implementation(libs.kotlin.test)
        }
    }
}
