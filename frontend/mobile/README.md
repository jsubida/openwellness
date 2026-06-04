# openwellness-mobile

Compose Multiplatform (Kotlin Multiplatform) app for **participants**, targeting
Android and iOS from one codebase (`edu.openwellness.mobile`). Talks to the
backend [API](../../backend/api/README.md) over HTTP. Currently ships a single
feature: OTP-verified **login and registration**; signed-in users land on a
placeholder home screen.

All UI and logic live in `commonMain` — only the Ktor engine (OkHttp / Darwin)
and the DataStore file path are platform-specific.

## Architecture

The app is split into Gradle modules along **Clean Architecture** seams (the
same vocabulary as the [backend `core` glossary](../../backend/core/README.md#glossary)):
a `core/` ring of shared building blocks, one `feature/auth/` vertical slice,
and a `:shared` composition root consumed by the two platform shells.

```text
      ┌─────────────────┐         ┌──────────────────┐
      │   :androidApp   │         │  iosApp (Xcode)  │   platform shells
      │ BuildConfig.    │         │ iOSApp.swift →   │
      │  API_BASE_URL   │         │ Shared.framework │
      └────────┬────────┘         └────────┬─────────┘
               │ initKoin(baseUrl)         │ doInitKoin(baseUrl)
               └─────────────┬─────────────┘
                             ▼
                        ┌─────────┐
                        │ :shared │   App(): theme + NavHost, Koin root
                        └────┬────┘
            ┌────────────────┴────────────────┐
            ▼                                 ▼
      feature/auth/                        core/
  presentation ─► domain ◄─ data    presentation · domain · data
```

Dependency direction within each slice is `data → domain ← presentation`;
feature modules may import `core/*`; `core/*` never imports `feature/*`. The
domain modules are pure Kotlin — no Compose, Ktor, or Koin imports.

| Ring | Module(s) | Responsibility |
| --- | --- | --- |
| Entities / use cases | `core/domain`, `feature/auth/domain` | `Result<T, E>`, `DataError`; the `AuthRepository` **port**, `AuthError`, domain models, and the `Validate*` use cases. |
| Interface adapters | `feature/auth/data` | DTOs, mappers, the Ktor remote data source, and `OpenWellnessAuthRepository` (the port implementation). |
| Frameworks & drivers | `core/data` | `HttpClientFactory` (Ktor + bearer auth + rotating refresh), multiplatform DataStore token storage, `ApiConfig`. |
| Presentation | `core/presentation`, `feature/auth/presentation` | Material 3 theme, shared components, `UiText`; MVI screens, ViewModels, and the type-safe nav graph. |
| Composition | `shared`, `androidApp`, `iosApp` | Koin modules assembled in `initKoin()`; `App()` NavHost; platform entry points. |

### How the pieces fit

- **`core/domain`** — the typed-error vocabulary: `Result<T, E>`, `Error`,
  `DataError` (network/local). Everything else builds on these.

- **`core/data`** — `HttpClientFactory` builds the authenticated Ktor client:
  content negotiation, logging capped at `HEADERS` (OTP codes and tokens are
  never logged), and an `Auth(bearer)` block that attaches the access token and
  performs a **rotating refresh** through a separate plain `refreshClient` —
  the recursion guard, since Ktor 3.5 removed `markAsRefreshTokenRequest()`.
  Tokens persist in multiplatform **DataStore** behind the `AuthTokenStorage`
  port. The platform `actual`s supply the engine (OkHttp on Android, Darwin on
  iOS) and the DataStore path.

- **`feature/auth/domain`** — the `AuthRepository` port (send/verify login and
  registration codes, `refresh`, `revokeCurrent`, `revokeAll`), `AuthError`,
  and the field validators (`ValidateEmail`, `ValidateOtpCode`,
  `ValidateParticipant`).

- **`feature/auth/data`** — wire DTOs and mappers plus
  `KtorAuthRemoteDataSource`, which calls the `/v1/auth:*` custom methods.
  The routes contain a literal `:` (e.g. `auth:verifyLoginCode`), so they are
  appended via `url { takeFrom(baseUrl); appendPathSegments(...) }` — never
  passed as a URL string, which Ktor would parse as a scheme.
  `OpenWellnessAuthRepository` persists the issued tokens on verify before
  returning, and the send methods are anti-enumeration (uniform result for any
  email).

- **`feature/auth/presentation`** — MVI (`State` / `Action` / `Event`
  contracts) with `LandingScreen`, `LoginScreen`, and `RegisterScreen`, their
  ViewModels, the `AuthError → UiText` mapping, and the type-safe nested nav
  graph (`AuthGraphRoute`).

- **`:shared`** — the composition root. `App()` applies `OpenWellnessTheme`
  and hosts the NavHost (auth graph → home placeholder; logout revokes the
  session best-effort and pops back). `initKoin(baseUrl)` assembles the Koin
  modules; `doInitKoin` is the iOS entry; `MainViewController` bridges to
  SwiftUI.

- **`:androidApp` / `iosApp/`** — thin shells. `MobileApp` (Application) calls
  `initKoin` with `BuildConfig.API_BASE_URL` and the Android context;
  `iOSApp.swift` calls `doInitKoin` and hosts the shared UI in a SwiftUI
  `WindowGroup`.

Stack: Kotlin 2.3.21 · Compose Multiplatform 1.11.0 · AGP 9.0.1 ·
Gradle 9.1.0 — with Koin (DI), Ktor (HTTP), kotlinx-serialization, type-safe
Compose Navigation, and DataStore (token storage).

## Layout

```text
androidApp/            Android shell: MobileApp (Koin init), MainActivity
iosApp/                Xcode project: iOSApp.swift, ContentView, Config.xcconfig
shared/                Composition root: App() NavHost, initKoin, home placeholder
core/
  domain/              Result<T, E>, Error, DataError
  data/                HttpClientFactory, AuthTokenStorage (DataStore), ApiConfig
  presentation/        Theme, shared components, UiText, ObserveAsEvents
feature/auth/
  domain/              AuthRepository port, AuthError, models, validators
  data/                DTOs, mappers, KtorAuthRemoteDataSource, repository impl
  presentation/        Landing/Login/Register MVI screens + nav graph
```

## Prerequisites

- **JDK 17+** to run Gradle (module bytecode targets JVM 11).
- **Android Studio** (with AGP 9 support) and **Android SDK 36** for the
  Android app; min SDK 24.
- **Xcode** for the iOS app (`iosArm64` / `iosSimulatorArm64`).
- **A running backend API** only at *runtime* — the test suites use Ktor's
  `MockEngine` and fakes, and need nothing running (see [Testing](#testing)).

## Configuration

The Android base URL is surfaced as `BuildConfig.API_BASE_URL`, resolved in
this order (it must end in `/v1/` — the trailing slash matters, so relative
routes like `auth:sendLoginCode` resolve correctly):

1. The Gradle property `openwellness.apiBaseUrl` (e.g. `-Popenwellness.apiBaseUrl=…`).
2. `openwellness.apiBaseUrl=` in `local.properties`.
3. Fallback: `http://10.0.2.2:8000/v1/` (the emulator's host loopback).

iOS defaults to `http://localhost:8000/v1/`, set in `iOSApp.swift`.

Example `local.properties` entry:

```properties
openwellness.apiBaseUrl=http://10.0.2.2:8000/v1/
```

## Running

```bash
# backend (from backend/): requires ≥32-char secrets
# API_AUTH_JWT_SECRET=... API_AUTH_CODE_PEPPER=... uv run uvicorn openwellness_api.main:app --reload

# Android — build + install on a connected device/emulator
./gradlew :androidApp:installDebug
```

For iOS, open `iosApp/iosApp.xcodeproj` in Xcode and run the `iosApp` scheme
on a simulator (the `Shared` framework is built by Gradle automatically).

## Testing

This stack uses the AGP 9 `androidLibrary {}` KMP DSL, so the JVM unit-test
task is **`testAndroidHostTest`** — there is no `testDebugUnitTest` here.
Host tests live in `src/androidHostTest/`; pure-Kotlin suites live in
`src/commonTest/` and also run natively.

```bash
# All JVM host tests (the unit suites)
./gradlew testAndroidHostTest

# Native run of a commonTest suite (validators)
./gradlew :feature:auth:domain:iosSimulatorArm64Test

# iOS framework link check (catches ABI/link breakage without Xcode)
./gradlew :shared:linkDebugFrameworkIosSimulatorArm64
```

What the suites cover (none need a live backend):

- `ValidationUseCasesTest` (`feature/auth/domain`, commonTest) — the email,
  OTP-code, and participant validators.
- `OpenWellnessAuthRepositoryTest` (`feature/auth/data`) — DTO mapping and
  token persistence against Ktor's `MockEngine`.
- `LoginViewModelTest` / `RegisterViewModelTest`
  (`feature/auth/presentation`) — the MVI flows against a fake repository,
  using Turbine + AssertK + `kotlinx-coroutines-test`.
