import json
import re
from pathlib import Path

from app.config import Settings
from app.integrations.google_sheets import GoogleSheetsClient
from app.integrations.supabase_sink import SupabaseSink
from app.workflows.stuckup.models import StuckupSyncResult


class StuckupService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._google_sheets = GoogleSheetsClient(settings)
        self._supabase = SupabaseSink(settings)

        self._backup_path = Path(settings.stuckup_raw_backup_path)
        self._backup_path.parent.mkdir(parents=True, exist_ok=True)

    def sync_source_sheet_to_supabase(self) -> StuckupSyncResult:
        if not self._settings.stuckup_source_spreadsheet_id:
            return self._error("STUCKUP_SOURCE_SPREADSHEET_ID is not configured")
        if not self._settings.stuckup_target_spreadsheet_id:
            return self._error("STUCKUP_TARGET_SPREADSHEET_ID is not configured")

        try:
            values = self._google_sheets.read_values(
                spreadsheet_id=self._settings.stuckup_source_spreadsheet_id,
                worksheet_name=self._settings.stuckup_source_worksheet_name,
                cell_range=self._settings.stuckup_source_range,
            )
        except Exception as exc:
            return self._error(f"google source read failed: {exc}")
        if not values:
            return self._error("source sheet is empty")

        source_headers = [str(v).strip() for v in values[0]]
        normalized_headers = self._normalize_headers(source_headers)
        allowed_statuses = {v.strip() for v in self._settings.stuckup_filter_status_values.split(",") if v.strip()}

        source_records: list[dict[str, str]] = []
        for row in values[1:]:
            record: dict[str, str] = {}
            for idx, normalized in enumerate(normalized_headers):
                record[normalized] = row[idx] if idx < len(row) else ""
            if record.get("status_desc", "") in allowed_statuses:
                source_records.append(record)

        self._write_backup(source_records)

        upsert_result = self._supabase.upsert_rows(
            rows=source_records,
            conflict_column=self._settings.supabase_stuckup_conflict_column,
        )
        if upsert_result.status != "ok":
            return self._error(
                f"supabase upsert failed: {upsert_result.message}",
                source_rows=len(source_records),
            )

        source_to_normalized = {source_headers[i]: normalized_headers[i] for i in range(len(source_headers))}
        requested_export_headers = [v.strip() for v in self._settings.stuckup_export_columns.split(",") if v.strip()]
        if not requested_export_headers:
            return self._error("STUCKUP_EXPORT_COLUMNS is empty", source_rows=len(source_records))

        selected_source_headers: list[str] = []
        selected_normalized_headers: list[str] = []
        for header in requested_export_headers:
            normalized = source_to_normalized.get(header)
            if not normalized:
                normalized = self._normalize_header_name(header)
            selected_source_headers.append(header)
            selected_normalized_headers.append(normalized)

        fetch_result, supabase_rows = self._supabase.fetch_all_rows(order_by=self._settings.supabase_stuckup_conflict_column)
        if fetch_result.status != "ok":
            return self._error(
                f"supabase fetch failed: {fetch_result.message}",
                source_rows=len(source_records),
                upserted_rows=len(source_records),
            )

        export_values: list[list[str]] = [selected_source_headers]
        for row in supabase_rows:
            export_values.append([str(row.get(column, "")) for column in selected_normalized_headers])

        try:
            self._google_sheets.overwrite_values(
                spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
                worksheet_name=self._settings.stuckup_target_worksheet_name,
                values=export_values,
            )
        except Exception as exc:
            return self._error(
                f"google target write failed: {exc}",
                source_rows=len(source_records),
                upserted_rows=len(source_records),
            )

        return StuckupSyncResult(
            status="ok",
            message="source sheet synced to supabase and exported to target sheet",
            source_rows=len(source_records),
            upserted_rows=len(source_records),
            exported_rows=max(len(export_values) - 1, 0),
            exported_columns=len(selected_source_headers),
        )

    @staticmethod
    def _normalize_headers(headers: list[str]) -> list[str]:
        seen: dict[str, int] = {}
        normalized: list[str] = []
        for idx, header in enumerate(headers):
            base = re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")
            if not base:
                base = f"col_{idx + 1}"
            count = seen.get(base, 0)
            seen[base] = count + 1
            normalized.append(base if count == 0 else f"{base}_{count + 1}")
        return normalized

    @staticmethod
    def _normalize_header_name(header: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")

    def _write_backup(self, rows: list[dict[str, str]]) -> None:
        with self._backup_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")

    @staticmethod
    def _error(
        message: str,
        *,
        source_rows: int = 0,
        upserted_rows: int = 0,
        exported_rows: int = 0,
        exported_columns: int = 0,
    ) -> StuckupSyncResult:
        return StuckupSyncResult(
            status="error",
            message=message,
            source_rows=source_rows,
            upserted_rows=upserted_rows,
            exported_rows=exported_rows,
            exported_columns=exported_columns,
        )
