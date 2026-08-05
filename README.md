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

# Google OAuth (required for Sign In with Google)
GOOGLE_OAUTH_ENABLED=true
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

For Google Cloud Console, configure the OAuth client with these local values:

- Authorized JavaScript origins: `http://127.0.0.1:5173` and `http://localhost:5173`
- Authorized redirect URIs: `http://127.0.0.1:8000/api/auth/google/callback`

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

## Docker Deployment (Single VM)

This repo includes a deployment compose stack in `compose.deploy.yaml` for:

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
- Google OAuth values if you use Google sign-in:
  - `GOOGLE_OAUTH_ENABLED=true`
  - `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
  - `GOOGLE_REDIRECT_URI=https://<your-domain>/api/auth/google/callback`

Google OAuth production checklist:

- Use HTTPS for your public app URL (Google does not allow non-HTTPS callback URIs for public domains).
- In Google Cloud Console, add:
  - Authorized JavaScript origins: `https://<your-domain>`
  - Authorized redirect URIs: `https://<your-domain>/api/auth/google/callback`
- Ensure `CORS_ORIGINS` contains the same frontend origin used above.

### 2) Build and run

```bash
docker compose -f compose.deploy.yaml up -d --build
```

### 3) Check status

```bash
docker compose -f compose.deploy.yaml ps
docker compose -f compose.deploy.yaml logs -f backend
docker compose -f compose.deploy.yaml logs -f worker
```

### 4) Endpoints

- Frontend: `http://<your-server-ip>/`
- Backend health (proxied): `http://<your-server-ip>/health`

The compose stack binds Postgres, Redis, and backend to localhost only on the VM (`127.0.0.1`), and only exposes frontend on port `80`.
