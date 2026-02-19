import hashlib
import importlib
import json

from fastapi.testclient import TestClient


def _signature(body: bytes) -> str:
    return hashlib.sha256(body + b"test_signing_secret").hexdigest()



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


def _load_main_with_secrets(
    monkeypatch,
    *,
    bot_secret: str,
    system_secret: str,
    system_secrets_csv: str = "",
):
    monkeypatch.setenv("SEATALK_APP_ID", "test_app")
    monkeypatch.setenv("SEATALK_APP_SECRET", "test_secret")
    monkeypatch.setenv("SEATALK_SIGNING_SECRET", bot_secret)
    monkeypatch.setenv("SEATALK_SYSTEM_SIGNING_SECRET", system_secret)
    monkeypatch.setenv("SEATALK_SYSTEM_SIGNING_SECRETS", system_secrets_csv)
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

    r0 = client.get("/")
    assert r0.status_code == 200
    assert r0.json() == {"status": "ok"}

    r1 = client.get("/health")
    assert r1.status_code == 200
    assert r1.json() == {"status": "ok"}

    r2 = client.get("/uptime-ping")
    assert r2.status_code == 200
    assert r2.json() == {"status": "alive"}

    r3 = client.get("/stuckup/status")
    assert r3.status_code == 200
    body = r3.json()
    assert body["auto_sync_enabled"] is False
    assert body["sync_mode"] == "scheduled"
    assert body["reference_row"] == 2


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
    signature = _signature(body)

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


def test_event_verification_signature_accepts_system_secret(monkeypatch) -> None:
    main = _load_main_with_secrets(monkeypatch, bot_secret="bot_secret", system_secret="system_secret")
    client = TestClient(main.app)

    payload = {
        "event_id": "evt-system-1",
        "event_type": "event_verification",
        "timestamp": 1,
        "app_id": "app",
        "event": {"seatalk_challenge": "abc123"},
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hashlib.sha256(body + b"system_secret").hexdigest()

    r = client.post(
        "/callbacks/seatalk",
        content=body,
        headers={"content-type": "application/json", "signature": signature},
    )
    assert r.status_code == 200
    assert r.json() == {"seatalk_challenge": "abc123"}


def test_event_verification_signature_accepts_any_system_secret_from_csv(monkeypatch) -> None:
    main = _load_main_with_secrets(
        monkeypatch,
        bot_secret="bot_secret",
        system_secret="",
        system_secrets_csv="sys_a, sys_b ,sys_c",
    )
    client = TestClient(main.app)

    payload = {
        "event_id": "evt-system-2",
        "event_type": "event_verification",
        "timestamp": 1,
        "app_id": "app",
        "event": {"seatalk_challenge": "abc123"},
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hashlib.sha256(body + b"sys_b").hexdigest()

    r = client.post(
        "/callbacks/seatalk",
        content=body,
        headers={"content-type": "application/json", "signature": signature},
    )
    assert r.status_code == 200
    assert r.json() == {"seatalk_challenge": "abc123"}


def test_group_mention_from_system_account_gets_group_reply(monkeypatch) -> None:
    main = _load_main(monkeypatch)
    client = TestClient(main.app)
    sent: dict[str, str | None] = {}

    async def _fake_send_group_text_message(group_id: str, content: str, *, thread_id: str | None = None):
        sent["group_id"] = group_id
        sent["content"] = content
        sent["thread_id"] = thread_id
        return {"code": 0}

    monkeypatch.setattr(main.seatalk_client, "send_group_text_message", _fake_send_group_text_message)

    payload = {
        "event_id": "evt-3",
        "event_type": "new_mentioned_message_received_from_group_chat",
        "timestamp": 1,
        "app_id": "app",
        "event": {
            "group_id": "g_1",
            "message": {
                "message_id": "m_1",
                "thread_id": "t_1",
                "tag": "text",
                "text": {"plain_text": "hello"},
                "sender": {
                    "seatalk_id": "0",
                    "employee_code": "",
                    "sender_type": 3,
                },
            },
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    r = client.post(
        "/callbacks/seatalk",
        content=body,
        headers={"content-type": "application/json", "signature": _signature(body)},
    )

    assert r.status_code == 200
    assert r.json() == {"code": 0}
    assert sent["group_id"] == "g_1"
    assert sent["thread_id"] == "t_1"
    assert isinstance(sent.get("content"), str)
    assert "Hi!" in (sent["content"] or "")


def test_bot_added_to_group_chat_sends_group_welcome(monkeypatch) -> None:
    main = _load_main(monkeypatch)
    client = TestClient(main.app)
    sent: dict[str, str | None] = {}

    async def _fake_send_group_text_message(group_id: str, content: str, *, thread_id: str | None = None):
        sent["group_id"] = group_id
        sent["content"] = content
        sent["thread_id"] = thread_id
        return {"code": 0}

    monkeypatch.setattr(main.seatalk_client, "send_group_text_message", _fake_send_group_text_message)

    payload = {
        "event_id": "evt-4",
        "event_type": "bot_added_to_group_chat",
        "timestamp": 1,
        "app_id": "app",
        "event": {
            "group": {
                "group_id": "group_nested_1",
                "group_name": "Ops Group",
            },
            "inviter": {
                "employee_code": "e_1",
            },
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    r = client.post(
        "/callbacks/seatalk",
        content=body,
        headers={"content-type": "application/json", "signature": _signature(body)},
    )

    assert r.status_code == 200
    assert r.json() == {"code": 0}
    assert sent["group_id"] == "group_nested_1"
    assert sent["thread_id"] is None
    assert isinstance(sent.get("content"), str)
    assert "/stuckup" in (sent["content"] or "")
