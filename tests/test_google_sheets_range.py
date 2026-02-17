from app.integrations.google_sheets import GoogleSheetsClient


def test_sheet_range_quotes_sheet_name() -> None:
    got = GoogleSheetsClient._sheet_range("My Sheet - SOC 5", "A1:Z1")
    assert got == "'My Sheet - SOC 5'!A1:Z1"


def test_sheet_range_escapes_single_quote() -> None:
    got = GoogleSheetsClient._sheet_range("Team's Data", "A2:ZZ2")
    assert got == "'Team''s Data'!A2:ZZ2"
