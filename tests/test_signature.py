import hashlib

from app.seatalk.signature import is_valid_signature


def test_signature_valid() -> None:
    secret = "abc123"
    body = b'{"hello":"world"}'
    signature = hashlib.sha256(body + secret.encode("utf-8")).hexdigest()
    assert is_valid_signature(secret, body, signature)


def test_signature_invalid() -> None:
    assert not is_valid_signature("abc", b"payload", "wrong")


def test_signature_missing_secret_allows() -> None:
    assert is_valid_signature("", b"payload", None)
