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

    @staticmethod
    def _scopes() -> list[str]:
        return ["https://www.googleapis.com/auth/spreadsheets"]

    def _load_credentials(self):
        if not self._credentials_file or not self._credentials_file.exists():
            raise FileNotFoundError("google service account file not found")
        return service_account.Credentials.from_service_account_file(
            str(self._credentials_file),
            scopes=self._scopes(),
        )

    def _build_service(self):
        credentials = self._load_credentials()
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def read_values(self, spreadsheet_id: str, worksheet_name: str, cell_range: str) -> list[list[str]]:
        service = self._build_service()
        response = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=self._sheet_range(worksheet_name, cell_range),
        ).execute()
        values: list[list[Any]] = response.get("values", [])
        return [[str(cell).strip() for cell in row] for row in values]

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
