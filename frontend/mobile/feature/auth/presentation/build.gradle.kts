import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// :feature:auth:presentation — Landing/Login/Register screens (MVI), type-safe
// nav routes + auth graph, and the auth presentation Koin module.
plugins {
    alias(libs.plugins.kotlinMultiplatform)
    alias(libs.plugins.androidMultiplatformLibrary)
    alias(libs.plugins.composeMultiplatform)
    alias(libs.plugins.composeCompiler)
    alias(libs.plugins.kotlinSerialization)
}

kotlin {
    androidLibrary {
        namespace = "edu.openwellness.mobile.feature.auth.presentation"
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
            implementation(projects.feature.auth.domain)
            implementation(projects.core.domain)
            implementation(projects.core.presentation)

            implementation(libs.compose.runtime)
            implementation(libs.compose.foundation)
            implementation(libs.compose.material3)
            implementation(libs.compose.ui)
            implementation(libs.compose.components.resources)
            implementation(libs.compose.uiToolingPreview)

            implementation(libs.androidx.lifecycle.viewmodel)
            implementation(libs.androidx.lifecycle.viewmodelCompose)
            implementation(libs.androidx.lifecycle.runtimeCompose)
            implementation(libs.kotlinx.collections.immutable)
            implementation(libs.kotlinx.coroutines.core)

            implementation(libs.navigation.compose)

            implementation(project.dependencies.platform(libs.koin.bom))
            implementation(libs.koin.compose)
            implementation(libs.koin.compose.viewmodel)
        }
        // ViewModel tests live in src/androidHostTest (run via testDebugUnitTest);
        // these multiplatform test libs are declared in commonTest so the host
        // test source set inherits them without racing androidHostTest creation.
        commonTest.dependencies {
            implementation(libs.kotlin.test)
            implementation(libs.kotlinx.coroutines.test)
            implementation(libs.turbine)
            implementation(libs.assertk)
        }
    }
}

// Unique resource package so the generated `Res` class does not collide with
// :core:presentation.
compose.resources {
    publicResClass = true
    packageOfResClass = "edu.openwellness.mobile.feature.auth.presentation.resources"
}

dependencies {
    androidRuntimeClasspath(libs.compose.uiTooling)
}
