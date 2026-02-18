from __future__ import annotations

from app.config import Settings
from app.integrations.supabase_sink import SupabaseSink


class _FakeQuery:
    def __init__(self, pages: list[list[dict[str, object]]]) -> None:
        self._pages = pages
        self._start = 0
        self._end = 0
        self._ordered_by: str | None = None

    def range(self, start: int, end: int) -> "_FakeQuery":
        self._start = start
        self._end = end
        return self

    def order(self, column: str) -> "_FakeQuery":
        self._ordered_by = column
        return self

    def execute(self):
        page_size = self._end - self._start + 1
        page_index = self._start // page_size
        data = self._pages[page_index] if page_index < len(self._pages) else []

        class _Result:
            def __init__(self, rows):
                self.data = rows

        return _Result(data)


class _FakeTable:
    def __init__(self, pages: list[list[dict[str, object]]]) -> None:
        self._pages = pages
        self.select_calls: list[str] = []

    def select(self, columns: str) -> _FakeQuery:
        self.select_calls.append(columns)
        return _FakeQuery(self._pages)


class _FakeClient:
    def __init__(self, pages: list[list[dict[str, object]]]) -> None:
        self._table_impl = _FakeTable(pages)

    def table(self, _: str) -> _FakeTable:
        return self._table_impl


def _settings() -> Settings:
    return Settings(
        SEATALK_APP_ID="x",
        SEATALK_APP_SECRET="y",
        SUPABASE_URL="https://example.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="key",
    )


def test_fetch_all_rows_paginates_beyond_default_limit() -> None:
    first_page = [{"shipment_id": str(i)} for i in range(1000)]
    second_page = [{"shipment_id": str(i)} for i in range(1000, 1200)]
    sink = SupabaseSink(_settings())
    sink._client = _FakeClient([first_page, second_page])  # type: ignore[assignment]

    result, rows = sink.fetch_all_rows(order_by="shipment_id")

    assert result.status == "ok"
    assert len(rows) == 1200
    assert rows[0]["shipment_id"] == "0"
    assert rows[-1]["shipment_id"] == "1199"
