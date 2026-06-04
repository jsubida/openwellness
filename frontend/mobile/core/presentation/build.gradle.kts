import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// :core:presentation — shared UI utilities (UiText, ObserveAsEvents), the
// branded OpenWellness theme, and reusable design-system composables.
plugins {
    alias(libs.plugins.kotlinMultiplatform)
    alias(libs.plugins.androidMultiplatformLibrary)
    alias(libs.plugins.composeMultiplatform)
    alias(libs.plugins.composeCompiler)
}

kotlin {
    androidLibrary {
        namespace = "edu.openwellness.mobile.core.presentation"
        compileSdk = libs.versions.android.compileSdk.get().toInt()
        minSdk = libs.versions.android.minSdk.get().toInt()

        compilerOptions {
            jvmTarget = JvmTarget.JVM_11
        }
        androidResources {
            enable = true
        }
        withHostTest {
            isIncludeAndroidResources = true
        }
    }

    iosArm64()
    iosSimulatorArm64()

    sourceSets {
        androidMain.dependencies {
            implementation(libs.compose.uiToolingPreview)
        }
        commonMain.dependencies {
            implementation(projects.core.domain)

            implementation(libs.compose.runtime)
            implementation(libs.compose.foundation)
            implementation(libs.compose.material3)
            implementation(libs.compose.ui)
            implementation(libs.compose.components.resources)
            implementation(libs.compose.uiToolingPreview)

            implementation(libs.androidx.lifecycle.runtimeCompose)
            implementation(libs.kotlinx.collections.immutable)
        }
        commonTest.dependencies {
            implementation(libs.kotlin.test)
        }
    }
}

// Unique resource package so the generated `Res` class does not collide with
// :feature:auth:presentation (both would otherwise default to the same name).
compose.resources {
    publicResClass = true
    packageOfResClass = "edu.openwellness.mobile.core.presentation.resources"
}

dependencies {
    androidRuntimeClasspath(libs.compose.uiTooling)
}
