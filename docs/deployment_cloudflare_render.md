# Deploy with Render + Cloudflare

## 1. Render service

1. Push this repo to GitHub.
2. Create a Render Web Service using `render.yaml`.
3. In Render service settings, set Python version to `3.12.9`.
4. Ensure these are present in the repo root:
   - `.python-version` with `3.12.9`
   - `render.yaml` with `PYTHON_VERSION=3.12.9`
5. Clear build cache in Render and redeploy.
6. Set required secrets in Render environment variables:
   - `SEATALK_APP_ID`
   - `SEATALK_APP_SECRET`
   - `SEATALK_SIGNING_SECRET`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `STUCKUP_SOURCE_SPREADSHEET_ID`
   - `STUCKUP_TARGET_SPREADSHEET_ID`
7. Upload your Google service account JSON and mount it at runtime, then set:
   - `GOOGLE_SERVICE_ACCOUNT_FILE` (example: `/etc/secrets/google-service-account.json`)

## 2. Cloudflare in front of Render

1. In Cloudflare DNS, create `CNAME`:
   - `bot.yourdomain.com` -> `your-render-service.onrender.com`
2. Enable proxy (orange cloud).
3. SSL/TLS mode: `Full`.
4. Optional WAF rule: allow `POST /callbacks/seatalk` and rate-limit unknown paths.

## 3. SeaTalk callback URL

Set callback URL in SeaTalk Open Platform to:

`https://bot.yourdomain.com/callbacks/seatalk`

## 4. Connectivity checks

- Render health:
  - `GET https://bot.yourdomain.com/health`
- SeaTalk event verification should return `seatalk_challenge` in under 5 seconds.

## 5. Google permissions

- Share source and target Google Sheets with service account email as Editor.
