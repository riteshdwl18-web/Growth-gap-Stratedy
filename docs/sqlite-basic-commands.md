# SQLite Basic Commands (CMD + Project Examples)

This quick reference is for Windows CMD and your DB:
`C:\Users\ritemaha\Desktop\GrowthGapStrategy\backend\runtime\app.db`

## 1. Open SQLite From CMD

### Option A: Use full sqlite path (works immediately)
```bat
"C:\Users\ritemaha\AppData\Local\Microsoft\WinGet\Packages\SQLite.SQLite_Microsoft.Winget.Source_8wekyb3d8bbwe\sqlite3.exe" "C:\Users\ritemaha\Desktop\GrowthGapStrategy\backend\runtime\app.db"
```

### Option B: Add sqlite to current CMD session PATH
```bat
set PATH=%PATH%;C:\Users\ritemaha\AppData\Local\Microsoft\WinGet\Packages\SQLite.SQLite_Microsoft.Winget.Source_8wekyb3d8bbwe
sqlite3 "C:\Users\ritemaha\Desktop\GrowthGapStrategy\backend\runtime\app.db"
```

## 2. Core SQLite Shell Commands

Run these after you see `sqlite>`:

```sql
.help
.tables
.schema
.schema runs
.databases
.quit
```

Useful output formatting:

```sql
.headers on
.mode column
.mode table
.mode csv
.nullvalue NULL
```

## 3. Basic SQL Commands (CRUD)

### Create table
```sql
CREATE TABLE IF NOT EXISTS demo (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT
);
```

### Insert rows
```sql
INSERT INTO demo (name, created_at) VALUES ('AAPL', datetime('now'));
INSERT INTO demo (name, created_at) VALUES ('MSFT', datetime('now'));
```

### Read rows
```sql
SELECT * FROM demo;
SELECT id, name FROM demo WHERE name = 'AAPL';
SELECT * FROM demo ORDER BY id DESC LIMIT 10;
```

### Update rows
```sql
UPDATE demo SET name = 'NVDA' WHERE id = 1;
```

### Delete rows
```sql
DELETE FROM demo WHERE id = 2;
DELETE FROM demo;
```

### Drop table
```sql
DROP TABLE IF EXISTS demo;
```

## 4. Transactions

```sql
BEGIN;
INSERT INTO demo (name, created_at) VALUES ('TSLA', datetime('now'));
UPDATE demo SET name = 'GOOGL' WHERE id = 1;
COMMIT;
```

If needed:

```sql
ROLLBACK;
```

## 5. Project-Specific Queries (GrowthGapStrategy)

Your `runs` progress fields are inside `payload_json`, so use `json_extract`.

### List latest runs with progress
```sql
SELECT
  run_id,
  status,
  CAST(json_extract(payload_json, '$.processed') AS INTEGER) AS processed,
  CAST(json_extract(payload_json, '$.total') AS INTEGER) AS total,
  created_at
FROM runs
ORDER BY created_at DESC
LIMIT 20;
```

### See available JSON keys in latest run payload
```sql
WITH latest AS (
  SELECT payload_json FROM runs ORDER BY created_at DESC LIMIT 1
)
SELECT key
FROM latest, json_each(latest.payload_json)
ORDER BY key;
```

### Count rows in each table
```sql
SELECT 'runs' AS table_name, COUNT(*) AS row_count FROM runs
UNION ALL
SELECT 'results', COUNT(*) FROM results
UNION ALL
SELECT 'uploads', COUNT(*) FROM uploads
UNION ALL
SELECT 'app_meta', COUNT(*) FROM app_meta;
```

### Delete all app data
```sql
BEGIN;
DELETE FROM results;
DELETE FROM runs;
DELETE FROM uploads;
DELETE FROM app_meta;
COMMIT;
```

### Compact database file after big deletes
```sql
VACUUM;
```

## 6. Import/Export CSV

### Export query to CSV from sqlite shell
```sql
.headers on
.mode csv
.once runs_export.csv
SELECT run_id, status, created_at FROM runs;
```

### Import CSV into a table
```sql
.mode csv
.import sample_upload.csv demo
```

Note: For import, create the destination table first with matching columns.

## 7. Backup and Restore

### Backup inside sqlite shell
```sql
.backup app_backup.db
```

### Dump full DB as SQL text
```sql
.output app_dump.sql
.dump
.output stdout
```

### Restore from SQL dump (run from CMD)
```bat
sqlite3 restored.db < app_dump.sql
```

## 8. Useful One-Liners From CMD

```bat
sqlite3 "C:\path\to\app.db" ".tables"
sqlite3 "C:\path\to\app.db" "SELECT COUNT(*) FROM runs;"
sqlite3 "C:\path\to\app.db" "PRAGMA integrity_check;"
```

## 9. Common Troubleshooting

- Error: `no such column ...`
  - Run `.schema <table_name>` and verify actual columns.
  - If values are in JSON text, query with `json_extract(...)`.

- Error: `database is locked`
  - Retry in read-only mode:
```bat
sqlite3 "file:C:/Users/ritemaha/Desktop/GrowthGapStrategy/backend/runtime/app.db?mode=ro" -uri
```

- sqlite3 command not found in CMD
  - Use full executable path, or reopen terminal after PATH update.
