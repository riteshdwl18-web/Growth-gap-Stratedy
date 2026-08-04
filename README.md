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

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start Celery worker (separate terminal):

```bash
cd backend
.venv\Scripts\activate
celery -A app.tasks worker --loglevel=info --pool=solo
```

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
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

# Google OAuth (required for Sign In with Google)
GOOGLE_OAUTH_ENABLED=true
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

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

## Next Build Steps

1. Replace file-based runtime store with PostgreSQL tables.
2. Add task retry/backoff policy for transient fetch/network issues.
3. Wire this API to your existing `stock_screener.py` logic as a service module.
4. Add auth and role-based access if multi-user.
5. Add Google Sheets export endpoint and settings page.
