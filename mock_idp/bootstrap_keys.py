import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _write_private_key(path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def ensure_key(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_private_key(path)


if __name__ == "__main__":
    keys_dir = Path(os.getenv("KEYS_DIR", "/app/keys"))
    ensure_key(keys_dir / "provider_private.pem")
    ensure_key(keys_dir / "client_private.pem")
    print(f"Mock OIDC keys available in {keys_dir}")
