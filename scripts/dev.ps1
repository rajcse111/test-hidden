Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\.venv\Scripts\uvicorn app.main:app --reload --app-dir apps/backend --host 0.0.0.0 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "npm run dev --workspace @interview/desktop"

