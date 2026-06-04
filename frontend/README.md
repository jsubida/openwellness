# frontend

The OpenWellness frontend is two sibling client apps. They share no code —
what they share is the backend API contract and a design intent: the dashboard
is a deliberate *principles-mirror* of the mobile app in idiomatic
React/TypeScript.

| Package | Audience | Role |
| --- | --- | --- |
| [`dashboard/`](dashboard/README.md) | Coaches and admins | React SPA (Vite + React 19 + Tailwind v4 + shadcn/ui). OTP login with a coach/admin role gate. |
| [`mobile/`](mobile/README.md) | Participants | Compose Multiplatform (KMP) app for Android and iOS. OTP login *and* registration. |

## Architecture

Both clients are pure HTTP consumers of the backend
[API](../backend/api/README.md) — neither touches a datastore directly, and
neither knows about the other.

```text
   ┌───────────────────┐         ┌───────────────────────┐
   │     dashboard     │         │        mobile         │
   │  React SPA (web)  │         │ Compose MP (Andr/iOS) │
   │  coaches · admins │         │     participants      │
   └─────────┬─────────┘         └───────────┬───────────┘
             │       HTTP · JSON · /v1       │
             └───────────────┬───────────────┘
                             ▼
                  backend api  (FastAPI)
            AIP-style REST  ·  /v1/auth:* custom methods
```

### What both clients keep in common

- **The AIP wire contract** — resource names (`participants/{pid}`),
  `camelCase` fields, RFC-3339 timestamps, opaque page tokens, and the AIP-193
  error envelope (see the
  [API conventions](../backend/api/README.md#api-conventions-aip)).

- **The auth flow** — the same email-OTP custom methods
  (`/v1/auth:sendLoginCode` / `auth:verifyLoginCode`, anti-enumeration uniform
  responses) issuing JWT access/refresh pairs with **rotating refresh** and a
  single-flight 401-retry. Mobile adds the registration pair; the dashboard
  adds a client-side coach/admin role gate (the server stays authoritative).
  Both treat the literal `:` in those routes carefully — it trips up naive URL
  handling (Ktor scheme parsing on mobile, MSW path-param matching in
  dashboard tests).

- **Clean-architecture intent** — layered `feature/auth` slices with
  dependency direction `data → domain ← presentation`, typed errors via
  `Result<T, E>`, and a `core` that never imports features. Mobile enforces
  this with Gradle module boundaries; the dashboard with an ESLint
  layer-boundary rule. The
  [dashboard README](dashboard/README.md#design) maps the two side by side.

- **Design language** — shared tokens (the dashboard's Tailwind `@theme`
  mirrors mobile's Material theme) and layout rhythm: 24px screen padding,
  16px between fields, 12px between buttons.

## Working on the packages

Each package is self-contained with its own toolchain — see its README for
prerequisites, configuration, and details:

```bash
# dashboard — npm / Vite
cd frontend/dashboard
npm install && npm run dev          # http://localhost:5173

# mobile — Gradle / Xcode
cd frontend/mobile
./gradlew :androidApp:installDebug  # iOS: open iosApp/iosApp.xcodeproj
```

Running either against real data needs the backend API up (see
[backend](../backend/README.md#running-the-services); auth requires the
`API_AUTH_*` secrets). Point the client at it via `VITE_API_BASE_URL`
(dashboard) or `openwellness.apiBaseUrl` (mobile).

## Testing

Neither suite needs a live backend — MSW stands in for the server on the
dashboard, Ktor's `MockEngine` on mobile:

```bash
cd frontend/dashboard && npm run test                  # vitest (unit + MSW integration)
cd frontend/mobile    && ./gradlew testAndroidHostTest # JVM host tests
```

The suites deliberately mirror each other — validators, auth
repository/mapping, and the login flow exist on both sides under matching
names (`ValidationUseCasesTest`, `OpenWellnessAuthRepositoryTest`,
`LoginViewModelTest` and their dashboard counterparts). See
[dashboard testing](dashboard/README.md#testing) and
[mobile testing](mobile/README.md#testing).
