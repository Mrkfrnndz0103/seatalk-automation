import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path

from app.config import Settings
from app.integrations.google_sheets import GoogleSheetsClient
from app.integrations.supabase_sink import SupabaseSink
from app.workflows.stuckup.service import StuckupService

logger = logging.getLogger(__name__)


class StuckupMonitor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sheets = GoogleSheetsClient(settings)
        self._supabase = SupabaseSink(settings)
        self._service = StuckupService(settings)
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._state_path = Path(settings.stuckup_state_path)
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if not self._settings.stuckup_auto_sync_enabled:
            logger.info("stuckup auto-sync is disabled")
            return
        if not self._settings.stuckup_source_spreadsheet_id or not self._settings.stuckup_target_spreadsheet_id:
            logger.warning("stuckup monitor not started: source/target spreadsheet ID is missing")
            return
        if not self._settings.google_service_account_file:
            logger.warning("stuckup monitor not started: GOOGLE_SERVICE_ACCOUNT_FILE is missing")
            return
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("stuckup monitor started")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task
            logger.info("stuckup monitor stopped")

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._check_reference_row_and_sync()
            except Exception:
                logger.exception("stuckup monitor iteration failed")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=max(5, self._settings.stuckup_poll_interval_seconds),
                )
            except asyncio.TimeoutError:
                pass

    async def _check_reference_row_and_sync(self) -> None:
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
            return

        logger.info("stuckup reference row changed, triggering sync")
        result = self._service.sync_source_sheet_to_supabase()
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
