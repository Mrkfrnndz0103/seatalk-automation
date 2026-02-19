import asyncio
import hashlib
import json
import logging
import re
import time
from pathlib import Path

from app.config import Settings
from app.integrations.google_sheets import GoogleSheetsClient
from app.integrations.supabase_sink import SupabaseSink
from app.seatalk.system_account_client import SeaTalkSystemAccountClient
from app.time_utils import format_local_timestamp, now_local
from app.workflows.stuckup.service import StuckupService

logger = logging.getLogger(__name__)


class StuckupMonitor:
    _SCHEDULED_SYNC_TS_STATE_KEY = "stuckup_last_scheduled_sync_ts"
    _DASHBOARD_TRIGGER_VALUE_STATE_KEY = "stuckup_dashboard_alert_trigger_value"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sheets = GoogleSheetsClient(settings)
        self._supabase = SupabaseSink(settings)
        self._system_account = SeaTalkSystemAccountClient(settings.stuckup_dashboard_alert_system_webhook_url)
        self._service = StuckupService(settings)
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._state_path = Path(settings.stuckup_state_path)
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._scheduled_state_path = self._state_path.with_name("scheduled_sync_state.txt")
        self._dashboard_trigger_state_path = self._state_path.with_name("dashboard_alert_trigger_state.txt")
        self._last_scheduled_sync_ts: float | None = None
        self._last_dashboard_trigger_value: str | None = None
        self._last_status: dict[str, str | int | None] = {
            "monitor": "idle",
            "last_check_at": None,
            "last_change_detected_at": None,
            "last_scheduled_sync_at": None,
            "last_summary_refresh_at": None,
            "last_summary_refresh_status": None,
            "last_summary_refresh_message": None,
            "last_sync_status": None,
            "last_sync_message": None,
            "last_source_rows": 0,
            "last_upserted_rows": 0,
            "last_exported_rows": 0,
            "last_exported_columns": 0,
            "last_dashboard_alert_check_at": None,
            "last_dashboard_alert_sent_at": None,
            "last_dashboard_alert_status": None,
            "last_dashboard_alert_message": None,
        }

    def start(self) -> None:
        if not self._settings.stuckup_auto_sync_enabled:
            logger.info("stuckup auto-sync is disabled")
            self._last_status["monitor"] = "disabled"
            return
        if not self._settings.stuckup_source_spreadsheet_id or not self._settings.stuckup_target_spreadsheet_id:
            logger.warning("stuckup monitor not started: source/target spreadsheet ID is missing")
            self._last_status["monitor"] = "not_started_missing_sheet_config"
            return
        if not self._settings.google_service_account_file:
            logger.warning("stuckup monitor not started: GOOGLE_SERVICE_ACCOUNT_FILE is missing")
            self._last_status["monitor"] = "not_started_missing_google_credentials"
            return
        if self._task and not self._task.done():
            return
        self._last_scheduled_sync_ts = self._load_last_scheduled_sync_ts()
        self._last_dashboard_trigger_value = self._load_last_dashboard_trigger_value()
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("stuckup monitor started")
        self._last_status["monitor"] = "running"

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task
            logger.info("stuckup monitor stopped")
        self._last_status["monitor"] = "stopped"

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                mode = self._settings.stuckup_sync_mode.strip().lower()
                if mode in {"row_change", "both"}:
                    await self._check_reference_row_and_sync()
                if mode in {"scheduled", "both"}:
                    await self._check_scheduled_sync()
                await self._refresh_dashboard_summary_only()
                await self._check_dashboard_alert_trigger_and_notify()
            except Exception:
                logger.exception("stuckup monitor iteration failed")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=max(5, self._settings.stuckup_poll_interval_seconds),
                )
            except asyncio.TimeoutError:
                pass

    async def _check_scheduled_sync(self) -> None:
        interval = max(30, self._settings.stuckup_scheduled_sync_interval_seconds)
        now_ts = time.time()
        if self._last_scheduled_sync_ts is not None and (now_ts - self._last_scheduled_sync_ts) < interval:
            return

        self._last_scheduled_sync_ts = now_ts
        self._save_last_scheduled_sync_ts(now_ts)
        self._last_status["last_scheduled_sync_at"] = format_local_timestamp(self._settings)
        logger.info("stuckup scheduled sync triggered")
        result = self._service.sync_source_sheet_to_supabase()
        self._record_sync_result(result.status, result.message, result.source_rows, result.upserted_rows, result.exported_rows, result.exported_columns)
        logger.info(
            "stuckup scheduled sync result: status=%s message=%s source_rows=%s upserted_rows=%s exported_rows=%s",
            result.status,
            result.message,
            result.source_rows,
            result.upserted_rows,
            result.exported_rows,
        )

    async def _check_reference_row_and_sync(self) -> None:
        self._last_status["last_check_at"] = format_local_timestamp(self._settings)
        row = self._settings.stuckup_reference_row
        reference_range = self._build_reference_row_range(row)
        values = self._sheets.read_values(
            spreadsheet_id=self._settings.stuckup_source_spreadsheet_id,
            worksheet_name=self._settings.stuckup_source_worksheet_name,
            cell_range=reference_range,
        )

        row_values = values[0] if values else []
        fingerprint = hashlib.sha256(json.dumps(row_values, ensure_ascii=True).encode("utf-8")).hexdigest()

        previous = self._load_last_fingerprint()
        if previous == fingerprint:
            logger.debug("stuckup reference row unchanged")
            return

        self._save_last_fingerprint(fingerprint)
        if previous is None:
            logger.info("stuckup monitor baseline set from reference row %s", row)
            self._last_status["last_sync_status"] = "baseline_set"
            self._last_status["last_sync_message"] = f"baseline set from row {row}"
            return

        logger.info("stuckup reference row changed, triggering sync")
        self._last_status["last_change_detected_at"] = format_local_timestamp(self._settings)
        result = self._service.sync_source_sheet_to_supabase()
        self._record_sync_result(result.status, result.message, result.source_rows, result.upserted_rows, result.exported_rows, result.exported_columns)
        logger.info(
            "stuckup auto-sync result: status=%s message=%s source_rows=%s upserted_rows=%s exported_rows=%s",
            result.status,
            result.message,
            result.source_rows,
            result.upserted_rows,
            result.exported_rows,
        )

    def _load_last_fingerprint(self) -> str | None:
        result, value = self._supabase.get_reference_fingerprint()
        if result.status == "ok":
            return value
        if result.status == "error":
            logger.warning("fallback to local stuckup state file due to supabase read error: %s", result.message)

        if not self._state_path.exists():
            return None
        value = self._state_path.read_text(encoding="utf-8").strip()
        return value or None

    def _save_last_fingerprint(self, value: str) -> None:
        result = self._supabase.set_reference_fingerprint(value)
        if result.status == "ok":
            return
        if result.status == "error":
            logger.warning("fallback to local stuckup state file due to supabase write error: %s", result.message)
        self._state_path.write_text(value, encoding="utf-8")

    def _build_reference_row_range(self, row: int) -> str:
        # Build row-check range using configured source range columns.
        # Example: source A1:AL -> reference A2:AL2
        raw = self._settings.stuckup_source_range.upper()
        cols = re.findall(r"[A-Z]+", raw)
        if not cols:
            return f"A{row}:ZZ{row}"
        start_col = cols[0]
        end_col = cols[1] if len(cols) > 1 else cols[0]
        return f"{start_col}{row}:{end_col}{row}"

    def _load_last_scheduled_sync_ts(self) -> float | None:
        result, value = self._supabase.get_state(self._SCHEDULED_SYNC_TS_STATE_KEY)
        if result.status == "ok" and value:
            try:
                return float(value)
            except ValueError:
                logger.warning("invalid scheduled sync timestamp in supabase state: %s", value)
        elif result.status == "error":
            logger.warning("fallback to local scheduled sync state file due to supabase read error: %s", result.message)

        if not self._scheduled_state_path.exists():
            return None
        try:
            value = self._scheduled_state_path.read_text(encoding="utf-8").strip()
            return float(value) if value else None
        except ValueError:
            logger.warning("invalid scheduled sync timestamp in local state file")
            return None

    def _save_last_scheduled_sync_ts(self, value: float) -> None:
        text = str(value)
        result = self._supabase.set_state(self._SCHEDULED_SYNC_TS_STATE_KEY, text)
        if result.status == "ok":
            return
        if result.status == "error":
            logger.warning("fallback to local scheduled sync state file due to supabase write error: %s", result.message)
        self._scheduled_state_path.write_text(text, encoding="utf-8")

    def get_status(self) -> dict[str, str | int | bool | None]:
        return {
            "auto_sync_enabled": self._settings.stuckup_auto_sync_enabled,
            "poll_interval_seconds": self._settings.stuckup_poll_interval_seconds,
            "sync_mode": self._settings.stuckup_sync_mode,
            "scheduled_sync_interval_seconds": self._settings.stuckup_scheduled_sync_interval_seconds,
            "reference_row": self._settings.stuckup_reference_row,
            "source_worksheet": self._settings.stuckup_source_worksheet_name,
            "source_range": self._settings.stuckup_source_range,
            "target_worksheet": self._settings.stuckup_target_worksheet_name,
            **self._last_status,
        }

    def _record_sync_result(
        self,
        status: str,
        message: str,
        source_rows: int,
        upserted_rows: int,
        exported_rows: int,
        exported_columns: int,
    ) -> None:
        self._last_status["last_sync_status"] = status
        self._last_status["last_sync_message"] = message
        self._last_status["last_source_rows"] = source_rows
        self._last_status["last_upserted_rows"] = upserted_rows
        self._last_status["last_exported_rows"] = exported_rows
        self._last_status["last_exported_columns"] = exported_columns

    async def _refresh_dashboard_summary_only(self) -> None:
        try:
            self._service.refresh_dashboard_summary_only()
            self._last_status["last_summary_refresh_at"] = format_local_timestamp(self._settings)
            self._last_status["last_summary_refresh_status"] = "ok"
            self._last_status["last_summary_refresh_message"] = "dashboard summary refreshed"
        except Exception as exc:
            logger.exception("dashboard summary refresh failed")
            self._last_status["last_summary_refresh_at"] = format_local_timestamp(self._settings)
            self._last_status["last_summary_refresh_status"] = "error"
            self._last_status["last_summary_refresh_message"] = str(exc)

    async def _check_dashboard_alert_trigger_and_notify(self) -> None:
        self._last_status["last_dashboard_alert_check_at"] = format_local_timestamp(self._settings)

        if not self._settings.stuckup_dashboard_alert_enabled:
            self._last_status["last_dashboard_alert_status"] = "disabled"
            self._last_status["last_dashboard_alert_message"] = "dashboard alert disabled"
            return

        if not self._system_account.enabled:
            self._last_status["last_dashboard_alert_status"] = "skipped"
            self._last_status["last_dashboard_alert_message"] = "system account webhook URL is not configured"
            return

        current_value = self._read_dashboard_alert_trigger_cell()
        trigger_value = self._settings.stuckup_dashboard_alert_trigger_value
        current_normalized = self._normalize_trigger_value(current_value)
        trigger_normalized = self._normalize_trigger_value(trigger_value)

        if self._last_dashboard_trigger_value is None:
            self._last_dashboard_trigger_value = current_value
            self._save_last_dashboard_trigger_value(current_value)
            self._last_status["last_dashboard_alert_status"] = "baseline_set"
            self._last_status["last_dashboard_alert_message"] = (
                f"baseline captured from "
                f"{self._settings.stuckup_dashboard_alert_trigger_worksheet_name}!"
                f"{self._settings.stuckup_dashboard_alert_trigger_cell}={current_value or '<empty>'}"
            )
            return

        previous_normalized = self._normalize_trigger_value(self._last_dashboard_trigger_value)
        if current_normalized != trigger_normalized:
            if current_value != self._last_dashboard_trigger_value:
                self._last_dashboard_trigger_value = current_value
                self._save_last_dashboard_trigger_value(current_value)
            self._last_status["last_dashboard_alert_status"] = "waiting"
            self._last_status["last_dashboard_alert_message"] = (
                f"waiting for trigger value '{trigger_value}' "
                f"(current: '{current_value or '<empty>'}')"
            )
            return

        if previous_normalized == trigger_normalized:
            self._last_status["last_dashboard_alert_status"] = "already_triggered"
            self._last_status["last_dashboard_alert_message"] = (
                "trigger is unchanged; waiting for a non-trigger value before next alert"
            )
            return

        alert_text = self._build_dashboard_alert_text()
        try:
            image_base64 = self._service.capture_dashboard_range_png_base64()
            await self._system_account.send_text_message(
                content=alert_text,
                at_all=self._settings.stuckup_dashboard_alert_at_all,
            )
            await self._system_account.send_image_message(
                image_base64=image_base64,
            )
        except Exception as exc:
            logger.exception("failed to send dashboard alert via system account")
            self._last_status["last_dashboard_alert_status"] = "error"
            self._last_status["last_dashboard_alert_message"] = str(exc)
            return

        self._last_dashboard_trigger_value = current_value
        self._save_last_dashboard_trigger_value(current_value)
        self._last_status["last_dashboard_alert_sent_at"] = format_local_timestamp(self._settings)
        self._last_status["last_dashboard_alert_status"] = "sent"
        self._last_status["last_dashboard_alert_message"] = "dashboard alert sent via system account"
        logger.info(
            "stuckup dashboard alert sent via system account webhook trigger_cell=%s!%s capture_range=%s!%s",
            self._settings.stuckup_dashboard_alert_trigger_worksheet_name,
            self._settings.stuckup_dashboard_alert_trigger_cell,
            self._settings.stuckup_dashboard_capture_worksheet_name,
            self._settings.stuckup_dashboard_capture_range,
        )

    def _read_dashboard_alert_trigger_cell(self) -> str:
        values = self._sheets.read_values(
            spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
            worksheet_name=self._settings.stuckup_dashboard_alert_trigger_worksheet_name,
            cell_range=self._settings.stuckup_dashboard_alert_trigger_cell,
        )
        return values[0][0].strip() if values and values[0] else ""

    def _load_last_dashboard_trigger_value(self) -> str | None:
        result, value = self._supabase.get_state(self._DASHBOARD_TRIGGER_VALUE_STATE_KEY)
        if result.status == "ok":
            return value
        if result.status == "error":
            logger.warning("fallback to local dashboard trigger state file due to supabase read error: %s", result.message)

        if not self._dashboard_trigger_state_path.exists():
            return None
        return self._dashboard_trigger_state_path.read_text(encoding="utf-8")

    def _save_last_dashboard_trigger_value(self, value: str) -> None:
        result = self._supabase.set_state(self._DASHBOARD_TRIGGER_VALUE_STATE_KEY, value)
        if result.status == "ok":
            return
        if result.status == "error":
            logger.warning("fallback to local dashboard trigger state file due to supabase write error: %s", result.message)
        self._dashboard_trigger_state_path.write_text(value, encoding="utf-8")

    @staticmethod
    def _normalize_trigger_value(value: str | None) -> str:
        return (value or "").strip().lower()

    def _build_dashboard_alert_text(self) -> str:
        raw_template = (
            self._settings.stuckup_dashboard_alert_text_template
            or "Outbound Stuck at SOC_Staging Stuckup Validation Report {date}"
        )
        date_format = self._settings.stuckup_dashboard_alert_date_format or "%Y-%m-%d"
        try:
            date_text = now_local(self._settings).strftime(date_format)
        except Exception:
            date_text = now_local(self._settings).strftime("%Y-%m-%d")

        return raw_template.replace("{date}", date_text).strip()
