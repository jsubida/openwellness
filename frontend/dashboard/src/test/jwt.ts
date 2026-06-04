// Shared fake-JWT builder for tests. A real access token is
// base64url(header).base64url(payload).signature; the dashboard only ever
// base64url-decodes the PAYLOAD (no signature verification — gating is UX), so
// a placeholder signature is fine. Mirrors the inline builders that already
// live in jwt.test / AuthContext.test / useLogin.test; new tests use this so we
// don't grow a fourth copy.

// base64url-encode a UTF-8 string (no padding), the way a real JWT segment is.
function b64url(value: string): string {
  return btoa(value).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Build a fake (unsigned-style) JWT: header.payload.signature. */
export function fakeJwt(payload: Record<string, unknown>): string {
  const header = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = b64url(JSON.stringify(payload))
  return `${header}.${body}.fakesignature`
}
