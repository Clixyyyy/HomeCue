# Run from the root HomeCue_Integrated_Build directory in VS Code PowerShell.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\backend")
if (-not (Test-Path ".venv\Scripts\python.exe")) {
  py -3 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Write-Host "Website/API: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Swagger API: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
