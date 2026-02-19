param(
  [string]$DatabaseUrl = 'postgresql+psycopg://postgres:postgres@localhost:5432/valore365',
  [int]$Port = 8000
)

$env:DATABASE_URL = $DatabaseUrl

Push-Location src/backend
try {
  if (-not (Test-Path .venv)) {
    python -m venv .venv
  }

  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  uvicorn app.main:app --reload --port $Port
}
finally {
  Pop-Location
}
