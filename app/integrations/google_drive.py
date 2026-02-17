import json
import logging
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import Settings
from app.integrations.types import SinkResult

logger = logging.getLogger(__name__)


class GoogleDriveSink:
    def __init__(self, settings: Settings) -> None:
        self._enabled = bool(settings.google_drive_folder_id and settings.google_service_account_file)
        self._folder_id = settings.google_drive_folder_id
        self._credentials_file = Path(settings.google_service_account_file) if settings.google_service_account_file else None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def upload_submission(self, record: dict[str, Any]) -> SinkResult:
        if not self.enabled:
            return SinkResult("google_drive", "skipped", "not configured")

        if not self._credentials_file or not self._credentials_file.exists():
            return SinkResult("google_drive", "error", "service account file not found")

        temp_path = Path("data/stuckup") / f"{record['submission_id']}.json"
        temp_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            temp_path.write_text(json.dumps(record, ensure_ascii=True), encoding="utf-8")
            credentials = service_account.Credentials.from_service_account_file(
                str(self._credentials_file),
                scopes=["https://www.googleapis.com/auth/drive.file"],
            )
            service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            metadata = {
                "name": temp_path.name,
                "parents": [self._folder_id],
                "mimeType": "application/json",
            }
            media = MediaFileUpload(str(temp_path), mimetype="application/json", resumable=False)
            service.files().create(body=metadata, media_body=media, fields="id").execute()
            return SinkResult("google_drive", "ok", "file uploaded")
        except Exception as exc:
            logger.exception("failed to upload submission to google drive")
            return SinkResult("google_drive", "error", str(exc))