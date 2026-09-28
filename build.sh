#!/usr/bin/env bash
#
# Render build step.
#
# Render also has a built-in Python build command, but an explicit
# script keeps the order visible and identical between local runs and
# the deployment. The order matters: dependencies first, then
# collectstatic, then migrate, because collectstatic needs the
# settings module (and therefore a working database configuration) and
# migrate must not run before the packages are present.
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
