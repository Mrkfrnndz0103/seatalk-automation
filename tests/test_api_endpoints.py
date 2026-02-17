import hashlib
import importlib
import json

from fastapi.testclient import TestClient



def _load_main(monkeypatch):
    monkeypatch.setenv("SEATALK_APP_ID", "test_app")
    monkeypatch.setenv("SEATALK_APP_SECRET", "test_secret")
    monkeypatch.setenv("SEATALK_SIGNING_SECRET", "test_signing_secret")
    monkeypatch.setenv("SEATALK_VERIFY_SIGNATURE", "true")
    monkeypatch.setenv("STUCKUP_AUTO_SYNC_ENABLED", "false")

    import app.config as config

    config.get_settings.cache_clear()
    import app.main as main

    main = importlib.reload(main)
    return main


def test_health_and_uptime(monkeypatch) -> None:
    main = _load_main(monkeypatch)
    client = TestClient(main.app)

    r1 = client.get("/health")
    assert r1.status_code == 200
    assert r1.json() == {"status": "ok"}

    r2 = client.get("/uptime-ping")
    assert r2.status_code == 200
    assert r2.json() == {"status": "alive"}


def test_event_verification_signature(monkeypatch) -> None:
    main = _load_main(monkeypatch)
    client = TestClient(main.app)

    payload = {
        "event_id": "evt-1",
        "event_type": "event_verification",
        "timestamp": 1,
        "app_id": "app",
        "event": {"seatalk_challenge": "abc123"},
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hashlib.sha256(body + b"test_signing_secret").hexdigest()

    r = client.post(
        "/callbacks/seatalk",
        content=body,
        headers={"content-type": "application/json", "signature": signature},
    )
    assert r.status_code == 200
    assert r.json() == {"seatalk_challenge": "abc123"}


def test_event_verification_invalid_signature(monkeypatch) -> None:
    main = _load_main(monkeypatch)
    client = TestClient(main.app)

    payload = {
        "event_id": "evt-2",
        "event_type": "event_verification",
        "timestamp": 1,
        "app_id": "app",
        "event": {"seatalk_challenge": "abc123"},
    }

    r = client.post(
        "/callbacks/seatalk",
        json=payload,
        headers={"signature": "invalid"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid callback signature"
