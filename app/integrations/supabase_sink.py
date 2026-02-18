import logging
from typing import Any

from supabase import Client, create_client

from app.config import Settings
from app.integrations.types import SinkResult

logger = logging.getLogger(__name__)


class SupabaseSink:
    def __init__(self, settings: Settings) -> None:
        self._enabled = bool(settings.supabase_url and settings.supabase_service_role_key)
        self._table = settings.supabase_stuckup_table
        self._state_table = settings.supabase_stuckup_state_table
        self._state_key = settings.supabase_stuckup_state_key
        self._data_hash_key = settings.supabase_stuckup_data_hash_key
        self._client: Client | None = None

        if self._enabled:
            self._client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def upsert_rows(self, rows: list[dict[str, Any]], conflict_column: str) -> SinkResult:
        if not self.enabled or not self._client:
            return SinkResult("supabase", "skipped", "not configured")
        if not rows:
            return SinkResult("supabase", "ok", "no rows to upsert")

        try:
            self._client.table(self._table).upsert(rows, on_conflict=conflict_column).execute()
            return SinkResult("supabase", "ok", f"upserted {len(rows)} rows")
        except Exception as exc:
            logger.exception("failed to upsert rows into supabase")
            return SinkResult("supabase", "error", str(exc))

    def fetch_all_rows(self, order_by: str | None = None) -> tuple[SinkResult, list[dict[str, Any]]]:
        if not self.enabled or not self._client:
            return SinkResult("supabase", "skipped", "not configured"), []

        try:
            page_size = 1000
            offset = 0
            rows: list[dict[str, Any]] = []

            while True:
                query = self._client.table(self._table).select("*").range(offset, offset + page_size - 1)
                if order_by:
                    query = query.order(order_by)

                page = query.execute().data or []
                rows.extend(page)

                if len(page) < page_size:
                    break

                offset += page_size

            return SinkResult("supabase", "ok", f"fetched {len(rows)} rows"), rows
        except Exception as exc:
            logger.exception("failed to fetch rows from supabase")
            return SinkResult("supabase", "error", str(exc)), []

    def get_state(self, key: str) -> tuple[SinkResult, str | None]:
        if not self.enabled or not self._client:
            return SinkResult("supabase_state", "skipped", "not configured"), None
        try:
            data = (
                self._client.table(self._state_table)
                .select("value")
                .eq("key", key)
                .limit(1)
                .execute()
                .data
                or []
            )
            if not data:
                return SinkResult("supabase_state", "ok", "state not found"), None
            value = data[0].get("value")
            return SinkResult("supabase_state", "ok", "state loaded"), str(value) if value else None
        except Exception as exc:
            logger.exception("failed to load stuckup state from supabase")
            return SinkResult("supabase_state", "error", str(exc)), None

    def set_state(self, key: str, value: str) -> SinkResult:
        if not self.enabled or not self._client:
            return SinkResult("supabase_state", "skipped", "not configured")
        try:
            self._client.table(self._state_table).upsert(
                [{"key": key, "value": value}],
                on_conflict="key",
            ).execute()
            return SinkResult("supabase_state", "ok", "state saved")
        except Exception as exc:
            logger.exception("failed to save stuckup state to supabase")
            return SinkResult("supabase_state", "error", str(exc))

    def get_reference_fingerprint(self) -> tuple[SinkResult, str | None]:
        return self.get_state(self._state_key)

    def set_reference_fingerprint(self, fingerprint: str) -> SinkResult:
        return self.set_state(self._state_key, fingerprint)

    def get_data_hash(self) -> tuple[SinkResult, str | None]:
        return self.get_state(self._data_hash_key)

    def set_data_hash(self, data_hash: str) -> SinkResult:
        return self.set_state(self._data_hash_key, data_hash)
