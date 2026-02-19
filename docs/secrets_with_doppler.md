# Secrets With Doppler

This project includes a Doppler-based workflow so `.env` and secrets can be restored on any machine.

## 1) Install Doppler CLI

Windows (PowerShell):

```powershell
winget install doppler.doppler
```

## 2) Authenticate

Interactive login:

```powershell
doppler login
```

Or use a service token:

```powershell
$env:DOPPLER_TOKEN = "dp.st...."
```

## 3) Choose project/config

Set once per terminal/session:

```powershell
$env:DOPPLER_PROJECT = "data-automation"
$env:DOPPLER_CONFIG = "dev"
```

## 4) First-time upload from local `.env`

```powershell
.\scripts\secrets_push.ps1
```

Optional explicit values:

```powershell
.\scripts\secrets_push.ps1 -Project data-automation -Config dev -EnvFile .env
```

## 5) Pull `.env` on any new machine

```powershell
.\scripts\secrets_pull.ps1
```

Optional explicit values:

```powershell
.\scripts\secrets_pull.ps1 -Project data-automation -Config dev -OutFile .env
```

## 6) Run app without storing local `.env`

```powershell
.\scripts\run_with_doppler.ps1 -Reload
```

This injects secrets into the process at runtime using Doppler.

## Notes

- `.env` stays gitignored and is not committed.
- Keep production/staging/dev in separate Doppler configs.
- Rotate credentials in Doppler, then pull again with `secrets_pull.ps1`.

## Render Integration (Optional)

This repo includes `scripts/start_render.sh` and `render.yaml` support for Doppler on Render.

How it works:
- `startCommand` runs `bash scripts/start_render.sh`.
- If `USE_DOPPLER_ON_RENDER=false` (default), app starts normally with Render env vars.
- If `USE_DOPPLER_ON_RENDER=true`, script runs app via:
  - `doppler run --project <DOPPLER_PROJECT> --config <DOPPLER_CONFIG> -- uvicorn ...`

Set these in Render service environment:
- `USE_DOPPLER_ON_RENDER=true`
- `DOPPLER_TOKEN=<service_token>`
- `DOPPLER_PROJECT=<doppler_project>`
- `DOPPLER_CONFIG=<doppler_config>`

Recommended:
- Use a dedicated Doppler service token with least privilege.
- Keep separate configs (`dev`, `staging`, `prod`) and match them per Render environment.
