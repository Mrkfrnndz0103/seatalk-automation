# Testing Guide

This project includes local automated tests under `tests/`.

## 1. Install test dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

## 2. Run all tests

```powershell
python -m pytest -q
```

## 3. Run specific test file

```powershell
python -m pytest -q tests/test_api_endpoints.py
python -m pytest -q tests/test_stuckup_handler.py
python -m pytest -q tests/test_signature.py
python -m pytest -q tests/test_google_sheets_range.py
```

## 4. What is covered

- `tests/test_api_endpoints.py`
  - `/health` and `/uptime-ping` responses
  - callback verification success with valid signature
  - callback verification failure with invalid signature
- `tests/test_stuckup_handler.py`
  - manual stuckup sync disabled behavior
  - help message output
- `tests/test_signature.py`
  - SeaTalk signature validation utility
- `tests/test_google_sheets_range.py`
  - Google Sheets range quoting/escaping for sheet names with spaces/symbols

## 5. Notes

- Tests are designed to run offline and do not call live SeaTalk/Google/Supabase APIs.
- `test_api_endpoints.py` forces `STUCKUP_AUTO_SYNC_ENABLED=false` for isolation.
- Live end-to-end validation (Render + SeaTalk + Google + Supabase) should still be done separately.
