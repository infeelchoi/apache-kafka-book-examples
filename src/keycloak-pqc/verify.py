#!/usr/bin/env python3
"""Verify Keycloak tokens signed by Luna HSM with optional PQC signatures.

This script implements the validation steps discussed in the README:
- Fetches the JWKS from a Keycloak realm and validates RS256 JWTs.
- Optionally validates a Dilithium signature that accompanies the token.

The PQC portion uses liboqs bindings when available.  If the module cannot be
imported the script prints an actionable message instead of crashing, which
allows the dry-run flow to succeed even when PQC tooling is not installed yet.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import dataclass
from typing import Optional

import requests
from jose import jwt


@dataclass
class PQCInputs:
    algorithm: str
    signature: bytes
    public_key: bytes


def b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def load_pqc_inputs(args: argparse.Namespace) -> Optional[PQCInputs]:
    if not args.pqc_sig or not args.pqc_public:
        return None
    algorithm = args.pqc_alg or "Dilithium2"
    return PQCInputs(
        algorithm=algorithm,
        signature=b64url_decode(args.pqc_sig),
        public_key=b64url_decode(args.pqc_public),
    )


def verify_rs256(token: str, issuer: str) -> dict:
    jwks_uri = f"{issuer.rstrip('/')}/protocol/openid-connect/certs"
    response = requests.get(jwks_uri, timeout=5)
    response.raise_for_status()
    jwks = response.json()
    claims = jwt.decode(
        token,
        jwks,
        algorithms=["RS256"],
        issuer=issuer,
        options={"verify_aud": False},
    )
    return claims


def verify_pqc(message: bytes, pqc: PQCInputs) -> bool:
    try:
        import oqs  # type: ignore
    except ModuleNotFoundError:
        print(
            "⚠️  python-oqs is not installed; skipping PQC verification."
            " Install with `pip install oqs` to enable this step.",
            file=sys.stderr,
        )
        return False

    with oqs.Signature(pqc.algorithm) as verifier:
        try:
            verifier.set_public_key(pqc.public_key)
        except AttributeError:
            # Older oqs versions use import_public_key
            verifier.import_public_key(pqc.public_key)
        return verifier.verify(message, pqc.signature)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", required=True, help="Path to the JWT file")
    parser.add_argument("--issuer", required=True, help="Realm issuer URL")
    parser.add_argument("--pqc-sig", help="Base64url encoded PQC signature")
    parser.add_argument("--pqc-public", help="Base64url encoded PQC public key")
    parser.add_argument(
        "--pqc-alg",
        help="PQC algorithm name (liboqs identifier). Defaults to Dilithium2",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = open(args.token, "r", encoding="utf-8").read().strip()
    claims = verify_rs256(token, args.issuer)
    print(f"✅ RS256 verification succeeded: sub={claims.get('sub')}")

    pqc_inputs = load_pqc_inputs(args)
    header_b64, payload_b64, _ = token.split(".")
    message = f"{header_b64}.{payload_b64}".encode()

    if pqc_inputs:
        if verify_pqc(message, pqc_inputs):
            print(
                f"✅ PQC verification succeeded using {pqc_inputs.algorithm}."
            )
        else:
            print(
                "❌ PQC verification failed or could not be executed."
                " Check the logs above for details."
            )
            return 1
    else:
        print("ℹ️ No PQC artefacts supplied; skipping PQC verification.")

    print(json.dumps({"claims": claims}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
