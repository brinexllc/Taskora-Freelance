web: gunicorn --chdir backend config.wsgi:application --bind 0.0.0.0:$PORT
click_receipts: python backend/manage.py process_click_receipts --watch
