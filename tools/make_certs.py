"""Self-signed TLS certificate for the local nginx edge (localhost and 127.0.0.1).

    python tools/make_certs.py            # writes deploy/certs/cert.pem and key.pem

The files are git-ignored. For a real deployment, replace them with a certificate
from a trusted authority. Existing files are kept unless ``--force`` is given.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

CERTS = Path(__file__).resolve().parents[1] / "deploy" / "certs"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()
    cert_path, key_path = CERTS / "cert.pem", CERTS / "key.pem"
    if cert_path.exists() and key_path.exists() and not args.force:
        print(f"Certificat déjà présent : {cert_path}")
        return 0
    CERTS.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=args.days))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Certificat auto-signé écrit dans {CERTS} (valable {args.days} jours)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
