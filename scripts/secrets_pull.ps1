param(
    [string]$Project = $env:DOPPLER_PROJECT,
    [string]$Config = $env:DOPPLER_CONFIG,
    [string]$OutFile = ".env"
)

function Resolve-Doppler {
    $cmd = Get-Command doppler -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetRoot) {
        $candidate = Get-ChildItem -Path $wingetRoot -Directory -Filter "Doppler.doppler_*" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($candidate) {
            $exe = Join-Path $candidate.FullName "doppler.exe"
            if (Test-Path $exe) {
                return $exe
            }
        }
    }
    return $null
}

$doppler = Resolve-Doppler
if (-not $doppler) {
    Write-Error "Doppler CLI is not installed. Install it first (Windows: winget install doppler.doppler)."
    exit 1
}

if (-not $Project -or -not $Config) {
    Write-Error "Missing Doppler project/config. Set DOPPLER_PROJECT and DOPPLER_CONFIG, or pass -Project and -Config."
    exit 1
}

Write-Host "Downloading secrets from Doppler project='$Project' config='$Config' to '$OutFile'..."
& $doppler secrets download --no-file --format env --project $Project --config $Config | Out-File -FilePath $OutFile -Encoding utf8

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to download secrets from Doppler."
    exit $LASTEXITCODE
}

Write-Host "Done."
