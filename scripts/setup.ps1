Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Installing Node dependencies..."
npm install

if (!(Test-Path ".venv")) {
  Write-Host "Creating Python virtual environment..."
  python -m venv .venv
}

Write-Host "Installing backend dependencies..."
.\.venv\Scripts\pip install -r apps\backend\requirements.lock

if (!(Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example"
}

Write-Host "Setup complete."
