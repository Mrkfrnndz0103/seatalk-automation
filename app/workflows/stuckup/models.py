from dataclasses import dataclass


@dataclass
class StuckupSyncResult:
    status: str
    message: str
    source_rows: int
    upserted_rows: int
    exported_rows: int
    exported_columns: int
