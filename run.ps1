$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker is not installed or is not available on PATH. Install Docker Desktop or Docker Engine, then run this again."
}

if (-not (Test-Path -LiteralPath ".env")) {
  Copy-Item -LiteralPath ".env.example" -Destination ".env"
  Write-Host "Created .env from .env.example. Change POSTGRES_PASSWORD before event day."
}

$HostPort = "7080"
Get-Content -LiteralPath ".env" | ForEach-Object {
  if ($_ -match "^\s*HOST_PORT\s*=\s*(.+?)\s*$") {
    $script:HostPort = $Matches[1].Trim()
  }
}

Write-Host "Building and starting Kairix on port $HostPort..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

$HealthUrl = "http://localhost:$HostPort/api/health"
$Ready = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    $Response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
    if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 300) {
      $Ready = $true
      break
    }
  } catch {
    Start-Sleep -Seconds 1
  }
}

if ($Ready) {
  Write-Host "Kairix is running."
} else {
  Write-Host "Kairix is still starting. Check logs with: docker compose logs -f web"
}

Write-Host "Home:        http://localhost:$HostPort/"
Write-Host "Admin:       http://localhost:$HostPort/admin"
Write-Host "Judge:       http://localhost:$HostPort/judge"
Write-Host "Public:      http://localhost:$HostPort/public"
Write-Host "Queue:       http://localhost:$HostPort/queue"
Write-Host "OBS overlay: http://localhost:$HostPort/obs-overlay"
