# GOOGLE-HEALTH-API-SIGNATURE fixtures

Inputs for `tests/test_google_health_signature.py` (opserver Phase 10.1, 10.1-07 Task 3, GHA-02).
Tests read only these checked-in files: no network, no key generation, no Tink import.

| File | What it is |
|------|------------|
| `gen_vectors.sh` | Regenerates `vectors.json` and the bundled selfcheck copy. Signs with the `openssl` CLI (`ecparam -name prime256v1`, `dgst -sha256 -sign`), an implementation independent of the verifier; a stdlib-only python step adds Tink's framing (`0x01`, 4-byte big-endian key id, DER ECDSA-SHA256) and writes the Tink JSON public keyset (`EcdsaPublicKey`: P-256, SHA256, DER). The two throwaway private keys live in a temp dir removed on exit. |
| `vectors.json` | `keyset` (key A), `keyset_rotated` (keys A and B, B primary), and five cases: `valid`, `tampered_body`, `wrong_key` (signed by B under A's id), `not_base64`, `unknown_key_id` (signed by B under B's id, absent from `keyset`). Generated 2026-09-30 with OpenSSL 3.6.4. |
| `google_webhooks_public_keyset.json` | Google's live public keyset, fetched 2026-09-30T22:29Z from `https://www.gstatic.com/googlehealthapi/webhooks/webhooks_public_keyset.json` (sha256 `a3d230844e751173471429147af64af74f849848fc1f10b172007f3f40d7745c`; five ENABLED `EcdsaPublicKey` keys, TINK prefix, primary `3908867516`). Public keys only. |

Bundled copies (the selfcheck runs inside the built image, which has no `tests/`):
`src/openwellness_api/google_health/data/webhooks_public_keyset.json` is byte-identical to the
snapshot, and `data/selfcheck_vector.json` carries `keyset` plus the `valid` case.
`test_the_bundled_copies_match_the_fixtures` pins both.

Regenerate: `bash gen_vectors.sh` (vectors), and
`curl -sS --max-time 10 https://www.gstatic.com/googlehealthapi/webhooks/webhooks_public_keyset.json`
into both keyset paths (snapshot; update the fetch date above).
