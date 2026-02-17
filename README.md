# SeaTalk Workflow Automation Server

Python FastAPI server for SeaTalk bot callback automation with workflow folders:
- `stuckup` (implemented, auto-triggered)
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

Monitoring endpoint:
- `GET /stuckup/status` (returns current monitor state + last sync result)

## 3. Callback URL

Configure in SeaTalk Open Platform:
- Callback URL: `https://<your-domain>/callbacks/seatalk`

## 4. Stuckup Workflow (Auto)

Trigger behavior:
1. Bot monitors source sheet reference row (`STUCKUP_REFERENCE_ROW`, default `2`).
2. If row value changes, bot runs sync automatically:
   - Source sheet A:AL (38 columns) -> Supabase upsert
   - Supabase -> target sheet export columns (`STUCKUP_EXPORT_COLUMNS`)

Source row filter:
- Only rows where `status_desc` is one of `STUCKUP_FILTER_STATUS_VALUES` are imported.
- Default values:
  - `SOC_Packed`
  - `SOC_Packing`
  - `SOC_Staging`
  - `SOC_LHTransported`
  - `SOC_LHTransporting`

Default destination columns retained:
- `journey_type`
- `spx_station_site`
- `shipment_id`
- `status_group`
- `status_desc`
- `status_timestamp`
- `ageing_bucket`
- `hub_dest_station_name`
- `hub_region`
- `cluster_name`
- `fms_last_update_time`
- `last_run_time`
- `last_operator`
- `day`
- `Ageing bucket_`
- `operator`

Key settings:
- `STUCKUP_AUTO_SYNC_ENABLED=true`
- `STUCKUP_POLL_INTERVAL_SECONDS=60`
- `STUCKUP_REFERENCE_ROW=2`
- `STUCKUP_FILTER_STATUS_VALUES=SOC_Packed,SOC_Packing,SOC_Staging,SOC_LHTransported,SOC_LHTransporting`
- `STUCKUP_EXPORT_COLUMNS=journey_type,spx_station_site,shipment_id,status_group,status_desc,status_timestamp,ageing_bucket,hub_dest_station_name,hub_region,cluster_name,fms_last_update_time,last_run_time,last_operator,day,Ageing bucket_,operator`
- `SUPABASE_STUCKUP_STATE_TABLE=stuckup_sync_state`
- `SUPABASE_STUCKUP_STATE_KEY=reference_row_fingerprint`
- `STUCKUP_STATE_PATH=data/stuckup/reference_row_state.txt` (fallback only)

State persistence:
- Fingerprint is stored in Supabase so restarts do not cause unexpected syncs.
- Local state file is used only as fallback if Supabase state read/write fails.

Notes:
- Manual `/stuckup sync` is disabled.
- `/stuckup help` shows auto-sync info.

## 5. Other Workflows (Scaffolded)

- `/backlogs`
- `/shortlanded`
- `/lh_request`

## 6. UptimeRobot (Render Free Tier)

To reduce cold starts on Render free tier, create an UptimeRobot monitor:

1. Monitor Type: `HTTP(s)`
2. URL: `https://<your-render-service>.onrender.com/uptime-ping`
3. Monitoring interval: `5 minutes`
4. Timeout: `30 seconds`
5. Alert contacts: optional

Expected response: HTTP `200` with body `{"status":"alive"}`.

## 7. Deploy

- Render config: `render.yaml` (native Python runtime)
- Python runtime pin: `.python-version` + `PYTHON_VERSION=3.12.9`
- Cloudflare + Render guide: `docs/deployment_cloudflare_render.md`
- Test execution guide: `docs/testing_guide.md`
