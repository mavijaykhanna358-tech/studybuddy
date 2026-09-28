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
from django.core.checks import Error, Tags, Warning, register
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


def warnings():

    """
    Return the misconfigurations the settings already corrected for.
    """

    return getattr(
        settings,
        'DEPLOYMENT_WARNINGS',
        ()
    )


# =========================================================
# SYSTEM CHECK
# =========================================================

HINT = (
    'StudyBuddy is configured entirely from environment '
    'variables. See .env.example for the names and the '
    'Deployment section of README.md.'
)


@register(Tags.staticfiles)
def deployment_configuration(app_configs, **kwargs):

    """
    Report every recorded problem through one system check.

    An `Error` is a problem no code path can repair, such as a
    missing DATABASE_URL or a short SECRET_KEY, so the command stops
    with the reason attached rather than failing later with a
    downstream symptom.

    A `Warning` is misconfiguration the settings have already worked
    around, currently a stale EMAIL_BACKEND pointing at a backend
    that cannot deliver. Production ignores that value and uses
    Resend, so the deployment is already behaving correctly and the
    build should not be held hostage. The warning exists so the
    variable does not stay on the dashboard pretending to work.
    """

    reported = [
        Error(
            f'{identifier} {detail}',
            hint=HINT,
            id=f'studybuddy.{identifier.lower()}',
        )
        for identifier, detail in problems()
    ]

    reported += [
        Warning(
            f'{identifier} {detail}',
            hint=HINT,
            id=f'studybuddy.{identifier.lower()}_ignored',
        )
        for identifier, detail in warnings()
    ]

    return reported


# =========================================================
# WEB SERVER STARTUP
# =========================================================

def refuse_to_start():

    """
    Stop a WSGI/ASGI server from booting a broken deployment.

    Only unrepairable problems stop the server. A warning describes
    something the settings already worked around, so refusing on it
    would take down a deployment that is in fact running correctly.
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
