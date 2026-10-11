# Cryptor Web

Cryptor Web is the Django migration of the Cryptor App desktop project. It is
an independent, local-first project; the existing Tkinter application remains
unchanged in the parent directory.

## Included in the first complete web version

- Account registration, login, logout, and 45-minute sessions
- A separate scrypt-derived vault key that is never written directly to a
  cookie or database
- Per-document AES-EAX encryption and authentication
- Owner-isolated document creation, reading, updating, and deletion
- Local Ollama drafting with actionable model, connection, and timeout errors
- Responsive browser UI and CSRF-protected forms
- Automated security and end-to-end tests

## Start the app

```bash
git clone https://github.com/mapenzim/cryptor-django.git
cd cryptor-django
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and create a new vault account.

The environment has already been prepared in this checkout, so the shortest
way to start it now is:

```bash
cd cryptor-django
./run_local.sh
```

## Import an existing desktop vault

The importer reads the desktop database in read-only mode, verifies every
encrypted document before writing anything, and can safely be run again to
refresh already imported records:

```bash
source .venv/bin/activate
python manage.py import_desktop_vault --username YOUR_DESKTOP_USERNAME
```

Enter the desktop vault password at the hidden prompt. The new web login uses
the same username and password. The source database at
`~/.cryptor_app/notebookserver.db` is never modified.

For AI drafting, install and start Ollama, then pull the model:

```bash
ollama pull llama3:8b
```

## Run tests

```bash
source .venv/bin/activate
python manage.py test
```

## Configuration

The defaults are intended for local testing. Before exposing the app to a
network, set at least:

```bash
export CRYPTOR_DJANGO_SECRET_KEY='a-long-random-production-secret'
export CRYPTOR_DJANGO_DEBUG=0
export CRYPTOR_DJANGO_ALLOWED_HOSTS='vault.example.com'
```

Optional settings:

- `CRYPTOR_OLLAMA_MODEL` (default `llama3:8b`)
- `CRYPTOR_OLLAMA_TIMEOUT` (default `300` seconds)
- `CRYPTOR_DJANGO_TIME_ZONE` (default `Africa/Harare`)

## Security boundary

This version is designed to run on the same trusted computer as the desktop
app. Vault keys exist only in process memory and disappear on logout, expiry,
or server restart. A restart leaves the Django login session intact but asks
the user to unlock the vault again.

Public multi-server hosting needs an explicit key-management design and should
not use the development secret key or server.

