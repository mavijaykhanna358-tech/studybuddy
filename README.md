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
| `RESEND_API_KEY` | unset | Without it, email prints to the console. **Required** in production. |
| `DEFAULT_FROM_EMAIL` | `onboarding@resend.dev` | Sender address. Must be on a domain verified in Resend. |
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

Mail goes out through the Resend HTTP API
(`users/email_backend.py`), which needs two things on Render:

1. `RESEND_API_KEY`, from <https://resend.com/api-keys>.
2. `DEFAULT_FROM_EMAIL` set to an address on a domain you have
   verified in Resend.

The second one is easy to miss. Resend's shared testing address,
`onboarding@resend.dev`, only delivers to the account owner's own
inbox and is rejected with a `403` for everyone else, so a password
reset sent from it never arrives. A production deployment that still
uses it fails the system check, which is the point.

`check` reports the first problem as `studybuddy.resend_api_key` and
the second as `studybuddy.default_from_email`, both of which stop a
build that could not deliver mail.

`EMAIL_BACKEND` is not something production gets to choose. A value
naming a backend that cannot deliver — console, locmem, filebased or
dummy — is **ignored in production** and the Resend backend is used
instead, for the same reason `DATABASE_URL` cannot fall back to
SQLite: a value that can only produce a broken deployment is not a
deployment decision worth honouring. A backend that genuinely sends,
such as SMTP, is still honoured, so leaving Resend entirely is allowed.

That override is reported as a warning, not an error:

```
?: (studybuddy.email_backend_ignored) EMAIL_BACKEND is set to
django.core.mail.backends.console.EmailBackend, which prints mail
instead of delivering it ... Delete EMAIL_BACKEND from the service to
stop this being reported.
```

The build passes, the mail is delivered, and the warning exists only
so the stale variable does not stay on the dashboard looking
effective. Outside production the console backend prints messages to
the terminal, which is all a local run needs.

Set `FRONTEND_BASE_URL` to the real https address so reset links
work off-site.

### When a reset email does not arrive

The backend logs the provider's own answer, so the Render log says
what Resend objected to:

```
INFO  users.email_backend: Resend accepted the message (id=... recipients=1 sender=no-reply@...)
ERROR users.email_backend: Resend rejected the email: code=403; type=validation_error; message=... (recipients=1 sender=no-reply@...)
ERROR users.forms: The password reset email could not be sent. The provider rejected the request or was unreachable.
```

`Resend accepted` with a message id is the proof of real delivery.
The rejected line is the diagnosis. Recipients, tokens, reset links
and the API key are redacted before anything is written, so these
lines are safe to paste into a bug report.

A failed send re-renders the form with "We could not send the reset
email just now" instead of redirecting to the "check your inbox"
page. Django's own `PasswordResetForm` logs the failure and carries
on, which shows a success page for a message that was never sent;
`StyledPasswordResetForm` sends without that blanket `except` so the
failure is visible.

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
| `RESEND_API_KEY` | Required. Without it the build stops: no email can be sent. |
| `DEFAULT_FROM_EMAIL` | Required. Must be on a domain verified in Resend, not `onboarding@resend.dev`. |
| `FRONTEND_BASE_URL` | Public `https://` address, used to build reset links. |

A PostgreSQL database is **not** declared in this repository, so
applying a Blueprint will not create or replace one. Link the
existing database to the service in the Render dashboard.

If `DATABASE_URL` is missing or malformed, `SECRET_KEY` is
missing or shorter than 50 characters, `RESEND_API_KEY` is unset, or
`DEFAULT_FROM_EMAIL` is still Resend's shared testing address, the
build stops there and names the variable, instead of failing later
with `Please supply the ENGINE value` or with the far less useful
`Unknown command: 'collectstatic'`.

`EMAIL_BACKEND` is handled differently. A stale value pointing at a
backend that cannot deliver is ignored in production rather than
being fatal, because the offending value lives in the Render
dashboard and not in this repository, so failing the build would
leave no way forward from here. Production uses Resend regardless and
reports the override as `studybuddy.email_backend_ignored`.

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

### Creating an admin on Render

Render Shell is a paid feature, so on a free plan the only way to
reach the production database is a command that runs during a build.
`provision_admin` is that command, and `build.sh` already calls it.

```bash
python manage.py provision_admin
```

It reads three environment variables and nothing else:

| Variable | Needed | Notes |
| --- | --- | --- |
| `ADMIN_USERNAME` | Always, to do anything | Without it the command does nothing. |
| `ADMIN_EMAIL` | Always, when the username is set | The address on the account. |
| `ADMIN_PASSWORD` | Only to create the account | Not needed to promote an existing one. |

**To create your first admin:**

1. On the Render service, under **Environment**, add the three
   variables. Set **Sync: No** on each one so the change applies to
   the next deploy rather than restarting the running container.
2. Pick a password that passes Django's validators: at least 8
   characters, not a common password, not all digits, and not
   similar to the username. A build is a good place for that to be
   enforced, so the command refuses a weak one and tells you which
   validator objected.
3. **Manual Deploy > Deploy latest commit**, or push any commit.
4. Watch the build log. A line like this means it worked:

   ```
   Created "siteadmin" (admin@studybuddy.example) as an active superuser.
   ```

5. Sign in at `https://<your-host>/admin/`.

**Then remove them.** Delete `ADMIN_PASSWORD` and redeploy
immediately; the next run reports the account is already an active
superuser and changes nothing. Once that is confirmed, delete
`ADMIN_USERNAME` and `ADMIN_EMAIL` too. The command stays in
`build.sh` and does nothing from then on, so it is not a way back
into the database.

The command is deliberately hard to misuse:

* **It does nothing at all without `ADMIN_USERNAME`,** and exits
  successfully, so a build can never be blocked by it and it leaves
  no working backdoor once the variables are gone.
* **It only ever touches one account.** Every query is filtered to a
  single row, so no other user can be read or written.
* **It never sets the password of an account that already exists.**
  A stale `ADMIN_PASSWORD` left on the service would otherwise reset
  the administrator's password on every deploy. Changing it needs
  the explicit `--reset-password` flag.
* **The password is never written to the build log,** not on success
  and not in the error a rejected password produces.
* **It refuses to create a second administrator on an address that
  already belongs to a staff account,** which is the duplicate the
  command exists to prevent.
* **It promotes `is_active` as well as `is_staff` and
  `is_superuser`,** because an inactive account cannot sign in
  however it is flagged.

Preview first with `--dry-run`, which reports what would change and
writes nothing. To change an existing password on purpose:

```bash
python manage.py provision_admin --reset-password
```

The command connects through the same `DATABASE_URL` the
application already uses and issues only portable ORM calls, so it
behaves identically on the Render PostgreSQL database. It is safe to
run in a normal development shell too, where it warns that it is
not the production database.

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
users/       auth, registration, profile, Resend backend,
             provision_admin command
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

281 tests cover the models, forms, views, ownership isolation
between accounts, login requirements, the dashboard statistics, the
reminder command, the Resend backend and its log redaction, the
whole password reset flow including a rejected send, the deployment
configuration of the settings module, and the admin provisioning
command including that it never reaches a second account or echoes
a password.

## Interface

The UI is a custom design system in `static/css/app.css`; there is
no CSS framework. It has a light and a dark theme, and the theme
toggle in the sidebar remembers the choice.
