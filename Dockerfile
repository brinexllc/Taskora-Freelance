FROM python:3.14.7-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
RUN DJANGO_DEBUG=true DATABASE_URL=sqlite:////tmp/build.sqlite3 python backend/manage.py collectstatic --noinput
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn --chdir backend config.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
