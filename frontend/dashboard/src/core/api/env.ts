// API base URL, INCLUDING the /v1 prefix. Mirrors mobile ApiConfig.baseUrl.
// Inlined at build time from VITE_API_BASE_URL; defaults to the local dev API.

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/v1'
