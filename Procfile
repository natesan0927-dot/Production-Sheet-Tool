release: python manage.py migrate --noinput && python manage.py seed_employees
web: gunicorn titans_crm.wsgi:application --bind 0.0.0.0:$PORT --workers 3
