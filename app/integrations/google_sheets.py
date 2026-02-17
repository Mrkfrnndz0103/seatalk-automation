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

    def overwrite_values(self, spreadsheet_id: str, worksheet_name: str, values: list[list[str]]) -> None:
        service = self._build_service()
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=self._sheet_range(worksheet_name, "A:ZZ"),
            body={},
        ).execute()
        if not values:
            return

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=self._sheet_range(worksheet_name, "A1"),
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    @staticmethod
    def _sheet_range(worksheet_name: str, cell_range: str) -> str:
        # Always quote sheet names to support spaces/special chars.
        escaped = worksheet_name.replace("'", "''")
        return f"'{escaped}'!{cell_range}"
