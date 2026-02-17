# SeaTalk Workflow Automation Server

Python FastAPI server for SeaTalk bot callback automation with workflow folders:
- `stuckup` (implemented)
- `backlogs` (scaffolded)
- `shortlanded` (scaffolded)
- `lh_request` (scaffolded)

## 1. Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Use Python 3.12.

Fill `.env` with SeaTalk, Google, and Supabase credentials.

## 2. Run

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 3. Callback URL

Configure in SeaTalk Open Platform:
- Callback URL: `https://<your-domain>/callbacks/seatalk`

## 4. Workflow Commands

### Stuckup

```text
/stuckup sync
```

Pipeline:
1. Read source sheet range `STUCKUP_SOURCE_RANGE` (default `A1:AL`, 38 cols).
2. Upsert all source columns into Supabase (`SUPABASE_STUCKUP_TABLE`).
3. Read back data from Supabase.
4. Export selected columns to target sheet based on `STUCKUP_EXPORT_RANGES`.

Default export ranges:
- `B1:E`
- `I1:J`
- `M`
- `Q1:U`
- `Y1:AA`
- `AH1:AK`

### Others (scaffolded)

- `/backlogs`
- `/shortlanded`
- `/lh_request`

## 5. Deploy

- Render config: `render.yaml` (native Python runtime)
- Python runtime pin: `.python-version` + `PYTHON_VERSION=3.12.9`
- Cloudflare + Render guide: `docs/deployment_cloudflare_render.md`
