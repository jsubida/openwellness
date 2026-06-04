import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.composeMultiplatform)
    alias(libs.plugins.composeCompiler)
}

// Base API URL surfaced into BuildConfig.API_BASE_URL. A Gradle property
// `openwellness.apiBaseUrl` wins; otherwise we read it from local.properties;
// otherwise we fall back to the Android emulator loopback host. Read through the
// Provider API so it stays configuration-cache compatible (local.properties is
// registered as a build input). Base URL ends in `/v1/` (trailing slash) so
// relative routes like `auth:sendLoginCode` resolve correctly.
val apiBaseUrl: String =
    providers.gradleProperty("openwellness.apiBaseUrl")
        .orElse(
            providers.fileContents(
                rootProject.layout.projectDirectory.file("local.properties")
            ).asText.map { text ->
                text.lineSequence()
                    .map(String::trim)
                    .firstOrNull { it.startsWith("openwellness.apiBaseUrl=") }
                    ?.substringAfter('=')
                    ?.trim()
                    .orEmpty()
            }.filter(String::isNotEmpty)
        )
        .getOrElse("http://10.0.2.2:8000/v1/")

kotlin {
    compilerOptions {
        jvmTarget = JvmTarget.JVM_11
    }
}
dependencies {
    implementation(projects.shared)

    implementation(libs.androidx.activity.compose)

    implementation(libs.compose.uiToolingPreview)
    debugImplementation(libs.compose.uiTooling)

    // koin-android provides androidContext(this@MobileApp); it `api`-exposes
    // koin-core so startKoin / KoinApplication are available too.
    implementation(project.dependencies.platform(libs.koin.bom))
    implementation(libs.koin.android)
}

android {
    namespace = "edu.openwellness.mobile"
    compileSdk = libs.versions.android.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "edu.openwellness.mobile"
        minSdk = libs.versions.android.minSdk.get().toInt()
        targetSdk = libs.versions.android.targetSdk.get().toInt()
        versionCode = 1
        versionName = "1.0"
        buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
    }
    buildFeatures {
        buildConfig = true
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
}
