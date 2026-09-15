web: python manage.py seed_data && gunicorn titans_crm.wsgi:application --bind 0.0.0.0:$PORT --workers 3
release: python manage.py migrate --noinput
