Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Installing Node dependencies..."
npm install

if (!(Test-Path ".venv")) {
  Write-Host "Creating Python virtual environment..."
  python -m venv .venv
}

Write-Host "Installing backend dependencies..."
if (Test-Path "apps\backend\requirements.lock") {
  .\.venv\Scripts\pip install -r apps\backend\requirements.lock
} else {
  .\.venv\Scripts\pip install -r apps\backend\requirements.txt
}

if (!(Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example"
}

Write-Host "Setup complete."
