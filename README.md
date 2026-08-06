# GrowthGapStrategy

Full-stack starter for the Growth Gap strategy.

- UI: Vue 3 + TypeScript + Vite
- API: FastAPI
- Runtime model: REST-based, async-ready architecture

## Project Structure

```
GrowthGapStrategy/
  frontend/              # Vue UI
  backend/               # FastAPI REST API
```

## Why Vue.js for this UI

Yes, Vue.js is a strong fit here:
- Fast component development for data-heavy dashboards
- Clean state handling and forms for run controls
- Easy integration with REST polling or WebSockets later

## Backend Setup

Start PostgreSQL first.

Option 1: Docker Compose

```bash
docker compose up -d postgres
```

Option 2: local PostgreSQL service

Create a database and user that match your `DATABASE_URL`.

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/growth_gap_strategy
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start Celery worker (separate terminal):

```bash
cd backend
. .venv/bin/activate
celery -A app.tasks worker --loglevel=info --pool=solo
```

PostgreSQL is now the primary application store for runs, results, uploads, users, sessions, live price cache, and saved filters.
On first startup with a configured `DATABASE_URL`, legacy data in `backend/runtime/app.db` and JSON runtime files is imported into PostgreSQL automatically.

Redis is required for Celery broker/result backend (default: `redis://127.0.0.1:6379/0`).

Open API docs:
- http://127.0.0.1:8000/docs

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open UI:
- http://127.0.0.1:5173

## Environment Variables

Frontend file: `frontend/.env`

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Backend variables (optional):

```env
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/growth_gap_strategy
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
FRONTEND_BASE_URL=http://127.0.0.1:5173
PASSWORD_RESET_TTL_MINUTES=20
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USERNAME=<your-brevo-smtp-login>
SMTP_PASSWORD=<your-brevo-smtp-key>
SMTP_FROM_EMAIL=<verified-sender@yourdomain.com>
SMTP_FROM_NAME=Growth Gap Strategy
SMTP_USE_TLS=true
```

### Forgot Password (Brevo Free Tier)

This project now supports full email-based password recovery:

- Request reset: `POST /api/auth/forgot-password`
- Complete reset: `POST /api/auth/reset-password`

Frontend routes:

- `/forgot-password`
- `/reset-password?token=<token>`

Brevo setup steps:

1. Create a Brevo account and open SMTP settings.
2. Add and verify your sender email/domain in Brevo.
3. Put SMTP values in `backend/.env` using the variables above.
4. Restart backend.
5. Use Forgot Password from login page and verify email delivery.

Security behavior:

- Forgot password response is generic and does not reveal whether account exists.
- Reset token is single-use and expires after `PASSWORD_RESET_TTL_MINUTES`.
- Raw reset token is never stored in DB; only SHA-256 hash is stored.
- Existing sessions are invalidated after password reset.

If you see `connection refused` for `127.0.0.1:5432`, PostgreSQL is not running yet or the `DATABASE_URL` does not match the actual host, port, database, username, or password.

## Implemented REST Endpoints

