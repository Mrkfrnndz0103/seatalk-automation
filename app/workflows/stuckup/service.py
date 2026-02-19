import json
import re
import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app.integrations.google_sheets import GoogleSheetsClient
from app.integrations.supabase_sink import SupabaseSink
from app.time_utils import format_local_timestamp
from app.workflows.stuckup.models import StuckupSyncResult

logger = logging.getLogger(__name__)


class StuckupService:
    _CLAIMS_RAW_MAX_EXPORT_COLUMNS = 17  # Keep column R+ formula columns intact.
    _DASHBOARD_SUMMARY_CLEAR_RANGE = "C4:AA9"
    _DASHBOARD_SUMMARY_START_CELL = "C4"

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
        data_hash = hashlib.sha256(
            json.dumps(source_records, ensure_ascii=True, sort_keys=True).encode("utf-8")
        ).hexdigest()
        _, previous_hash = self._supabase.get_data_hash()
        is_updated = previous_hash != data_hash
        sync_status = "Updated" if is_updated else "no update"
        conflict_column = self._settings.supabase_stuckup_conflict_column

        if is_updated:
            upsert_result = self._supabase.upsert_rows(
                rows=source_records,
                conflict_column=conflict_column,
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
        target_is_claims_raw = self._is_claims_raw_sheet(self._settings.stuckup_target_worksheet_name)
        if target_is_claims_raw and len(selected_source_headers) > self._CLAIMS_RAW_MAX_EXPORT_COLUMNS:
            logger.warning(
                "target worksheet '%s' allows up to %s exported columns; truncating from %s",
                self._settings.stuckup_target_worksheet_name,
                self._CLAIMS_RAW_MAX_EXPORT_COLUMNS,
                len(selected_source_headers),
            )
            selected_source_headers = selected_source_headers[: self._CLAIMS_RAW_MAX_EXPORT_COLUMNS]
            selected_normalized_headers = selected_normalized_headers[: self._CLAIMS_RAW_MAX_EXPORT_COLUMNS]

        fetch_result, supabase_rows = self._supabase.fetch_all_rows(order_by=conflict_column)
        if fetch_result.status != "ok":
            return self._error(
                f"supabase fetch failed: {fetch_result.message}",
                source_rows=len(source_records),
                upserted_rows=len(source_records) if is_updated else 0,
            )

        source_conflict_values = {
            str(record.get(conflict_column, "")).strip()
            for record in source_records
            if str(record.get(conflict_column, "")).strip()
        }
        stale_conflict_values = sorted(
            {
                str(row.get(conflict_column, "")).strip()
                for row in supabase_rows
                if str(row.get(conflict_column, "")).strip()
                and str(row.get(conflict_column, "")).strip() not in source_conflict_values
            }
        )
        if stale_conflict_values:
            delete_result = self._supabase.delete_rows_by_values(conflict_column, stale_conflict_values)
            if delete_result.status != "ok":
                return self._error(
                    f"supabase cleanup failed: {delete_result.message}",
                    source_rows=len(source_records),
                    upserted_rows=len(source_records) if is_updated else 0,
                )
            # Stale rows were removed, so this run produced an effective update.
            sync_status = "Updated"
            fetch_result, supabase_rows = self._supabase.fetch_all_rows(order_by=conflict_column)
            if fetch_result.status != "ok":
                return self._error(
                    f"supabase fetch failed after cleanup: {fetch_result.message}",
                    source_rows=len(source_records),
                    upserted_rows=len(source_records) if is_updated else 0,
                )

        export_values: list[list[str]] = [selected_source_headers]
        for row in supabase_rows:
            export_values.append([str(row.get(column, "")) for column in selected_normalized_headers])

        try:
            # 1) Write sync log in columns A:B, latest at row 2
            existing_log_rows = self._google_sheets.read_values(
                spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
                worksheet_name=self._settings.stuckup_log_worksheet_name,
                cell_range="A2:B1000",
            )
            timestamp = format_local_timestamp(self._settings)
            new_log_rows = [[timestamp, sync_status]] + existing_log_rows

            self._google_sheets.clear_range(
                spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
                worksheet_name=self._settings.stuckup_log_worksheet_name,
                cell_range="A:B",
            )
            self._google_sheets.update_values(
                spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
                worksheet_name=self._settings.stuckup_log_worksheet_name,
                start_cell="A1",
                values=[["run_time", "status"]] + new_log_rows,
            )

            # 2) Write data table in columns A onward
            self._google_sheets.clear_range(
                spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
                worksheet_name=self._settings.stuckup_target_worksheet_name,
                cell_range="A:Q" if target_is_claims_raw else "A:ZZ",
            )
            required_rows = max(len(export_values), 1)
            required_columns = max(len(export_values[0]) if export_values else 1, 1)
            self._google_sheets.ensure_grid_size(
                spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
                worksheet_name=self._settings.stuckup_target_worksheet_name,
                min_rows=required_rows,
                min_columns=required_columns,
            )
            write_response = self._google_sheets.update_values(
                spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
                worksheet_name=self._settings.stuckup_target_worksheet_name,
                start_cell="A1",
                values=export_values,
            )
            logger.info(
                "stuckup google write response: updatedRows=%s updatedColumns=%s updatedCells=%s requestedRows=%s requestedColumns=%s",
                write_response.get("updatedRows"),
                write_response.get("updatedColumns"),
                write_response.get("updatedCells"),
                required_rows,
                required_columns,
            )

            # 3) Refresh dashboard summary paragraph.
            self.refresh_dashboard_summary_only()
        except Exception as exc:
            return self._error(
                f"google target write failed: {exc}",
                source_rows=len(source_records),
                upserted_rows=len(source_records) if is_updated else 0,
            )

        self._supabase.set_data_hash(data_hash)

        return StuckupSyncResult(
            status="ok",
            message=f"source sheet synced to supabase and exported to target sheet ({sync_status})",
            source_rows=len(source_records),
            upserted_rows=len(source_records) if is_updated else 0,
            exported_rows=max(len(export_values) - 1, 0),
            exported_columns=len(selected_source_headers),
        )

    def refresh_dashboard_summary_only(self) -> None:
        dashboard_values = self._read_dashboard_block_stable()
        summary_lines = self._build_dashboard_summary_from_block(dashboard_values)
        summary_paragraph = self._format_summary_paragraph(summary_lines)
        self._google_sheets.ensure_grid_size(
            spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
            worksheet_name="dashboard_summary",
            min_rows=8,
            min_columns=28,
        )
        self._google_sheets.clear_range(
            spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
            worksheet_name="dashboard_summary",
            cell_range=self._DASHBOARD_SUMMARY_CLEAR_RANGE,
        )
        self._google_sheets.update_values(
            spreadsheet_id=self._settings.stuckup_target_spreadsheet_id,
            worksheet_name="dashboard_summary",
            start_cell=self._DASHBOARD_SUMMARY_START_CELL,
            values=[[summary_paragraph]],
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

    @staticmethod
    def _is_claims_raw_sheet(worksheet_name: str) -> bool:
        return worksheet_name.strip().lower() == "claims_raw"

    def _build_dashboard_summary_from_block(self, values: list[list[str]]) -> list[str]:
        timestamp = format_local_timestamp(self._settings)
        if not values:
            return [
                f"As of {timestamp}, the dashboard block at B10:AB43 is empty, so no trend can be computed.",
                "Action Taken: Performed a data refresh check and queued the next sync to repopulate dashboard metrics.",
            ]

        region_header_idx = -1
        region_col_idx = -1
        for idx, row in enumerate(values):
            for col_idx, cell in enumerate(row):
                if str(cell).strip().lower() == "region":
                    region_header_idx = idx
                    region_col_idx = col_idx
                    break
            if region_header_idx >= 0:
                break

        if region_col_idx < 0:
            region_col_idx = 1

        ave_col_idx = region_col_idx + 1
        total_col_idx = region_col_idx + 2
        latest_col_idx = region_col_idx + 3
        prev_col_idx = region_col_idx + 4
        cluster_marker_col_idx = region_col_idx + 13
        cluster_name_col_idx = region_col_idx + 14
        hub_name_col_idx = region_col_idx + 15
        pct_col_idx = region_col_idx + 18

        region_totals: list[tuple[str, int]] = []
        total_row: list[str] | None = None
        header_row: list[str] = values[region_header_idx] if region_header_idx >= 0 else []

        if region_header_idx >= 0:
            for row in values[region_header_idx + 1 :]:
                name = self._cell(row, region_col_idx)
                if not name:
                    continue
                if name.lower() == "total":
                    total_row = row
                    break
                total_l7d = self._to_int(self._cell(row, total_col_idx))
                if total_l7d is not None:
                    region_totals.append((name, total_l7d))

        ave_l7d = self._to_int(self._cell(total_row or [], ave_col_idx))
        total_l7d = self._to_int(self._cell(total_row or [], total_col_idx))
        latest_label = self._cell(header_row, latest_col_idx) or "latest day"
        latest_count = self._to_int(self._cell(total_row or [], latest_col_idx))
        prev_label = self._cell(header_row, prev_col_idx) or "previous day"
        prev_count = self._to_int(self._cell(total_row or [], prev_col_idx))

        top_regions = sorted(region_totals, key=lambda item: item[1], reverse=True)[:3]
        top_regions_text = ", ".join(f"{name} ({count})" for name, count in top_regions) if top_regions else "n/a"

        clusters: list[tuple[str, float]] = []
        hubs: list[tuple[str, float]] = []
        seen_hubs: set[str] = set()
        for row in values:
            if self._cell(row, cluster_marker_col_idx) == "*":
                cluster_name = self._cell(row, cluster_name_col_idx)
                cluster_pct = self._to_percent(self._cell(row, pct_col_idx))
                if cluster_name and cluster_pct is not None:
                    clusters.append((cluster_name, cluster_pct))

            hub_name = self._cell(row, hub_name_col_idx)
            hub_pct = self._to_percent(self._cell(row, pct_col_idx))
            if hub_name and hub_pct is not None and hub_name.lower() != "top dc/hubs affected:":
                if hub_name not in seen_hubs:
                    hubs.append((hub_name, hub_pct))
                    seen_hubs.add(hub_name)

        clusters.sort(key=lambda item: item[1], reverse=True)
        hubs.sort(key=lambda item: item[1], reverse=True)
        top_clusters_text = ", ".join(f"{name} ({pct:.2f}%)" for name, pct in clusters[:3]) if clusters else "n/a"
        top_hubs_text = ", ".join(f"{name} ({pct:.2f}%)" for name, pct in hubs[:3]) if hubs else "n/a"

        lead_cluster = clusters[0][0] if clusters else "the highest-impact cluster"
        lead_hubs = [name for name, _ in hubs[:2]]
        lead_hub_text = " and ".join(lead_hubs) if lead_hubs else "priority destination hubs"

        sentence_1 = (
            f"As of {timestamp}, SOC_Staging recorded {latest_count if latest_count is not None else 'n/a'} stuck orders on "
            f"{latest_label}, compared with {prev_count if prev_count is not None else 'n/a'} on {prev_label}, with "
            f"a 7-day total of {total_l7d if total_l7d is not None else 'n/a'} and an average of "
            f"{ave_l7d if ave_l7d is not None else 'n/a'}."
        )
        sentence_2 = f"Top Contributing Regions by Total L7D are {top_regions_text}."
        sentence_3 = (
            f"The most affected clusters and hubs are {top_clusters_text}; TOP hubs include {top_hubs_text}."
        )
        sentence_4 = (
            f"Action Taken: Prioritized the dispatch for {lead_cluster} since these hubs is 1-day dispatch only "
            f"({lead_hub_text}) to reduce ageing backlog before the next validation run."
        )
        return [sentence_1, sentence_2, sentence_3, sentence_4]

    @staticmethod
    def _format_summary_paragraph(lines: list[str]) -> str:
        cleaned = [line.strip() for line in lines if line and line.strip()]
        if not cleaned:
            return ""

        action_line = ""
        body_lines: list[str] = []
        for line in cleaned:
            if line.startswith("Action Taken:"):
                action_line = line
            else:
                body_lines.append(line)

        body = " ".join(body_lines).strip()
        if not action_line:
            return body

        if body:
            return f"{body}\n\n  {action_line}"
        return f"  {action_line}"

    @staticmethod
    def _cell(row: list[str], idx: int) -> str:
        return row[idx].strip() if idx < len(row) and row[idx] is not None else ""

    @staticmethod
    def _to_int(value: str) -> int | None:
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return None

    @staticmethod
    def _to_percent(value: str) -> float | None:
        cleaned = value.replace("%", "").strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _read_dashboard_block_stable(self) -> list[list[str]]:
        spreadsheet_id = self._settings.stuckup_target_spreadsheet_id
        worksheet_name = "dashboard_summary"
        cell_range = "B10:AB43"

        current = self._google_sheets.read_values(
            spreadsheet_id=spreadsheet_id,
            worksheet_name=worksheet_name,
            cell_range=cell_range,
        )
        current_fingerprint = self._fingerprint_block(current)

        # Formula-driven dashboards can lag a few seconds after raw table updates.
        # Read a few times and use the stabilized snapshot.
        for _ in range(4):
            time.sleep(2)
            nxt = self._google_sheets.read_values(
                spreadsheet_id=spreadsheet_id,
                worksheet_name=worksheet_name,
                cell_range=cell_range,
            )
            nxt_fingerprint = self._fingerprint_block(nxt)
            if nxt_fingerprint == current_fingerprint:
                return nxt
            current = nxt
            current_fingerprint = nxt_fingerprint

        return current

    @staticmethod
    def _fingerprint_block(values: list[list[str]]) -> str:
        return hashlib.sha256(json.dumps(values, ensure_ascii=True, sort_keys=False).encode("utf-8")).hexdigest()

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
