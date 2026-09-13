param([ValidateSet('backend', 'frontend', 'click-receipts', 'admin-jobs')][string]$Service = 'backend')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:TASKORA_ENV = 'local'
$env:TASKORA_LOAD_DOTENV = 'false'
$env:REAL_MONEY_ENABLED = 'false'
if ($Service -eq 'frontend') {
    $env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8000/api'
    $env:API_URL = 'http://127.0.0.1:8000/api'
    Set-Location -LiteralPath (Join-Path $PSScriptRoot 'frontend')
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    pnpm dev
    exit $LASTEXITCODE
}
$taskoraPython = $null
foreach ($candidate in @('.venv-mvp/Scripts/python.exe', '.venv/Scripts/python.exe')) {
    if (Test-Path -LiteralPath $candidate) {
        & $candidate --version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $taskoraPython = $candidate; break }
    }
}
if (-not $taskoraPython) {
    py -3 -m venv .venv-mvp
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $taskoraPython = '.venv-mvp/Scripts/python.exe'
}
& $taskoraPython -m pip install -r requirements.txt
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
& $taskoraPython backend/manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $taskoraPython backend/manage.py seed_catalog --apply
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($Service -eq 'click-receipts') {
    & $taskoraPython backend/manage.py process_click_receipts --watch
    exit $LASTEXITCODE
}
if ($Service -eq 'admin-jobs') {
    & $taskoraPython backend/manage.py process_admin_jobs --watch
    exit $LASTEXITCODE
}
& $taskoraPython backend/manage.py runserver 127.0.0.1:8000
