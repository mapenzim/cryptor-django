#!/bin/sh
set -eu

cd "$(dirname "$0")"
.venv/bin/python manage.py migrate --noinput
exec .venv/bin/python manage.py runserver 127.0.0.1:8000
