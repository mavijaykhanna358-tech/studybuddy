#!/usr/bin/env bash
#
# Render build step.
#
# Render also has a built-in Python build command, but an explicit
# script keeps the order visible and identical between local runs and
# the deployment. The order matters: dependencies first, then
# collectstatic, then migrate. collectstatic only needs the settings
# module, never a database connection, and migrate must not run before
# the packages are present.
#
# collectstatic and migrate both run Django's system checks first, so
# an unset DATABASE_URL or SECRET_KEY stops the build here with the
# reason named, rather than surfacing later as a connection error.
#
# Every step is idempotent, so a redeploy is safe.

set -euo pipefail

echo "---- Installing dependencies ----"
pip install --upgrade pip
pip install -r requirements.txt

echo "---- Collecting static files ----"
# --no-input stops Django asking for the admin's missing-secret-key
# prompt, which would hang a non-interactive build.
python manage.py collectstatic --no-input

echo "---- Applying migrations ----"
python manage.py migrate --noinput

echo "---- Build complete ----"
