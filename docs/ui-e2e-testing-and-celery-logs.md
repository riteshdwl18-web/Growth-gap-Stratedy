# UI E2E Testing and Celery Logs Runbook

This runbook covers:
- Starting all services
- Verifying Celery is active
- Testing all major UI functionality end to end
- Checking Celery logs and task behavior

## 1) Prerequisites

- Redis running at redis://127.0.0.1:6379/0
- Backend venv installed with dependencies
- Frontend dependencies installed

If Redis is not running locally, start it with Docker:

```powershell
docker run --name growthgap-redis -p 6379:6379 -d redis:7
```

## 2) Start Services (3 Terminals)

### Terminal A: Backend API

```powershell
Set-Location C:\Users\ritemaha\Desktop\GrowthGapStrategy\backend
.\growthgapup\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Terminal B: Celery Worker

```powershell
Set-Location C:\Users\ritemaha\Desktop\GrowthGapStrategy\backend
.\growthgapup\Scripts\Activate.ps1
celery -A app.tasks worker --loglevel=info --pool=solo
```

Optional: write Celery logs to file

```powershell
Set-Location C:\Users\ritemaha\Desktop\GrowthGapStrategy\backend
.\growthgapup\Scripts\Activate.ps1
New-Item -ItemType Directory -Force -Path .\runtime\logs | Out-Null
celery -A app.tasks worker --loglevel=info --pool=solo --logfile=.\runtime\logs\celery-worker.log
```

### Terminal C: Frontend

```powershell
Set-Location C:\Users\ritemaha\Desktop\GrowthGapStrategy\frontend
npm run dev -- --host=127.0.0.1 --port=5173
```

Open app:
- http://127.0.0.1:5173

## 3) Quick Health Checks

### Backend health

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/health
```

### Celery worker reachable from control API

Run from backend terminal with venv active:

```powershell
celery -A app.tasks inspect ping
```

Expected output includes pong from at least one worker.

## 4) Full UI Test Checklist

## A. Authentication and Shell

1. Open app and log in.
2. Confirm navigation works between Dashboard, Runs, and Run Details.

Expected:
- No 401 loops after login.
- Sidebar and page routing stable.

## B. CSV Validation and Start Run

1. Go to Dashboard.
2. Upload a valid CSV with headers:
   - Name
   - BSE Code
   - NSE Code
   - ISIN Code
   - Industry Group
3. Click Validate.
4. Start workflow run.

Expected:
- Validation summary appears.
- Run is created quickly (non-blocking).
- You can navigate away while processing continues.

## C. Active Processing and Status Flow

1. Open Runs page.
2. Observe status progression for a new run:
   - queued
   - preparing
   - running
   - cooling_down (if retry/backoff triggers)
   - completed or partial_completed
3. Confirm processed counters increase over time.

Expected:
- Polling updates automatically.
- Stop button enabled only while run is active.

## D. Run Details Progress Panel

1. Open a run in Run Details.
2. Verify strip shows:
   - status
   - stage
   - retry count
   - cooldown info (if active)
   - processed/pass/fail/skipped metrics
3. Verify cooldown countdown decreases when cooling_down.

Expected:
- Progress UI reflects current backend state.

## E. Filters, Favorites, Results Table

1. Use search and filters in Run Details.
2. Save favorite filter.
3. Edit, set default, and delete favorite.
4. Export filtered results CSV.

Expected:
- Favorites persist per user.
- Filtered export downloads.

## F. Retry Failed Rows Flow

1. Pick a finished run with skipped rows.
2. Click Retry N chip on Runs page, or click Retry Failed Rows in Run Details.
3. Confirm modal action.
4. Verify a new run starts.

Expected:
- New run is created from retryable error rows only.
- Retry run appears in Runs list with its own progress.

## G. Completion and Download Rules

1. For completed and partial_completed runs, click Download run CSV.
2. For active runs, verify download remains disabled.

Expected:
- Download enabled only for completed and partial_completed.

## H. Stop Run Behavior

1. Start a run.
2. Click Stop in Runs list.

Expected:
- Run transitions to stopped.
- stopped_at is populated.
- No further row processing occurs.

## 5) Celery Logs: How to Check

## Live worker console logs

If worker runs in foreground, logs are printed directly in Terminal B.

## Tail file logs (if --logfile used)

```powershell
Get-Content C:\Users\ritemaha\Desktop\GrowthGapStrategy\backend\runtime\logs\celery-worker.log -Wait
```

## Filter for task lines

```powershell
Select-String -Path C:\Users\ritemaha\Desktop\GrowthGapStrategy\backend\runtime\logs\celery-worker.log -Pattern "process_run_task|Task|ERROR|WARNING"
```

## Inspect active/reserved/scheduled tasks

Run from backend terminal with venv active:

```powershell
celery -A app.tasks inspect active
celery -A app.tasks inspect reserved
celery -A app.tasks inspect scheduled
```

## Worker stats

```powershell
celery -A app.tasks inspect stats
```

## 6) Validate Task Is Really Celery (Not Local Fallback)

Use these checks:

1. Keep worker running, start a run from UI, and confirm Task received/executed logs in Celery terminal.
2. Stop Celery worker and start another run.
3. Restart worker and compare behavior.

Expected:
- With worker running: task logs appear in Celery worker output.
- With worker stopped: run still proceeds via backend local fallback.

Optional DB check for full payload metadata:

```powershell
Set-Location C:\Users\ritemaha\Desktop\GrowthGapStrategy\backend
.\growthgapup\Scripts\Activate.ps1
python -c "import sqlite3; c=sqlite3.connect('runtime/app.db'); r=c.execute('select run_id,payload_json from runs order by created_at desc limit 3').fetchall(); print(r); c.close()"
```

## 7) API Smoke Commands (Optional)

## List runs

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/runs" -WebSession $session
```

## Stop run

```powershell
Invoke-WebRequest -Method Post -Uri "http://127.0.0.1:8000/api/runs/<run_id>/stop" -WebSession $session
```

## Retry failed rows

```powershell
Invoke-WebRequest -Method Post -Uri "http://127.0.0.1:8000/api/runs/<run_id>/retry-failed" -WebSession $session
```

## 8) Common Troubleshooting

## 401 Unauthorized in UI

- Ensure frontend host matches backend cookie host style:
  - Use 127.0.0.1 for both frontend and backend, or localhost for both.

## Celery command not found

- Activate backend venv first.
- Reinstall backend requirements.

## No Celery task logs

- Verify worker is started with -A app.tasks
- Verify Redis reachable on 127.0.0.1:6379
- Run celery -A app.tasks inspect ping

## No retry button enabled

- Retry button enables only for finished runs with skipped rows.
- Active runs cannot start retry.
