"""
WSGI config for project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')

# Gunicorn runs no system checks, so a deployment with a missing
# DATABASE_URL or SECRET_KEY would otherwise boot and only fail on the
# first request that touched the database. Refuse here, with the reason
# in the server log.

from project.deployment import refuse_to_start  # noqa: E402

refuse_to_start()

application = get_wsgi_application()
