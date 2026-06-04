# openwellness-dashboard

React web dashboard for **coaches and admins**. Talks to the backend API over
HTTP. Currently ships a single feature: OTP-verified login (the landing page
*is* the login page); signed-in users land on a placeholder home page.

## Design

The dashboard is a *principles-mirror* of the mobile app
(`frontend/mobile/`): it keeps the clean-architecture **intent** — layered
features, typed errors, `Result<T, E>`, design tokens — in idiomatic
React/TypeScript, and drops the Android-only ceremony (no DI container, no
`SavedStateHandle`, no event channels).

| Mobile (KMP) | Dashboard (React) |
| --- | --- |
| `core/domain` (`Result`, `DataError`) | `src/core/result.ts`, `src/core/errors.ts` |
| `core/data` (HttpClient, token storage) | `src/core/api/*`, `src/core/auth/tokenStorage.ts` |
| `core/presentation` (theme, components) | `src/styles/globals.css`, `src/core/theme/*`, `src/core/ui/*` |
| `feature/auth/domain` | `src/features/auth/model/*` |
| `feature/auth/data` | `src/features/auth/api/*` |
| `feature/auth/presentation` | `src/features/auth/ui/*` + `src/features/auth/hooks/*` |
| `App.kt` NavHost + Koin singletons | `src/app/*` (router, providers) + `src/core/auth/AuthContext.tsx` |

Dependency direction (enforced by `import-x/no-restricted-paths` in
`eslint.config.js`): `ui/hooks → model ← api`; everything may import `core/`;
`model/` and `api/` import no React (except `api/mutations.ts`, the TanStack
Query glue); `core/` never imports `features/`.

Auth specifics:

- **OTP login** via `POST /v1/auth:sendLoginCode` / `auth:verifyLoginCode`
  (AIP-193 error envelopes, anti-enumeration uniform responses).
- **Tokens**: access token in memory only; refresh token in `localStorage`.
  Refresh **rotates** the pair; the API client retries a 401 once after a
  single-flight refresh.
- **Role gate**: after verify, the JWT `roles` claim must contain `coach` or
  `admin` (client-side UX gate only — the server stays authoritative).

## Layout

```
src/
  main.tsx              Mount <App/>
  app/                  RouterProvider, providers, routes
  core/                 Shared base (mirrors mobile core/*)
    result.ts errors.ts api/ auth/ ui/ theme/ lib/
  features/auth/
    model/              Domain types, errors, validators, messages
    api/                DTOs, mappers, authApi, TanStack mutations
    hooks/useLogin.ts   The "ViewModel": step machine, cooldown, role gate
    ui/                 LandingLoginPage, EmailStep, CodeStep
  pages/                HomePage placeholder
  styles/globals.css    Tailwind v4 @theme design tokens
  test/                 Vitest setup (jsdom, jest-dom, MSW)
```

Styling is **Tailwind CSS v4** (CSS-first config — no `tailwind.config.js`;
tokens live in `styles/globals.css` `@theme`) plus **shadcn/ui** primitives
generated into `src/core/ui/` (see `components.json`). Layout rhythm mirrors
mobile: 24px screen padding, 16px between fields, 12px between buttons.

## Running locally

```bash
npm install
cp .env.example .env.local   # adjust VITE_API_BASE_URL if needed

# backend (from backend/api): requires ≥32-char secrets
# API_AUTH_JWT_SECRET=... API_AUTH_CODE_PEPPER=... uv run uvicorn openwellness_api.main:app --reload

npm run dev                  # http://localhost:5173
```

The backend allows `http://localhost:5173` / `http://127.0.0.1:5173` by
default (`API_CORS_ALLOWED_ORIGINS`). A commented Vite proxy alternative
lives in `vite.config.ts`.

## Configuration

Only `VITE_`-prefixed vars reach the client; they are inlined at build time.

| Variable | Default | Meaning |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/v1` | API base URL, **including** `/v1` |

## Testing

```bash
npm run test         # vitest (unit + MSW integration)
npm run typecheck    # tsc -b
npm run lint         # eslint (incl. layer-boundary rule)
npm run format       # prettier
```

Test suites mirror the mobile ones: validators
(`ValidationUseCasesTest`), auth API mapping
(`OpenWellnessAuthRepositoryTest`), and the login flow
(`LoginViewModelTest`) — with MSW standing in for Ktor's `MockEngine`.
