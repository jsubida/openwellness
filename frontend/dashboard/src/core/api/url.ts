// Slash-route URL builder. Mirrors the mobile `appendPathSegments(verb)` trick
// in HttpClientFactory.kt / KtorAuthRemoteDataSource.kt: the verb carries a
// literal `:` (e.g. `auth:sendLoginCode`) that must be appended as a path
// segment, NOT passed to `new URL(path, base)` (which parses `auth:` as a
// scheme). We concatenate against the base so the colon survives verbatim.

import { API_BASE_URL } from './env'

export function buildApiUrl(path: string, base: string = API_BASE_URL): string {
  const trimmedBase = base.replace(/\/+$/, '')
  const trimmedPath = path.replace(/^\/+/, '')
  return `${trimmedBase}/${trimmedPath}`
}
