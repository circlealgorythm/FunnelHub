# FunnelHub Inbox App

Local React inbox for operator replies.

## Run Locally

Start the backend first:

```bash
cd ..
docker compose up -d postgres redis
python -m alembic upgrade head
$env:PYTHONPATH="src"; python -m uvicorn funnelhub.main:app --host 127.0.0.1 --port 8000
```

Configure inbox auth in the backend `.env`:

```bash
INBOX_ADMIN_USERNAME=aisu
INBOX_ADMIN_PASSWORD_HASH=<generated hash>
INBOX_SESSION_SECRET=<long random secret>
```

Generate a password hash:

```bash
$env:PYTHONPATH="src"; python -c "from funnelhub.services.auth import hash_password; print(hash_password('CHANGE_ME'))"
```

Start the inbox app:

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

The app reads `VITE_API_BASE_URL`; default is `http://127.0.0.1:8000`.
