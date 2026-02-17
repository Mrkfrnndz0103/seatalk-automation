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
            query = self._client.table(self._table).select("*").limit(50000)
            if order_by:
                query = query.order(order_by)
            data = query.execute().data or []
            return SinkResult("supabase", "ok", f"fetched {len(data)} rows"), data
        except Exception as exc:
            logger.exception("failed to fetch rows from supabase")
            return SinkResult("supabase", "error", str(exc)), []
