import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_STUCKUP_EXPORT_RANGES = "B1:E,I1:J,M,Q1:U,Y1:AA,AH1:AK"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    seatalk_app_id: str = Field(alias="SEATALK_APP_ID")
    seatalk_app_secret: str = Field(alias="SEATALK_APP_SECRET")
    seatalk_signing_secret: str = Field(default="", alias="SEATALK_SIGNING_SECRET")
    seatalk_verify_signature: bool = Field(default=True, alias="SEATALK_VERIFY_SIGNATURE")
    seatalk_api_base_url: str = Field(default="https://openapi.seatalk.io", alias="SEATALK_API_BASE_URL")

    google_service_account_file: str = Field(default="", alias="GOOGLE_SERVICE_ACCOUNT_FILE")
    stuckup_source_spreadsheet_id: str = Field(default="", alias="STUCKUP_SOURCE_SPREADSHEET_ID")
    stuckup_source_worksheet_name: str = Field(default="Source", alias="STUCKUP_SOURCE_WORKSHEET_NAME")
    stuckup_source_range: str = Field(default="A1:AL", alias="STUCKUP_SOURCE_RANGE")

    stuckup_target_spreadsheet_id: str = Field(default="", alias="STUCKUP_TARGET_SPREADSHEET_ID")
    stuckup_target_worksheet_name: str = Field(default="Stuckup", alias="STUCKUP_TARGET_WORKSHEET_NAME")
    stuckup_export_ranges: str = Field(default=DEFAULT_STUCKUP_EXPORT_RANGES, alias="STUCKUP_EXPORT_RANGES")

    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_stuckup_table: str = Field(default="stuckup_shipments", alias="SUPABASE_STUCKUP_TABLE")
    supabase_stuckup_conflict_column: str = Field(default="shipment_id", alias="SUPABASE_STUCKUP_CONFLICT_COLUMN")

    stuckup_raw_backup_path: Path = Field(default=Path("data/stuckup/raw_full.jsonl"), alias="STUCKUP_RAW_BACKUP_PATH")
    stuckup_auto_sync_enabled: bool = Field(default=True, alias="STUCKUP_AUTO_SYNC_ENABLED")
    stuckup_poll_interval_seconds: int = Field(default=60, alias="STUCKUP_POLL_INTERVAL_SECONDS")
    stuckup_reference_row: int = Field(default=2, alias="STUCKUP_REFERENCE_ROW")
    stuckup_state_path: Path = Field(default=Path("data/stuckup/reference_row_state.txt"), alias="STUCKUP_STATE_PATH")

    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    configure_logging(settings.log_level)
    return settings
