// AIP-193 error envelope wire types. Mirrors the backend shape in
// backend/api/.../errors/responses.py (ErrorBody/ErrorResponse) and the
// mobile ErrorEnvelopeDto. Detail entries are open-ended; the only field we
// read is the 429 rate-limit hint `retry_after_secs` (snake_case on the wire).

export interface ErrorDetail {
  retry_after_secs?: number
  [key: string]: unknown
}

export interface ErrorBody {
  code: number
  status: string
  message: string
  details: ErrorDetail[]
}

export interface ErrorEnvelope {
  error: ErrorBody
}
