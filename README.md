# StudyBuddy

A student planner built with Django. Subjects, tasks and notes live
in one place, with a dashboard that surfaces what needs attention
today.

## Features

- **Dashboard** — task counts, completion percentage, overdue and
  due-soon counts, the next five tasks and the five most recent
  notes.
- **Subjects** — one workspace per user. Subject names are unique
  per account, and deleting a subject warns how many tasks and
  notes are affected (tasks are removed, notes are kept).
- **Tasks** — priority, status, due date and optional subject, with
  search, filters, sorting, pagination, and a one-click complete /
  reopen control.
- **Notes** — title, body, optional subject and a file attachment
  (images, PDF, Word, Excel, PowerPoint, text; up to 25 MB) with an
  in-page viewer.
- **Accounts** — register, log in, profile page and a working
  password reset flow.

Every list is scoped to the signed-in user, and every detail, edit
and delete view returns 404 for somebody else's object.

## Requirements

- Python 3.12 or newer
- SQLite (bundled) or a managed PostgreSQL / MySQL

## Setup

```bash
git clone <your-repo-url>
cd project

python -m venv .venv
```

Activate it:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

Install dependencies and prepare the database:

```bash
pip install -r requirements.txt

python manage.py migrate
```

No `.env` is needed for local development. Create a superuser if
you want the admin site:

```bash
python manage.py createsuperuser
```

Run it:

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

## Configuration

Every setting has a working default, so `.env` is optional
locally. Copy `.env.example` to `.env` to change anything. Real
environment variables (shell, CI, hosting) take priority over the
file.

| Variable | Default | Notes |
| --- | --- | --- |
| `DJANGO_ENV` | `development` | `production` turns `DEBUG` off by default. |
| `DEBUG` | follows `DJANGO_ENV` | Set explicitly to override. |
| `SECRET_KEY` | insecure dev key | **Required** when `DEBUG` is off; at least 50 characters. |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost,...` | Comma separated. |
| `CSRF_TRUSTED_ORIGINS` | the deployed domains | Needed for HTTPS domains. |
| `DATABASE_URL` | unset (SQLite) in development, required in production | Any `dj-database-url` URL. |
| `DATABASE_SSL_REQUIRE` | `False` | Set `True` only for a managed database that demands encryption. A `?sslmode=require` in `DATABASE_URL` is always honoured either way. |
| `RESEND_API_KEY` | unset | Without it, email prints to the console. |
| `DEFAULT_FROM_EMAIL` | `onboarding@resend.dev` | Sender address. |
| `FRONTEND_BASE_URL` | `http://localhost:8000` | Public address; password reset links are built from it. |
| `CLOUDINARY_*` | unset | Leave empty to store attachments on local disk. |

Generate a secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

When `DEBUG` is off, Django refuses to start with a short or
default `SECRET_KEY`, and switches on HTTPS-only cookies, HSTS
and `X-Frame-Options: DENY`.

## Email

With `RESEND_API_KEY` set, mail goes out through the Resend HTTP
API (`users/email_backend.py`). Without it, Django's console
backend prints messages instead of dropping them. Set
`FRONTEND_BASE_URL` to the real https address so reset links work
off-site.

## Task reminders

A management command emails a reminder for tasks due tomorrow and
for anything overdue:

```bash
python manage.py send_task_reminders
```

Preview without sending anything:

```bash
python manage.py send_task_reminders --dry-run
```

A task is only reminded once. Editing its due date or reopening it
clears the flag so it can be reminded again, and a task whose mail
fails is retried on the next run instead of being marked as sent.

`.github/workflows/send_reminders.yml` runs this daily at 03:30
UTC and on demand from the Actions tab. It needs the `SECRET_KEY`,
`DATABASE_URL`, `RESEND_API_KEY` and `DEFAULT_FROM_EMAIL`
repository secrets.

## Deployment

The included `Procfile` runs gunicorn:

```
web: gunicorn project.wsgi --bind 0.0.0.0:$PORT
```

### Render

`build.sh` is the build step. Set the Render **Build Command** to
`bash build.sh` (or leave it blank, which auto-detects the file).
It installs dependencies, collects static files and applies
migrations, in that order:

```bash
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --noinput
```

Set these environment variables on the service:

| Variable | Notes |
| --- | --- |
| `DJANGO_ENV` | `production`. Render does not set this for you. |
| `SECRET_KEY` | At least 50 characters. Changing it signs everyone out. |
| `DATABASE_URL` | Required. Render fills this in once a PostgreSQL database is linked under **Dashboard > Connect**. |
| `ALLOWED_HOSTS` | Your Render hostname. |
| `CSRF_TRUSTED_ORIGINS` | Same hostname, with `https://`. |
| `RESEND_API_KEY` | Needed for password reset email. |
| `DEFAULT_FROM_EMAIL` | Sender shown on outgoing mail. |
| `FRONTEND_BASE_URL` | Public `https://` address, used to build reset links. |

A PostgreSQL database is **not** declared in this repository, so
applying a Blueprint will not create or replace one. Link the
existing database to the service in the Render dashboard.

If `DATABASE_URL` is missing or malformed, or `SECRET_KEY` is
missing or shorter than 50 characters, the build stops there and
names the variable, instead of failing later with
`Please supply the ENGINE value` or with the far less useful
`Unknown command: 'collectstatic'`.

That second message is worth explaining, because it is misleading.
`collectstatic` is contributed by `django.contrib.staticfiles`, and
Django only finds it through the app registry. When the settings
module fails to import, `get_commands` returns just Django's core
commands instead, so the build reports an unknown command and the
real reason never appears. `project/settings.py` therefore always
imports: a problem is recorded in `DEPLOYMENT_ERRORS` and reported
from two places, both of which see the reason.

* `project/deployment.py` registers a system check for it. Django
  runs that check before `collectstatic`, `migrate`, `runserver` and
  `check` do any work, so each of those stops with the variable named,
  for example `(studybuddy.database_url) DATABASE_URL is not set`.
* `project/wsgi.py` and `project/asgi.py` refuse to boot. Gunicorn
  runs no system checks, so without this a broken deployment would
  come up and only fail on the first request.

`collectstatic` needs the settings module but never a database
connection, which is why it can now be used to diagnose a deployment
whose database settings are still wrong.

### Other hosts

Set `DJANGO_ENV=production` and the variables above in your host's
dashboard, then collect static files:

```bash
python manage.py collectstatic --noinput
```

WhiteNoise serves the collected files. The `static/` directory
holds the stylesheet and scripts and is tracked in git;
`staticfiles/` is generated output and is not. Re-run
`collectstatic` after any change under `static/`, otherwise the
deployed stylesheet is the stale one.

## Project layout

```
project/     settings, deployment checks, urls, wsgi/asgi
users/       auth, registration, profile, Resend backend
tasks/       Subject, Task, Note models, forms, views, urls
dashboard/   dashboard view and stats
templates/   base shell, per-app templates, shared includes
static/      css/app.css
media/       attachments when Cloudinary is not configured
```

## Tests

```bash
python manage.py test
```

215 tests cover the models, forms, views, ownership isolation
between accounts, login requirements, the dashboard statistics,
the reminder command, the Resend backend, and the deployment
configuration of the settings module.

## Interface

The UI is a custom design system in `static/css/app.css`; there is
no CSS framework. It has a light and a dark theme, and the theme
toggle in the sidebar remembers the choice.
