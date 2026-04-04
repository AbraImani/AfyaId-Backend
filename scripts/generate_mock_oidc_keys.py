from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
KEYS_DIR = ROOT / "mock_idp" / "keys"


def write_private_key(path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def main() -> None:
    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    provider_key = KEYS_DIR / "provider_private.pem"
    client_key = KEYS_DIR / "client_private.pem"

    if not provider_key.exists():
        write_private_key(provider_key)
        print(f"Created {provider_key}")
    else:
        print(f"Exists  {provider_key}")

    if not client_key.exists():
        write_private_key(client_key)
        print(f"Created {client_key}")
    else:
        print(f"Exists  {client_key}")


if __name__ == "__main__":
    main()
