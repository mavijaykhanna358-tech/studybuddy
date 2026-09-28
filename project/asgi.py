"""
ASGI config for project project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')

# Same reason as project/wsgi.py: an ASGI server runs no system checks,
# so refuse a broken deployment at startup instead of at the first
# request.

from project.deployment import refuse_to_start  # noqa: E402

refuse_to_start()

application = get_asgi_application()
