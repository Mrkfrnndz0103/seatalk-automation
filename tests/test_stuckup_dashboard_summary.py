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
