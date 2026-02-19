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
        self.delete_calls: list[tuple[str, list[str]]] = []

    def select(self, columns: str) -> _FakeQuery:
        self.select_calls.append(columns)
        return _FakeQuery(self._pages)

    def delete(self) -> "_FakeDeleteQuery":
        return _FakeDeleteQuery(self)


class _FakeDeleteQuery:
    def __init__(self, table: _FakeTable) -> None:
        self._table = table
        self._column = ""
        self._values: list[str] = []

    def in_(self, column: str, values: list[str]) -> "_FakeDeleteQuery":
        self._column = column
        self._values = values
        return self

    def execute(self):
        self._table.delete_calls.append((self._column, list(self._values)))

        class _Result:
            data: list[dict[str, object]] = []

        return _Result()


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


def test_delete_rows_by_values_batches_requests() -> None:
    sink = SupabaseSink(_settings())
    fake_client = _FakeClient([])
    sink._client = fake_client  # type: ignore[assignment]

    values = [f"id_{i}" for i in range(1205)]
    result = sink.delete_rows_by_values("shipment_id", values, batch_size=500)

    assert result.status == "ok"
    assert len(fake_client._table_impl.delete_calls) == 3
    assert fake_client._table_impl.delete_calls[0][0] == "shipment_id"
    assert len(fake_client._table_impl.delete_calls[0][1]) == 500
    assert len(fake_client._table_impl.delete_calls[1][1]) == 500
    assert len(fake_client._table_impl.delete_calls[2][1]) == 205


def test_delete_rows_by_values_noop_on_empty_values() -> None:
    sink = SupabaseSink(_settings())
    fake_client = _FakeClient([])
    sink._client = fake_client  # type: ignore[assignment]

    result = sink.delete_rows_by_values("shipment_id", [])

    assert result.status == "ok"
    assert result.message == "no rows to delete"
    assert fake_client._table_impl.delete_calls == []
