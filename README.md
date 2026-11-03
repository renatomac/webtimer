# webtimer

A multi-studio round timer for jiu-jitsu studios (Django). Each studio gets its own
workspace, presets, logo, timezone and timer session. Staff control the timer from a
phone/laptop; a TV shows a read-only display through a secret, revocable link.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_DEBUG=1            # enables an insecure dev SECRET_KEY, local hosts, media serving
python manage.py migrate
python manage.py createsuperuser # platform administrator
python manage.py runserver
python manage.py test            # run the test suite
```

### Environment variables

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Required when `DJANGO_DEBUG` is off. |
| `DJANGO_DEBUG` | `1` for development only. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts, e.g. `yourname.pythonanywhere.com`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Optional, e.g. `https://yourname.pythonanywhere.com`. |
| `DJANGO_STATIC_ROOT` / `DJANGO_MEDIA_ROOT` | Default `./staticfiles` and `./media`. |
| `DB_PATH` | SQLite file (default `./db.sqlite3`). |
| `DB_ENGINE=mysql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` | Use MySQL instead of SQLite. |
| `DJANGO_SECURE_COOKIES` | Defaults to `1` when not in debug; set `0` only for plain HTTP. |

## Creating the first studio (platform administrator)

1. Log in at `/admin/` with the superuser.
2. Create a user for the studio administrator (Users → Add). Leave "staff" off: they
   only use the timer app, not Django admin.
3. Studios → Add: set name, slug (the URL, `/s/<slug>/`), timezone (e.g. `America/Sao_Paulo`)
   and optional logo. In the **Studio memberships** section add the user.
4. The studio administrator logs in at `/accounts/login/`, creates presets under **Presets**, and
   copies the TV link from the control page. "Revoke and regenerate link" (or the admin
   action) invalidates the old link immediately.

A studio administrator can only see and change their own studio; other studios return 404.

## Deploying on PythonAnywhere

1. Open a Bash console, clone the repo and create a virtualenv:
   ```bash
   git clone <repo-url> ~/webtimer && cd ~/webtimer
   mkvirtualenv webtimer --python=python3.12
   pip install -r requirements.txt
   ```
2. **Web** tab → *Add a new web app* → Manual configuration (same Python version). Set the
   virtualenv to `/home/<user>/.virtualenvs/webtimer` and source code to `/home/<user>/webtimer`.
3. **Environment variables and WSGI**: edit the WSGI file shown on the Web tab to contain:
   ```python
   import os, sys
   path = "/home/<user>/webtimer"
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ["DJANGO_SECRET_KEY"] = "<long random string>"
   os.environ["DJANGO_ALLOWED_HOSTS"] = "<user>.pythonanywhere.com"
   os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = "https://<user>.pythonanywhere.com"
   os.environ["DB_PATH"] = "/home/<user>/webtimer-data/db.sqlite3"
   os.environ["DJANGO_STATIC_ROOT"] = "/home/<user>/webtimer-static"
   os.environ["DJANGO_MEDIA_ROOT"] = "/home/<user>/webtimer-media"
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
   Generate a key with `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`.
   (For the management commands below, export the same variables in the console.)
4. **Database** (SQLite is fine for the MVP; for MySQL create a database in the *Databases*
   tab, `pip install mysqlclient` and set `DB_ENGINE=mysql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`).
   ```bash
   mkdir -p ~/webtimer-data ~/webtimer-media
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py collectstatic --noinput
   ```
5. **Static and media**: on the Web tab, *Static files*:
   - URL `/static/` → directory `/home/<user>/webtimer-static`
   - URL `/media/` → directory `/home/<user>/webtimer-media`
6. Click **Reload**, then create the first studio as described above.

## Manual verification (TV display + command screen)

1. Create a studio with a preset: 2 rounds, `00:10` round, `00:05` rest, count down. Add a logo.
2. Browser A (the "TV"): open the display link. Click **Enable sound** once. It should show
   the date/time in the studio timezone, `Ready`, `10:00`-style digits (`00:10`) and a faint logo.
3. Browser B (phone/laptop, logged in): open `/s/<slug>/`. Start/Pause/Resume/Stop/Reset
   buttons should enable and disable according to the state (e.g. only Start while Ready).
4. Press **Start**. Within ~1 s the TV shows `Round 1 of 2 · Rolling` counting down from `00:10`.
   Listen for one beep each at 3, 2 and 1 s remaining, then a distinct bell at 0.
5. Rest: the TV shows `Rest before Round 2 of 2`, with beeps at 3/2/1 s and no bell at the end of rest.
6. Round 2 repeats the beeps and ends with the bell, then the TV shows `Finished` (no rest after the final round).
7. Pause mid-round: both screens freeze and show `Paused`; Resume continues from the same value.
   Stop shows `Stopped`; Reset returns to `Ready`.
8. While running, refresh the TV page: it recovers phase, round and time without restarting
   (click Enable sound again after a reload). No beeps should fire for cues that already passed.
9. Edit the preset (e.g. 3 rounds) while a run is active: the current run is unaffected; the
   next Start uses the new values. Repeat with a count-up preset: digits start at `00:00`
   and end at the configured duration in both rolling and rest phases, with the same sound cues.
10. Click "Revoke and regenerate link": the old TV URL returns 404.
11. Log in as a second studio's administrator: they cannot open the first studio's URLs (404).
