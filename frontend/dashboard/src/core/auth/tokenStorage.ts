// Access + refresh token storage. Mirrors mobile AuthTokenStorage.kt, adapted
// to the web threat model:
//   - access token: MODULE MEMORY ONLY — never persisted, dies on reload by
//     design (XSS can't read it from storage).
//   - refresh token: localStorage, so a reload can bootstrap a session.
// localStorage access is guarded (privacy/incognito modes can throw).

const REFRESH_KEY = 'openwellness.refreshToken'

interface TokenPair {
  accessToken: string
  refreshToken: string
}

let accessToken: string | null = null

function readRefresh(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY)
  } catch {
    return null
  }
}

function writeRefresh(value: string): void {
  try {
    localStorage.setItem(REFRESH_KEY, value)
  } catch {
    // Best effort — a session can still run from in-memory tokens this load.
  }
}

function removeRefresh(): void {
  try {
    localStorage.removeItem(REFRESH_KEY)
  } catch {
    // Ignore — nothing more we can do if storage is unavailable.
  }
}

export const tokenStorage = {
  getAccessToken(): string | null {
    return accessToken
  },

  getRefreshToken(): string | null {
    return readRefresh()
  },

  setTokens({ accessToken: access, refreshToken: refresh }: TokenPair): void {
    accessToken = access
    writeRefresh(refresh)
  },

  clear(): void {
    accessToken = null
    removeRefresh()
  },
}
