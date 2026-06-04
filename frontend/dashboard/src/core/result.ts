// Generic typed success/failure wrapper. Mirrors mobile Result.kt
// (core/domain/util/Result.kt) — a discriminated union instead of a sealed
// interface, so `r.ok` narrows the value/error the same way `is Result.Success`
// does in Kotlin.

export type Result<T, E> = { ok: true; value: T } | { ok: false; error: E }

/** A Result that carries no success payload — only a typed error on failure. */
export type EmptyResult<E> = Result<void, E>

export function ok<T>(value: T): { ok: true; value: T } {
  return { ok: true, value }
}

/** Convenience for the void-payload case (mirrors `Result.Success(Unit)`). */
export function okVoid(): { ok: true; value: void } {
  return { ok: true, value: undefined }
}

export function err<E>(error: E): { ok: false; error: E } {
  return { ok: false, error }
}

export function isOk<T, E>(r: Result<T, E>): r is { ok: true; value: T } {
  return r.ok
}

export function map<T, U, E>(r: Result<T, E>, fn: (v: T) => U): Result<U, E> {
  return r.ok ? ok(fn(r.value)) : r
}

export function mapErr<T, E, F>(
  r: Result<T, E>,
  fn: (e: E) => F,
): Result<T, F> {
  return r.ok ? r : err(fn(r.error))
}
