#!/usr/bin/env bash
#
# Render runs this on every deploy, before starting the web process.
#
# Migrations live here rather than in a pre-deploy command because Render's
# free plan does not offer one. Every step is safe to repeat: migrate does
# nothing when the database is current, remove_demo_data does nothing once the
# demo logins are gone, and seed_employees leaves an existing account —
# including its changed password — alone.

set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py remove_demo_data
python manage.py seed_employees
