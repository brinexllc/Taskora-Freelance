# Taskora Freelance

Full-stack платформа фриланс-проектов: React/Vinext frontend, Django REST API и PostgreSQL. Frontend и backend разворачиваются как два отдельных Railway-сервиса из одного monorepo.

## Local Development

### Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python backend/manage.py migrate
python backend/manage.py runserver
```

Если `DATABASE_URL` в `.env` пустой, Django использует локальную SQLite. Для PostgreSQL укажите полный URL подключения только в локальном `.env` или Railway Variables.

### Frontend

```powershell
Set-Location frontend
Copy-Item .env.example .env.local
pnpm install --frozen-lockfile
pnpm dev
```

По умолчанию интерфейс доступен на `http://localhost:3000`, API — на `http://127.0.0.1:8000/api`.

## Backend Environment Variables

| Variable | Назначение | Локальный пример |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Секрет Django; обязателен при `DJANGO_DEBUG=false` | `change-me` |
| `DJANGO_DEBUG` | Режим отладки (`true`/`false`) | `true` |
| `DJANGO_ALLOWED_HOSTS` | Разрешённые host names через запятую | `localhost,127.0.0.1` |
| `DATABASE_URL` | PostgreSQL URL; при пустом значении используется SQLite | пусто |
| `DATABASE_SSL_REQUIRE` | Требовать TLS для PostgreSQL | `false` локально |
| `CORS_ALLOWED_ORIGINS` | Frontend origins через запятую | `http://localhost:3000` |
| `CSRF_TRUSTED_ORIGINS` | Доверенные origins через запятую | `http://localhost:3000` |
| `DJANGO_SECURE_SSL_REDIRECT` | HTTPS redirect; по умолчанию выключен для безопасности за Railway proxy | `false` |

## Frontend Environment Variables

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api
```

URL нормализуется централизованно в `frontend/lib/api.js`, поэтому завершающий `/` у base URL необязателен. В production переменная должна быть доступна во время frontend build.

## Railway Backend Deployment

- Root Directory: `/`
- Build Command: `pip install -r requirements.txt && python backend/manage.py collectstatic --noinput`
- Pre-deploy Command: `python backend/manage.py migrate --noinput`
- Start Command: `gunicorn --chdir backend config.wsgi:application --bind 0.0.0.0:$PORT`

Railway Variables:

```env
DJANGO_SECRET_KEY=<secure-random-secret>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=taskora-freelance-production.up.railway.app
DATABASE_URL=<Railway-PostgreSQL-connection-URL>
DATABASE_SSL_REQUIRE=true
CORS_ALLOWED_ORIGINS=https://FRONTEND-DOMAIN
CSRF_TRUSTED_ORIGINS=https://FRONTEND-DOMAIN
```

Не запускайте `migrate` внутри Gunicorn start command: миграции должны выполняться один раз на pre-deploy этапе.

## Railway Frontend Deployment

- Root Directory: `/frontend`
- Build Command: `pnpm install --frozen-lockfile && pnpm run build`
- Start Command: `pnpm start`

Railway Variable (должна быть доступна на build этапе):

```env
NEXT_PUBLIC_API_URL=https://taskora-freelance-production.up.railway.app/api
```

Vinext собирает standalone Node.js server в `dist/standalone`, а `pnpm start` запускает его на Railway `PORT` и адресе `0.0.0.0`.

## Production URLs

- Backend: https://taskora-freelance-production.up.railway.app
- API: https://taskora-freelance-production.up.railway.app/api
- Projects: https://taskora-freelance-production.up.railway.app/api/projects/
- Proposals: https://taskora-freelance-production.up.railway.app/api/proposals/
- Health: https://taskora-freelance-production.up.railway.app/api/health/
- Frontend: добавьте Railway domain после создания frontend-сервиса и внесите его в backend `CORS_ALLOWED_ORIGINS` и `CSRF_TRUSTED_ORIGINS`.

## Validation

```powershell
python backend/manage.py check
python backend/manage.py makemigrations --check
python backend/manage.py test marketplace
python backend/manage.py collectstatic --noinput

Set-Location frontend
pnpm lint
pnpm build
```

Файлы `.env` и `.env.*` исключены из Git; в репозитории хранятся только безопасные `.env.example`.
