#!/usr/bin/env bash
# Regenerates vectors.json (and the selfcheck copy bundled in the package) for
# the GOOGLE-HEALTH-API-SIGNATURE verifier tests (opserver Phase 10.1, GHA-02).
#
# Signing uses the openssl CLI, an implementation independent of both the Tink
# verifier and a `cryptography` fallback. A short stdlib-only python step
# assembles the Tink wire format Google uses:
#   signature = 0x01 || key_id (4 bytes, big-endian) || DER ECDSA-SHA256
#   keyset    = Tink JSON public keyset of EcdsaPublicKey protos (P-256, SHA256, DER)
# No Tink import, no network. The two throwaway private keys live in a temp dir
# that is removed on exit; only public material and signatures are written.
#
# Usage (from anywhere): bash gen_vectors.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
package_data="$here/../../../src/openwellness_api/google_health/data"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

command -v openssl >/dev/null || { echo "openssl not found" >&2; exit 1; }

openssl ecparam -name prime256v1 -genkey -noout -out "$work/key_a.pem"
openssl ecparam -name prime256v1 -genkey -noout -out "$work/key_b.pem"
openssl ec -in "$work/key_a.pem" -pubout -outform DER -out "$work/pub_a.der" 2>/dev/null
openssl ec -in "$work/key_b.pem" -pubout -outform DER -out "$work/pub_b.der" 2>/dev/null

# The signed body: a single-object notification shaped like Google's examples.
printf '%s' '{"data":{"version":"1","clientProvidedSubscriptionName":"vector","healthUserId":"vector-user","operation":"UPSERT","dataType":"steps","intervals":[{"civilIso8601TimeInterval":{"startTime":"2026-09-01T08:00:00","endTime":"2026-09-01T08:05:00"}}]}}' > "$work/body.json"

openssl dgst -sha256 -sign "$work/key_a.pem" -out "$work/sig_a.der" "$work/body.json"
openssl dgst -sha256 -sign "$work/key_b.pem" -out "$work/sig_b.der" "$work/body.json"
# Sanity: openssl itself accepts both signatures over the body.
openssl dgst -sha256 -verify "$work/pub_a.der" -keyform DER -signature "$work/sig_a.der" "$work/body.json" >/dev/null
openssl dgst -sha256 -verify "$work/pub_b.der" -keyform DER -signature "$work/sig_b.der" "$work/body.json" >/dev/null

python3 - "$work" "$here/vectors.json" "$package_data/selfcheck_vector.json" <<'PY'
import base64
import json
import sys
from pathlib import Path

work, out_vectors, out_selfcheck = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])

KEY_A = 0x5EED0A01  # in "keyset" and "keyset_rotated"
KEY_B = 0x5EED0B02  # only in "keyset_rotated" (a newly rotated key)
TYPE_URL = "type.googleapis.com/google.crypto.tink.EcdsaPublicKey"


def point(der_spki: bytes) -> tuple[bytes, bytes]:
    raw = der_spki[-65:]
    assert raw[0] == 0x04, "expected an uncompressed P-256 point"
    return raw[1:33], raw[33:65]


def field(tag: int, payload: bytes) -> bytes:
    assert len(payload) < 128
    return bytes([tag, len(payload)]) + payload


def ecdsa_public_key(der_spki: bytes) -> bytes:
    x, y = point(der_spki)
    # EcdsaParams: hash_type=SHA256(3), curve=NIST_P256(2), encoding=DER(2)
    params = bytes([0x08, 0x03, 0x10, 0x02, 0x18, 0x02])
    # EcdsaPublicKey: version=0 (omitted), params=2, x=3, y=4 (leading 0x00 as Google's keys carry)
    return field(0x12, params) + field(0x1A, b"\x00" + x) + field(0x22, b"\x00" + y)


def key_entry(key_id: int, der_spki: bytes) -> dict:
    return {
        "keyData": {
            "typeUrl": TYPE_URL,
            "value": base64.b64encode(ecdsa_public_key(der_spki)).decode("ascii"),
            "keyMaterialType": "ASYMMETRIC_PUBLIC",
        },
        "status": "ENABLED",
        "keyId": key_id,
        "outputPrefixType": "TINK",
    }


def tink_signature(key_id: int, der_sig: bytes) -> str:
    return base64.b64encode(b"\x01" + key_id.to_bytes(4, "big") + der_sig).decode("ascii")


pub_a = (work / "pub_a.der").read_bytes()
pub_b = (work / "pub_b.der").read_bytes()
sig_a = (work / "sig_a.der").read_bytes()
sig_b = (work / "sig_b.der").read_bytes()
body = (work / "body.json").read_text("utf-8")
tampered = body.replace('"steps"', '"sleep"')
assert tampered != body

keyset = {"primaryKeyId": KEY_A, "key": [key_entry(KEY_A, pub_a)]}
keyset_rotated = {"primaryKeyId": KEY_B, "key": [key_entry(KEY_A, pub_a), key_entry(KEY_B, pub_b)]}

cases = [
    {"name": "valid", "body": body, "signature": tink_signature(KEY_A, sig_a), "expect": "valid"},
    {"name": "tampered_body", "body": tampered, "signature": tink_signature(KEY_A, sig_a), "expect": "invalid"},
    # Signed by key B but carrying key A's id: a known key id that does not verify.
    {"name": "wrong_key", "body": body, "signature": tink_signature(KEY_A, sig_b), "expect": "invalid"},
    {"name": "not_base64", "body": body, "signature": "%%not*base64%%", "expect": "invalid"},
    # Signed by key B under its own id, absent from "keyset": the refetch rule applies.
    {"name": "unknown_key_id", "body": body, "signature": tink_signature(KEY_B, sig_b), "expect": "unknown_key_id"},
]

vectors = {
    "generator": "gen_vectors.sh (openssl ecparam prime256v1, openssl dgst -sha256 -sign; stdlib python for the Tink framing)",
    "key_ids": {"a": KEY_A, "b": KEY_B},
    "keyset": keyset,
    "keyset_rotated": keyset_rotated,
    "cases": cases,
}
out_vectors.write_text(json.dumps(vectors, indent=2) + "\n", "utf-8")

selfcheck = {
    "source": "tests/fixtures/google_health_signature/vectors.json (case 'valid'); regenerate with gen_vectors.sh",
    "keyset": keyset,
    "body": body,
    "signature": cases[0]["signature"],
}
out_selfcheck.write_text(json.dumps(selfcheck, indent=2) + "\n", "utf-8")
PY

echo "wrote $here/vectors.json and $package_data/selfcheck_vector.json"
