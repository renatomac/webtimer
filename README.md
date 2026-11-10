# webtimer

A Django round-timer app based on the timer experience in the CRM project. Users can
create personal timers with work/rest rounds, run them with audio cues, and optionally
connect Spotify playback controls.

The previous multi-studio timer remains available under `/legacy/`. Its Studio, Preset,
and TimerSession data is preserved; new CRM-style timers start empty.

## Spotify music controls

The controller includes Spotify playlist, device, playback, shuffle, and volume controls.
Create a Spotify developer application and register this exact callback URL:

`https://your-domain.example/timers/spotify/callback/`

Then set `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, and `SPOTIFY_REDIRECT_URI` in the
server environment. Spotify playback control requires Spotify Premium and an active device.

## Local development

On Windows PowerShell (set `DJANGO_DEBUG` in each new terminal):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DJANGO_DEBUG = "1"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

On Bash:

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
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI` | Optional Spotify OAuth credentials; callback URI must end in `/timers/spotify/callback/`. |

## Using the timer app

1. Run migrations, create a Django user, and log in at `/accounts/login/`.
2. Open `/timers/` and create a timer with its round count, work duration, rest interval,
   count direction, and optional finish sound.
3. Open a timer to start, pause, or reset it. Your timers are private to your account.
4. To configure Spotify, register `https://your-domain.example/timers/spotify/callback/`
   as the redirect URI in your Spotify developer application and set the Spotify
   environment variables before restarting the app.

The timer migration adds a per-user Timer table without dropping the previous Studio,
Preset, or TimerSession tables. Those legacy screens remain at `/legacy/`; the root URL
redirects to the new timer library.

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
6. Click **Reload**, then create a user and timer as described above.

For later updates, pull the changes and run `python manage.py collectstatic --noinput`
with the same `DJANGO_STATIC_ROOT` used by the Web tab's `/static/` mapping, then
click **Reload**. Reloading Django alone does not update PythonAnywhere's served
CSS files. The timer layout stylesheet has a version query parameter to refresh
browser caches; increment it whenever that stylesheet changes.

## Manual verification

1. Create a 2-round timer with a 10-second work phase and 5-second rest. Verify the total
   excludes rest after the final round.
2. Run the timer and verify it transitions through work, rest, and finished states; test
   pause, resume, and reset.
3. Create a second user and confirm each user can only list and operate their own timers.
4. If Spotify is configured, connect an account and test playlist/device selection and
   playback controls. Without configuration, the timer should explain that Spotify is unavailable.
5. Open `/legacy/` and verify the existing Studio/Preset data remains available.