- `GET /health`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/results`
- `GET /api/runs/{run_id}/download.csv`
- `POST /api/runs/{run_id}/stop`
- `POST /api/uploads/validate`
- `POST /api/runs/from-upload/{upload_id}`

## CSV Upload Validation Rules

Upload is accepted only when headers match this exact allow-list:

- `Name`
- `BSE Code`
- `NSE Code`
- `ISIN Code`
- `Industry Group`

Validation behavior:

- Missing or unexpected headers fail validation.
- Fully blank lines are ignored.
- Rows with blank `NSE Code` are rejected.
- Valid rows are persisted in backend runtime storage and can be processed via `POST /api/runs/from-upload/{upload_id}`.

## Current Processing Mode

- Celery workers execute the real strategy implementation from sibling `SwingTrading/stock_screener.py`.
- Run status transitions: `queued -> running -> completed` (or `stopped`/`failed`).
- Per-symbol output is available through `GET /api/runs/{run_id}/results`.
- Stopped runs include `stopped_at` in run metadata.
- CSV download is enabled only after run completion via `GET /api/runs/{run_id}/download.csv`.
- If Redis/Celery broker is unavailable, backend automatically falls back to local background processing so runs do not fail at enqueue time.
- First-time visitors land on the login page; account creation remains available from the login screen when no users exist yet.

## Next Build Steps

1. Add schema-managed migrations for PostgreSQL changes.
2. Add task retry/backoff policy for transient fetch/network issues.
3. Wire this API to your existing `stock_screener.py` logic as a service module.
4. Add auth and role-based access if multi-user.
5. Add Google Sheets export endpoint and settings page.

## Docker Quick Start (Local PostgreSQL Only)

Use this when you only want PostgreSQL in Docker and run backend/frontend manually on host.

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Check health:

```bash
docker compose ps
docker compose logs -f postgres
```

Stop PostgreSQL:

```bash
docker compose stop postgres
```

Remove PostgreSQL container and volume (full reset):

```bash
docker compose down -v
```

## Docker Deployment (Single VM, Full Stack)

This repo includes a full-stack deployment compose file at `compose.deploy.yaml`:

- `postgres` (persistent volume)
- `redis`
- `backend` (FastAPI)
- `worker` (Celery)
- `frontend` (Nginx + built Vue assets)

### 1) Prepare Docker env

```bash
cp backend/.env.docker.example backend/.env.docker
```

Edit `backend/.env.docker` and set:

- `CORS_ORIGINS` to your real domain or public IP origin
- `SESSION_COOKIE_SECURE=true` in production
- Forgot password email settings if you use reset links:
  - `FRONTEND_BASE_URL`
  - `PASSWORD_RESET_TTL_MINUTES`
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USERNAME`
  - `SMTP_PASSWORD`
  - `SMTP_FROM_EMAIL`
  - `SMTP_FROM_NAME`
  - `SMTP_USE_TLS`

Optional: set frontend API URL at runtime build time:

```bash
export VITE_API_BASE_URL=http://<your-server-ip>
```

### 2) Build and run

```bash
docker compose -f compose.deploy.yaml up -d --build
```

Rebuild only changed services:

```bash
docker compose -f compose.deploy.yaml up -d --build backend worker
docker compose -f compose.deploy.yaml up -d --build frontend
```

### 3) Check status

```bash
docker compose -f compose.deploy.yaml ps
docker compose -f compose.deploy.yaml logs -f backend
docker compose -f compose.deploy.yaml logs -f worker
docker compose -f compose.deploy.yaml logs -f frontend
docker compose -f compose.deploy.yaml logs -f postgres
docker compose -f compose.deploy.yaml logs -f redis
```

Restart a single service:

```bash
docker compose -f compose.deploy.yaml restart backend
docker compose -f compose.deploy.yaml restart worker
docker compose -f compose.deploy.yaml restart frontend
```

Stop stack without deleting volumes:

```bash
docker compose -f compose.deploy.yaml stop
```

Stop and remove stack:

```bash
docker compose -f compose.deploy.yaml down
```

Full reset (delete Postgres + runtime volumes):

```bash
docker compose -f compose.deploy.yaml down -v
```

### 4) Endpoints

- Frontend: `http://<your-server-ip>/`
- Backend health (proxied): `http://<your-server-ip>/health`

Useful backend endpoints after deployment:

- `http://<your-server-ip>/docs`
- `http://<your-server-ip>/api/auth/me`

The compose stack binds Postgres, Redis, and backend to localhost only on the VM (`127.0.0.1`), and only exposes frontend on port `80`.

## Common Docker Troubleshooting

If frontend opens but API fails:

```bash
docker compose -f compose.deploy.yaml logs -f backend
docker compose -f compose.deploy.yaml logs -f frontend
```

If backend cannot connect to Postgres:

```bash
docker compose -f compose.deploy.yaml logs -f postgres
docker compose -f compose.deploy.yaml exec postgres pg_isready -U postgres -d growth_gap_strategy
```

If forgot password returns success but no email arrives:

```bash
docker compose -f compose.deploy.yaml logs -f backend | grep -i "smtp\|password reset\|auth"
```
