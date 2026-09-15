# Convenience script to run the Titans CRM locally for development.
# Usage: .\scripts\run_dev.ps1

$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

& "$ProjectDir\venv\Scripts\python.exe" manage.py runserver 0.0.0.0:8000
