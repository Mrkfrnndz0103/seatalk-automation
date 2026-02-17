# Cloudflare Implementation Guide (SeaTalk Bot + Render)

Use Cloudflare as the edge layer in front of your Render-hosted SeaTalk bot server.

## 1. Purpose of Cloudflare

Cloudflare is used for:
- Custom domain (for example, `bot.yourdomain.com`)
- HTTPS and SSL/TLS management
- Security controls (WAF and rate limiting)
- Stable callback URL even if backend hosting changes later

Cloudflare does not run this Python app. Render runs `FastAPI`.

## 2. Prerequisites

1. Render service is deployed and healthy:
   - `https://<your-render-service>.onrender.com/health`
2. Domain is added to Cloudflare and status is `Active`.
3. SeaTalk callback endpoint in this app is:
   - `/callbacks/seatalk`

## 3. Cloudflare DNS Setup

1. Open Cloudflare Dashboard -> `DNS`.
2. Click `Add record`.
3. Create record:
   - Type: `CNAME`
   - Name: `bot`
   - Target: `<your-render-service>.onrender.com`
   - Proxy status: `Proxied` (orange cloud)
4. Save record.

Your callback base URL becomes:
- `https://bot.yourdomain.com`

## 4. SSL/TLS Setup

1. Go to `SSL/TLS` -> `Overview`.
2. Set mode to `Full`.
3. Go to `SSL/TLS` -> `Edge Certificates`.
4. Enable `Always Use HTTPS`.

## 5. Security Rules (Free Tier)

1. Go to `Security` -> `WAF` -> `Custom rules`.
2. Create an allow rule for SeaTalk callback:
   - URI path equals `/callbacks/seatalk`
   - HTTP method equals `POST`
3. Create a rate-limiting rule for `/callbacks/seatalk` to protect abuse.
4. Optionally challenge/block unexpected methods for callback path.

## 6. Render Compatibility Checklist

1. Render runtime must be Python `3.12.9`.
2. Keep these runtime pin files in repo root:
   - `runtime.txt`
   - `.python-version`
3. Keep `PYTHON_VERSION=3.12.9` in `render.yaml`.
4. If Render still uses Python 3.14:
   - Set Python version in dashboard to `3.12.9`
   - Clear build cache
   - Redeploy

## 7. SeaTalk Callback Configuration

In SeaTalk Open Platform, set callback URL to:
- `https://bot.yourdomain.com/callbacks/seatalk`

After saving, SeaTalk sends verification event. Your app must respond quickly.

## 8. Validation Steps

1. Open:
   - `https://bot.yourdomain.com/health`
2. Confirm HTTP 200 response.
3. Confirm SeaTalk callback verification passes.
4. Trigger a source-sheet row 2 change, then check Render logs for:
   - `stuckup reference row changed, triggering sync`
   - `stuckup auto-sync result: status=ok ...`

## 8.1 Supabase state table (required for stable auto-trigger)

Create a state table so row fingerprint persists across Render restarts:

```sql
create table if not exists stuckup_sync_state (
  key text primary key,
  value text not null
);
```

Expected env:
- `SUPABASE_STUCKUP_STATE_TABLE=stuckup_sync_state`
- `SUPABASE_STUCKUP_STATE_KEY=reference_row_fingerprint`

## 9. Free-Tier Notes

1. Cloudflare Free is sufficient for DNS/proxy/basic WAF setup.
2. Render Free may sleep on inactivity.
3. Cold starts can delay SeaTalk callbacks.
4. Mitigation: periodic uptime ping using UptimeRobot.

UptimeRobot sample config:
- Monitor Type: `HTTP(s)`
- URL: `https://<your-render-service>.onrender.com/uptime-ping`
- Monitoring interval: `5 minutes`
- Timeout: `30 seconds`
- Expected status: `200`

## 10. Quick Troubleshooting

1. SeaTalk verification failed:
   - Confirm callback URL path is exactly `/callbacks/seatalk`
   - Confirm `SEATALK_SIGNING_SECRET` matches SeaTalk app setting
2. 5xx from callback:
   - Check Render logs
   - Confirm env vars are set
3. Python build fails with `pydantic-core`/`maturin`:
   - Ensure Python `3.12.9`
   - Clear build cache and redeploy
