from cryptography.fernet import Fernet
from django.conf import settings

_fernet_instance: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    key = settings.CREDENTIAL_ENCRYPTION_KEY
    if not key:
        key = Fernet.generate_key().decode()
    if isinstance(key, str):
        key = key.encode()
    if len(key) != 44:
        key = Fernet.generate_key()
    _fernet_instance = Fernet(key)
    return _fernet_instance


def encrypt_value(plaintext: str) -> bytes:
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8"))


def decrypt_value(ciphertext: bytes) -> str:
    f = _get_fernet()
    return f.decrypt(ciphertext).decode("utf-8")
