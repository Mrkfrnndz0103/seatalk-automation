import hashlib


def is_valid_signature(signing_secret: str, body: bytes, signature: str | None) -> bool:
    if not signing_secret:
        return True
    if not signature:
        return False
    expected = hashlib.sha256(body + signing_secret.encode("utf-8")).hexdigest()
    return expected == signature.strip().lower()