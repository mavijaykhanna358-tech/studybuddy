"""
Deployment configuration checks.

`project/settings.py` must always import. Django's
`ManagementUtility.execute` swallows an `ImproperlyConfigured` raised
while importing the settings, and `get_commands` then returns only the
core command list because `settings.configured` is False.
`collectstatic` is contributed by `django.contrib.staticfiles`, which
is only reached through the app registry, so the build stops with

    Unknown command: 'collectstatic'

and the actual reason never reaches the log. An earlier version of
this project raised from the settings module, and that is exactly the
failure it produced.

So the settings record their problems in `DEPLOYMENT_ERRORS` rather
than raising, and this module reports them through the two channels
that can actually show them:

* A system check, which every management command runs before it does
  any work. The check carries `Tags.staticfiles` because
  `collectstatic` runs only checks with that tag, whereas `migrate`,
  `runserver` and `check` run all of them.
* A hard failure from `project/wsgi.py` and `project/asgi.py`. Gunicorn
  imports those and never runs system checks, so without this a broken
  deployment would boot and only fail on the first request.
"""

import sys

from django.conf import settings
from django.core.checks import Error, Tags, register
from django.core.exceptions import ImproperlyConfigured


# =========================================================
# RECORDED PROBLEMS
# =========================================================

def problems():

    """
    Return the configuration problems recorded by the settings.
    """

    return getattr(
        settings,
        'DEPLOYMENT_ERRORS',
        ()
    )


# =========================================================
# SYSTEM CHECK
# =========================================================

@register(Tags.staticfiles)
def deployment_configuration(app_configs, **kwargs):

    """
    Turn every recorded problem into a check error.

    A check error stops the command with the reason attached, so
    `collectstatic` and `migrate` fail with the actual cause instead
    of a downstream symptom.
    """

    return [
        Error(
            f'{identifier} {detail}',
            hint=(
                'StudyBuddy is configured entirely from environment '
                'variables. See .env.example for the names and the '
                'Deployment section of README.md.'
            ),
            id=f'studybuddy.{identifier.lower()}',
        )
        for identifier, detail in problems()
    ]


# =========================================================
# WEB SERVER STARTUP
# =========================================================

def refuse_to_start():

    """
    Stop a WSGI/ASGI server from booting a broken deployment.
    """

    found = problems()

    if not found:
        return

    border = '=' * 57

    lines = [
        '',
        border,
        ' StudyBuddy cannot start: configuration problems',
        border,
    ]

    for identifier, detail in found:
        lines.append(f'{identifier} {detail}')

    lines += [
        border,
        '',
    ]

    sys.stderr.write(
        '\n'.join(lines)
    )

    sys.stderr.flush()

    raise ImproperlyConfigured(
        'StudyBuddy is not configured correctly: '
        + ', '.join(
            identifier for identifier, _ in found
        )
    )
