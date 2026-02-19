import logging
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import Settings

logger = logging.getLogger(__name__)


class GoogleSheetsClient:
    def __init__(self, settings: Settings) -> None:
        self._credentials_file = Path(settings.google_service_account_file) if settings.google_service_account_file else None

    def _build_service(self):
        if not self._credentials_file or not self._credentials_file.exists():
            raise FileNotFoundError("google service account file not found")
        credentials = service_account.Credentials.from_service_account_file(
            str(self._credentials_file),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def read_values(self, spreadsheet_id: str, worksheet_name: str, cell_range: str) -> list[list[str]]:
        service = self._build_service()
        response = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=self._sheet_range(worksheet_name, cell_range),
        ).execute()
        values: list[list[Any]] = response.get("values", [])
        return [[str(cell).strip() for cell in row] for row in values]

    def read_grid_snapshot(self, spreadsheet_id: str, worksheet_name: str, cell_range: str) -> dict[str, Any]:
        service = self._build_service()
        response = (
            service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                ranges=[self._sheet_range(worksheet_name, cell_range)],
                includeGridData=True,
            )
            .execute()
        )

        sheets = response.get("sheets", [])
        if not sheets:
            raise ValueError(f"worksheet '{worksheet_name}' not found")
        sheet = sheets[0]
        data_blocks = sheet.get("data", [])
        if not data_blocks:
            raise ValueError(f"no grid data returned for '{worksheet_name}'!{cell_range}")
        block = data_blocks[0]

        start_row = int(block.get("startRow", 0))
        start_col = int(block.get("startColumn", 0))
        row_data = block.get("rowData", []) or []
        row_meta = block.get("rowMetadata", []) or []
        col_meta = block.get("columnMetadata", []) or []

        row_count = len(row_meta) if row_meta else len(row_data)
        if row_count < len(row_data):
            row_count = len(row_data)
        col_count = len(col_meta)
        if col_count == 0:
            col_count = max((len((row or {}).get("values", []) or []) for row in row_data), default=0)

        values: list[list[str]] = [["" for _ in range(col_count)] for _ in range(row_count)]
        backgrounds: list[list[dict[str, float] | None]] = [[None for _ in range(col_count)] for _ in range(row_count)]
        text_colors: list[list[dict[str, float] | None]] = [[None for _ in range(col_count)] for _ in range(row_count)]
        font_sizes: list[list[int | None]] = [[None for _ in range(col_count)] for _ in range(row_count)]
        bold: list[list[bool]] = [[False for _ in range(col_count)] for _ in range(row_count)]
        horizontal_alignments: list[list[str]] = [["LEFT" for _ in range(col_count)] for _ in range(row_count)]

        for r in range(row_count):
            row = row_data[r] if r < len(row_data) and row_data[r] is not None else {}
            cell_values = row.get("values", []) or []
            for c in range(col_count):
                cell = cell_values[c] if c < len(cell_values) and cell_values[c] is not None else {}
                values[r][c] = str(cell.get("formattedValue", "")).strip()
                effective_format = cell.get("effectiveFormat", {}) or {}

                bg = (effective_format.get("backgroundColorStyle", {}) or {}).get("rgbColor")
                if not bg:
                    bg = effective_format.get("backgroundColor")
                backgrounds[r][c] = bg if isinstance(bg, dict) else None

                text_format = effective_format.get("textFormat", {}) or {}
                text_color = (text_format.get("foregroundColorStyle", {}) or {}).get("rgbColor")
                if not text_color:
                    text_color = text_format.get("foregroundColor")
                text_colors[r][c] = text_color if isinstance(text_color, dict) else None
                font_sizes[r][c] = int(text_format.get("fontSize")) if text_format.get("fontSize") else None
                bold[r][c] = bool(text_format.get("bold", False))
                horizontal_alignments[r][c] = str(effective_format.get("horizontalAlignment", "LEFT")).upper()

        row_heights = [int((meta or {}).get("pixelSize", 21)) for meta in row_meta]
        if len(row_heights) < row_count:
            row_heights.extend([21] * (row_count - len(row_heights)))
        col_widths = [int((meta or {}).get("pixelSize", 100)) for meta in col_meta]
        if len(col_widths) < col_count:
            col_widths.extend([100] * (col_count - len(col_widths)))

        merges: list[dict[str, int]] = []
        sheet_id = int((sheet.get("properties", {}) or {}).get("sheetId", -1))
        row_end = start_row + row_count
        col_end = start_col + col_count
        for merge in sheet.get("merges", []) or []:
            if int(merge.get("sheetId", -1)) != sheet_id:
                continue

            mr0 = int(merge.get("startRowIndex", 0))
            mr1 = int(merge.get("endRowIndex", 0))
            mc0 = int(merge.get("startColumnIndex", 0))
            mc1 = int(merge.get("endColumnIndex", 0))

            ir0 = max(mr0, start_row)
            ir1 = min(mr1, row_end)
            ic0 = max(mc0, start_col)
            ic1 = min(mc1, col_end)
            if ir0 >= ir1 or ic0 >= ic1:
                continue

            merges.append(
                {
                    "start_row": ir0 - start_row,
                    "end_row": ir1 - start_row,
                    "start_col": ic0 - start_col,
                    "end_col": ic1 - start_col,
                }
            )

        return {
            "values": values,
            "row_heights": row_heights,
            "col_widths": col_widths,
            "backgrounds": backgrounds,
            "text_colors": text_colors,
            "font_sizes": font_sizes,
            "bold": bold,
            "horizontal_alignments": horizontal_alignments,
            "merges": merges,
        }

    def overwrite_values(self, spreadsheet_id: str, worksheet_name: str, values: list[list[str]]) -> None:
        self.clear_range(spreadsheet_id, worksheet_name, "A:ZZ")
        if values:
            self.update_values(spreadsheet_id, worksheet_name, "A1", values)

    def clear_range(self, spreadsheet_id: str, worksheet_name: str, cell_range: str) -> None:
        service = self._build_service()
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=self._sheet_range(worksheet_name, cell_range),
            body={},
        ).execute()

    def update_values(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        start_cell: str,
        values: list[list[str]],
    ) -> dict[str, Any]:
        service = self._build_service()
        return (
            service.spreadsheets()
            .values()
            .update(
            spreadsheetId=spreadsheet_id,
            range=self._sheet_range(worksheet_name, start_cell),
            valueInputOption="USER_ENTERED",
            body={"values": values},
            )
            .execute()
        )

    def ensure_grid_size(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        min_rows: int,
        min_columns: int,
    ) -> None:
        service = self._build_service()
        metadata = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            includeGridData=False,
        ).execute()

        target_props: dict[str, Any] | None = None
        for sheet in metadata.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("title") == worksheet_name:
                target_props = props
                break

        if not target_props:
            raise ValueError(f"worksheet '{worksheet_name}' not found")

        grid = target_props.get("gridProperties", {})
        current_rows = int(grid.get("rowCount", 0))
        current_columns = int(grid.get("columnCount", 0))
        update_fields: list[str] = []
        properties: dict[str, Any] = {"sheetId": target_props["sheetId"], "gridProperties": {}}

        if current_rows < min_rows:
            properties["gridProperties"]["rowCount"] = min_rows
            update_fields.append("gridProperties.rowCount")
        if current_columns < min_columns:
            properties["gridProperties"]["columnCount"] = min_columns
            update_fields.append("gridProperties.columnCount")

        if not update_fields:
            return

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": properties,
                            "fields": ",".join(update_fields),
                        }
                    }
                ]
            },
        ).execute()

    @staticmethod
    def _sheet_range(worksheet_name: str, cell_range: str) -> str:
        # Always quote sheet names to support spaces/special chars.
        escaped = worksheet_name.replace("'", "''")
        return f"'{escaped}'!{cell_range}"
