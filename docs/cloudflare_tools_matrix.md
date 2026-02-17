# Cloudflare Tools Matrix

This document lists Cloudflare tools for this project in two groups:
- Currently needed (for present architecture)
- Future optional (for enhancements)

Current architecture:
- SeaTalk webhook -> Cloudflare (optional edge) -> Render (FastAPI app)
- Data layer: Supabase + Google Sheets

## 1. Currently Needed

1. Cloudflare DNS
- Purpose: map custom domain (for example `bot.yourdomain.com`) to Render service hostname.
- Why needed: stable callback URL and domain control.

2. Cloudflare Proxy (orange cloud)
- Purpose: proxy traffic through Cloudflare edge.
- Why needed: TLS termination, origin masking, edge controls.

3. SSL/TLS Settings
- Purpose: secure HTTPS between users/SeaTalk and Cloudflare/origin.
- Recommended mode: `Full`.

4. WAF Custom Rules
- Purpose: allow expected webhook traffic and reduce malicious requests.
- Typical rule target: `POST /callbacks/seatalk`.

5. Rate Limiting Rules
- Purpose: protect callback endpoint from burst abuse and accidental floods.
- Typical rule target: `/callbacks/seatalk`.

## 2. Future Optional

1. Cloudflare Workers
- Use when you want edge logic: request validation, lightweight routing, enrichment, or fallback handling before Render.

2. Cloudflare Queues
- Use for async buffering/retry during bursts and downstream outages.

3. Cloudflare KV
- Use for low-latency edge key-value config/cache.

4. Cloudflare D1
- Use for lightweight edge relational state (if needed for specific features).

5. Cloudflare R2
- Use for object storage: raw snapshots, archives, exports.

6. Durable Objects
- Use for strict per-key coordination/stateful edge workflows.

7. Cron Triggers
- Use for scheduled tasks (maintenance, periodic checks, backfills).

8. Analytics and Logs
- Use for traffic visibility, incident triage, and security analysis.

9. Zero Trust / Access
- Use for protecting internal/admin endpoints.

10. Turnstile
- Use if a public web UI/form is introduced and bot abuse prevention is needed.

## 3. Recommendation for This Project

Minimum set to keep now:
- DNS
- Proxy
- SSL/TLS
- WAF rules
- Rate limiting

Keep Render as Python runtime host and Supabase as primary data store.
Add Workers/Queues/R2 only when concrete feature needs appear.
