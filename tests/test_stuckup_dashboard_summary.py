from app.config import Settings
from app.workflows.stuckup.service import StuckupService


def _settings() -> Settings:
    return Settings(
        SEATALK_APP_ID="x",
        SEATALK_APP_SECRET="y",
    )


def test_build_dashboard_summary_from_block_returns_sentences_with_action_taken() -> None:
    service = StuckupService(_settings())
    values = [
        ["", "Region", "Ave L7D", "Total L7D", "18-Feb", "17-Feb"],
        ["", "RC", "2", "4", "0", "2"],
        ["", "InterSOC", "57", "226", "0", "100"],
        ["", "SOL-IIS", "89", "355", "0", "144", "", "", "", "", "", "", "", "", "*", "SOC BCP", "GenSan Tambler Hub", "", "", "30.95%"],
        ["", "MIN", "43", "216", "0", "83", "", "", "", "", "", "", "", "", "*", "No Cluster", "SOC 5", "", "", "27.48%"],
        ["", "Total", "199", "830", "0", "335"],
    ]

    lines = service._build_dashboard_summary_from_block(values)
    text = " ".join(lines)

    assert len(lines) >= 4
    assert "7-day total of 830" in text
    assert "SOL-IIS (355)" in text
    assert "SOC BCP" in text
    assert "Action Taken:" in text


def test_build_dashboard_summary_from_block_handles_shifted_dashboard_columns() -> None:
    service = StuckupService(_settings())
    # Mirrors live dashboard shape where key metrics start at index 2 ("Region").
    values = [
        [],
        ["", "", "Stuck at SOC_Staging"],
        [],
        ["", "", "Region", "Ave L7D", "Total L7D", "18-Feb", "17-Feb", "", "", "", "", "", "", "", "", "Top DC/HUBs affected:", "", "", "", "", "%"],
        ["", "", "RC", "3", "8", "0", "6", "", "", "", "", "", "", "", "", "*", "SOL-IIS", "San Agustin Hub", "", "", "9.75%"],
        ["", "", "InterSOC", "4", "13", "11", "1", "", "", "", "", "", "", "", "", "", "", "Tangkalan Hub", "", "", "3.87%"],
        ["", "", "Total", "109", "376", "137", "187", "", "", "", "", "", "", "", "", "", "", "SOC 5", "", "", "2.99%"],
    ]

    lines = service._build_dashboard_summary_from_block(values)
    text = " ".join(lines)

    assert "7-day total of 376" in text
    assert "average of 109" in text
    assert "RC (8)" in text
    assert "SOL-IIS" in text
    assert "Action Taken:" in text


class _FakeSheets:
    def __init__(self) -> None:
        self.ensure_calls: list[dict[str, object]] = []
        self.clear_calls: list[dict[str, object]] = []
        self.update_calls: list[dict[str, object]] = []

    def ensure_grid_size(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        min_rows: int,
        min_columns: int,
    ) -> None:
        self.ensure_calls.append(
            {
                "spreadsheet_id": spreadsheet_id,
                "worksheet_name": worksheet_name,
                "min_rows": min_rows,
                "min_columns": min_columns,
            }
        )

    def clear_range(self, spreadsheet_id: str, worksheet_name: str, cell_range: str) -> None:
        self.clear_calls.append(
            {
                "spreadsheet_id": spreadsheet_id,
                "worksheet_name": worksheet_name,
                "cell_range": cell_range,
            }
        )

    def update_values(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        start_cell: str,
        values: list[list[str]],
    ) -> dict[str, int]:
        self.update_calls.append(
            {
                "spreadsheet_id": spreadsheet_id,
                "worksheet_name": worksheet_name,
                "start_cell": start_cell,
                "values": values,
            }
        )
        return {"updatedRows": len(values)}


def test_refresh_dashboard_summary_writes_to_merged_summary_block_top_left() -> None:
    service = StuckupService(_settings())
    fake_sheets = _FakeSheets()
    service._google_sheets = fake_sheets  # type: ignore[assignment]
    service._read_dashboard_block_stable = lambda: []  # type: ignore[assignment]

    service.refresh_dashboard_summary_only()

    assert fake_sheets.clear_calls
    assert fake_sheets.update_calls
    assert fake_sheets.clear_calls[-1]["cell_range"] == "C4:AA9"
    assert fake_sheets.update_calls[-1]["start_cell"] == "C4"
