param([ValidateSet('backend', 'frontend')][string]$Service = 'backend')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($Service -eq 'frontend') {
    $env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8000/api'
    Set-Location -LiteralPath (Join-Path $PSScriptRoot 'frontend')
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    pnpm dev
    exit $LASTEXITCODE
}
if (-not (Test-Path -LiteralPath '.venv-mvp/Scripts/python.exe')) {
    py -3.14 -m venv .venv-mvp
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& .venv-mvp/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$databasePath = (Join-Path $PSScriptRoot 'backend/local-mvp.sqlite3').Replace('\', '/')
$env:DATABASE_URL = "sqlite:///$databasePath"
$env:DJANGO_DEBUG = 'true'
$env:DJANGO_SECRET_KEY = 'django-insecure-taskora-local-only'
$env:DJANGO_ALLOWED_HOSTS = 'localhost,127.0.0.1'
$env:CORS_ALLOWED_ORIGINS = 'http://localhost:3000,http://127.0.0.1:3000'
$env:CORS_ALLOW_ALL_ORIGINS = 'false'
$env:EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
$env:FRONTEND_URL = 'http://localhost:3000'
& .venv-mvp/Scripts/python.exe backend/manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .venv-mvp/Scripts/python.exe backend/manage.py runserver 127.0.0.1:8000
