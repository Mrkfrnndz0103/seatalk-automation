import asyncio
from pathlib import Path

from app.config import Settings
from app.integrations.types import SinkResult
from app.workflows.stuckup.monitor import StuckupMonitor


class _FakeSheets:
    def __init__(self, initial_value: str) -> None:
        self.value = initial_value

    def read_values(self, spreadsheet_id: str, worksheet_name: str, cell_range: str) -> list[list[str]]:
        return [[self.value]]


class _FakeSupabase:
    def get_state(self, key: str) -> tuple[SinkResult, str | None]:
        return SinkResult("supabase_state", "ok", "state not found"), None

    def set_state(self, key: str, value: str) -> SinkResult:
        return SinkResult("supabase_state", "ok", "state saved")


class _FakeService:
    def capture_dashboard_range_png_base64(self) -> str:
        return "aGVsbG8="


class _FakeSeaTalk:
    def __init__(self) -> None:
        self.text_calls: list[dict[str, str | bool]] = []
        self.image_calls: list[dict[str, str]] = []
        self.enabled = True

    async def send_text_message(self, content: str, *, at_all: bool = False):
        self.text_calls.append({"content": content, "at_all": at_all})
        return {"code": 0}

    async def send_image_message(self, image_base64: str):
        self.image_calls.append({"image_base64": image_base64})
        return {"code": 0}


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        SEATALK_APP_ID="x",
        SEATALK_APP_SECRET="y",
        STUCKUP_TARGET_SPREADSHEET_ID="sheet_1",
        STUCKUP_DASHBOARD_ALERT_SYSTEM_WEBHOOK_URL="https://example.test/webhook",
        STUCKUP_STATE_PATH=tmp_path / "stuckup_state.txt",
    )


def test_dashboard_alert_sends_once_per_updated_transition(tmp_path: Path) -> None:
    monitor = StuckupMonitor(_settings(tmp_path))
    fake_sheets = _FakeSheets(initial_value="no update")
    fake_seatalk = _FakeSeaTalk()
    monitor._sheets = fake_sheets  # type: ignore[assignment]
    monitor._supabase = _FakeSupabase()  # type: ignore[assignment]
    monitor._service = _FakeService()  # type: ignore[assignment]
    monitor._system_account = fake_seatalk  # type: ignore[assignment]

    asyncio.run(monitor._check_dashboard_alert_trigger_and_notify())
    assert monitor.get_status()["last_dashboard_alert_status"] == "baseline_set"
    assert len(fake_seatalk.text_calls) == 0
    assert len(fake_seatalk.image_calls) == 0

    fake_sheets.value = "Updated"
    asyncio.run(monitor._check_dashboard_alert_trigger_and_notify())
    assert monitor.get_status()["last_dashboard_alert_status"] == "sent"
    assert len(fake_seatalk.text_calls) == 1
    assert len(fake_seatalk.image_calls) == 1
    assert "Outbound Stuck at SOC_Staging Stuckup Validation Report" in fake_seatalk.text_calls[0]["content"]
    assert fake_seatalk.text_calls[0]["at_all"] is True

    asyncio.run(monitor._check_dashboard_alert_trigger_and_notify())
    assert monitor.get_status()["last_dashboard_alert_status"] == "already_triggered"
    assert len(fake_seatalk.text_calls) == 1
    assert len(fake_seatalk.image_calls) == 1

    fake_sheets.value = "no update"
    asyncio.run(monitor._check_dashboard_alert_trigger_and_notify())
    assert monitor.get_status()["last_dashboard_alert_status"] == "waiting"

    fake_sheets.value = "UPDATED"
    asyncio.run(monitor._check_dashboard_alert_trigger_and_notify())
    assert monitor.get_status()["last_dashboard_alert_status"] == "sent"
    assert len(fake_seatalk.text_calls) == 2
    assert len(fake_seatalk.image_calls) == 2
