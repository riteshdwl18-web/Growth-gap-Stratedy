from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
RUNS_DIR = RUNTIME_DIR / "runs"
RESULTS_DIR = RUNTIME_DIR / "results"
UPLOADS_DIR = RUNTIME_DIR / "uploads"
EXPORTS_DIR = RUNTIME_DIR / "exports"
DB_PATH = RUNTIME_DIR / "app.db"


for directory in (RUNS_DIR, RESULTS_DIR, UPLOADS_DIR, EXPORTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)


_db_init_lock = threading.Lock()
_db_initialized = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row["name"]) == column_name for row in rows)


def _init_db() -> None:
    global _db_initialized
    if _db_initialized:
        return

    with _db_init_lock:
        if _db_initialized:
            return

        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    row_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_results_run_id
                ON results(run_id, id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    upload_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    valid INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
                ON sessions(expires_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS live_price_cache (
                    symbol TEXT PRIMARY KEY,
                    price REAL NOT NULL,
                    quote_as_of TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_live_price_cache_expires_at
                ON live_price_cache(expires_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_result_filters (
                    filter_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    name TEXT NOT NULL,
                    query_json TEXT NOT NULL,
                    is_default INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_user_result_filters_user_name
                ON user_result_filters(username, name)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_result_filters_user_default
                ON user_result_filters(username, is_default)
                """
            )

            if not _table_has_column(conn, "runs", "username"):
                conn.execute("ALTER TABLE runs ADD COLUMN username TEXT NOT NULL DEFAULT ''")
            if not _table_has_column(conn, "uploads", "username"):
                conn.execute("ALTER TABLE uploads ADD COLUMN username TEXT NOT NULL DEFAULT ''")

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runs_username_created_at
                ON runs(username, created_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_uploads_username_created_at
                ON uploads(username, created_at)
                """
            )
            conn.commit()

        _bootstrap_from_json_files_once()
        _db_initialized = True


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return str(row["value"])


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_meta(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _bootstrap_from_json_files_once() -> None:
    with _connect() as conn:
        if _meta_get(conn, "migrated_from_json") == "1":
            return

        # Migrate runs
        for path in RUNS_DIR.glob("*.json"):
            payload = _read_json(path, None)
            if not isinstance(payload, dict):
                continue
            run_id = str(payload.get("run_id") or path.stem)
            status = str(payload.get("status", "queued"))
            created_at = str(payload.get("created_at", now_iso()))
            conn.execute(
                """
                INSERT OR REPLACE INTO runs(run_id, username, status, created_at, payload_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (run_id, str(payload.get("username", "")), status, created_at, json.dumps(payload, ensure_ascii=True)),
            )

        # Migrate results
        for path in RESULTS_DIR.glob("*.json"):
            run_id = path.stem
            rows = _read_json(path, [])
            if not isinstance(rows, list):
                continue
            conn.execute("DELETE FROM results WHERE run_id = ?", (run_id,))
            for row in rows:
                if not isinstance(row, dict):
                    continue
                conn.execute(
                    "INSERT INTO results(run_id, row_json) VALUES(?, ?)",
                    (run_id, json.dumps(row, ensure_ascii=True)),
                )

        # Migrate uploads
        for path in UPLOADS_DIR.glob("*.json"):
            payload = _read_json(path, None)
            if not isinstance(payload, dict):
                continue
            upload_id = str(payload.get("upload_id") or path.stem)
            created_at = str(payload.get("created_at", now_iso()))
            valid = 1 if bool(payload.get("valid", False)) else 0
            conn.execute(
                """
                INSERT OR REPLACE INTO uploads(upload_id, username, created_at, valid, payload_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    str(payload.get("username", "")),
                    created_at,
                    valid,
                    json.dumps(payload, ensure_ascii=True),
                ),
            )

        _meta_set(conn, "migrated_from_json", "1")
        conn.commit()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=True, indent=2)
    tmp_path.replace(path)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as file_obj:
        return json.load(file_obj)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def results_path(run_id: str) -> Path:
    return RESULTS_DIR / f"{run_id}.json"


def upload_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}.json"


def export_csv_path(run_id: str) -> Path:
    return EXPORTS_DIR / f"{run_id}.csv"


def save_run(run_id: str, payload: dict[str, Any]) -> None:
    _init_db()
    username = str(payload.get("username", ""))
    status = str(payload.get("status", "queued"))
    created_at = str(payload.get("created_at", now_iso()))
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO runs(run_id, username, status, created_at, payload_json)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                username = excluded.username,
                status = excluded.status,
                created_at = excluded.created_at,
                payload_json = excluded.payload_json
            """,
            (run_id, username, status, created_at, json.dumps(payload, ensure_ascii=True)),
        )
        conn.commit()


def load_run(run_id: str) -> dict[str, Any] | None:
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT payload_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    return json.loads(str(row["payload_json"]))


def list_runs_payloads(username: str | None = None) -> list[dict[str, Any]]:
    _init_db()
    with _connect() as conn:
        if username is None:
            rows = conn.execute("SELECT payload_json FROM runs").fetchall()
        else:
            rows = conn.execute(
                "SELECT payload_json FROM runs WHERE username = ?",
                (username,),
            ).fetchall()
    return [json.loads(str(row["payload_json"])) for row in rows]


def save_results(run_id: str, rows: list[dict[str, Any]]) -> None:
    _init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM results WHERE run_id = ?", (run_id,))
        for row in rows:
            conn.execute(
                "INSERT INTO results(run_id, row_json) VALUES(?, ?)",
                (run_id, json.dumps(row, ensure_ascii=True)),
            )
        conn.commit()


def load_results(run_id: str) -> list[dict[str, Any]]:
    _init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT row_json FROM results WHERE run_id = ? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
    return [json.loads(str(row["row_json"])) for row in rows]


def append_result(run_id: str, row: dict[str, Any]) -> None:
    _init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO results(run_id, row_json) VALUES(?, ?)",
            (run_id, json.dumps(row, ensure_ascii=True)),
        )
        conn.commit()


def save_upload(upload_id: str, payload: dict[str, Any], username: str) -> None:
    _init_db()
    created_at = str(payload.get("created_at", now_iso()))
    valid = 1 if bool(payload.get("valid", False)) else 0
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO uploads(upload_id, username, created_at, valid, payload_json)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(upload_id) DO UPDATE SET
                username = excluded.username,
                created_at = excluded.created_at,
                valid = excluded.valid,
                payload_json = excluded.payload_json
            """,
            (upload_id, username, created_at, valid, json.dumps(payload, ensure_ascii=True)),
        )
        conn.commit()


def load_upload(upload_id: str, username: str | None = None) -> dict[str, Any] | None:
    _init_db()
    with _connect() as conn:
        if username is None:
            row = conn.execute("SELECT payload_json FROM uploads WHERE upload_id = ?", (upload_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT payload_json FROM uploads WHERE upload_id = ? AND username = ?",
                (upload_id, username),
            ).fetchone()
    if row is None:
        return None
    return json.loads(str(row["payload_json"]))


def count_users() -> int:
    _init_db()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    if row is None:
        return 0
    return int(row["total"])


def load_user(username: str) -> dict[str, Any] | None:
    _init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT username, password_hash, salt, created_at
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
    if row is None:
        return None

    return {
        "username": str(row["username"]),
        "password_hash": str(row["password_hash"]),
        "salt": str(row["salt"]),
        "created_at": str(row["created_at"]),
    }


def save_user(username: str, password_hash: str, salt: str) -> None:
    _init_db()
    created_at = now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO users(username, password_hash, salt, created_at)
            VALUES(?, ?, ?, ?)
            """,
            (username, password_hash, salt, created_at),
        )
        conn.commit()


def save_session(token: str, username: str, expires_at: str) -> None:
    _init_db()
    created_at = now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions(token, username, expires_at, created_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(token) DO UPDATE SET
                username = excluded.username,
                expires_at = excluded.expires_at
            """,
            (token, username, expires_at, created_at),
        )
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (created_at,))
        conn.commit()


def load_session(token: str) -> dict[str, Any] | None:
    _init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT token, username, expires_at, created_at
            FROM sessions
            WHERE token = ?
            """,
            (token,),
        ).fetchone()
    if row is None:
        return None

    return {
        "token": str(row["token"]),
        "username": str(row["username"]),
        "expires_at": str(row["expires_at"]),
        "created_at": str(row["created_at"]),
    }


def delete_session(token: str) -> None:
    _init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def load_live_price_cache(symbols: list[str]) -> dict[str, dict[str, Any]]:
    _init_db()
    clean_symbols = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    if not clean_symbols:
        return {}

    placeholders = ",".join(["?"] * len(clean_symbols))
    params = [*clean_symbols]
    query = (
        "SELECT symbol, price, quote_as_of, expires_at, source "
        "FROM live_price_cache "
        f"WHERE symbol IN ({placeholders})"
    )

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    cached: dict[str, dict[str, Any]] = {}
    for row in rows:
        cached[str(row["symbol"])]= {
            "price": float(row["price"]),
            "quote_as_of": str(row["quote_as_of"]),
            "expires_at": str(row["expires_at"]),
            "source": str(row["source"]),
        }
    return cached


def save_live_price_cache(
    quotes: dict[str, float],
    quote_as_of: str,
    expires_at: str,
    source: str = "google_finance",
) -> None:
    _init_db()
    if not quotes:
        return

    updated_at = now_iso()
    rows = [
        (symbol.strip().upper(), float(price), quote_as_of, expires_at, updated_at, source)
        for symbol, price in quotes.items()
        if symbol.strip()
    ]
    if not rows:
        return

    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO live_price_cache(symbol, price, quote_as_of, expires_at, updated_at, source)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                price = excluded.price,
                quote_as_of = excluded.quote_as_of,
                expires_at = excluded.expires_at,
                updated_at = excluded.updated_at,
                source = excluded.source
            """,
            rows,
        )
        conn.execute("DELETE FROM live_price_cache WHERE expires_at <= ?", (updated_at,))
        conn.commit()


def list_user_result_filters(username: str) -> list[dict[str, Any]]:
    _init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT filter_id, username, name, query_json, is_default, created_at, updated_at
            FROM user_result_filters
            WHERE username = ?
            ORDER BY is_default DESC, updated_at DESC
            """,
            (username,),
        ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "filter_id": str(row["filter_id"]),
                "username": str(row["username"]),
                "name": str(row["name"]),
                "query": json.loads(str(row["query_json"])),
                "is_default": bool(int(row["is_default"])),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
        )
    return items


def save_user_result_filter(
    username: str,
    name: str,
    query: dict[str, Any],
    is_default: bool,
    max_filters: int = 5,
    filter_id: str | None = None,
) -> dict[str, Any]:
    _init_db()
    now = now_iso()
    normalized_name = name.strip()
    if not normalized_name:
        raise RuntimeError("Favorite name is required")

    next_filter_id = (filter_id or uuid4().hex).strip()
    if not next_filter_id:
        raise RuntimeError("Filter id is required")

    with _connect() as conn:
        existing = conn.execute(
            """
            SELECT filter_id, created_at
            FROM user_result_filters
            WHERE filter_id = ? AND username = ?
            """,
            (next_filter_id, username),
        ).fetchone()

        if existing is None:
            count_row = conn.execute(
                "SELECT COUNT(*) AS total FROM user_result_filters WHERE username = ?",
                (username,),
            ).fetchone()
            total = int(count_row["total"]) if count_row else 0
            if total >= max_filters:
                raise RuntimeError(f"You can save up to {max_filters} favorite filters")
            created_at = now
            conn.execute(
                """
                INSERT INTO user_result_filters(
                    filter_id, username, name, query_json, is_default, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    next_filter_id,
                    username,
                    normalized_name,
                    json.dumps(query, ensure_ascii=True),
                    1 if is_default else 0,
                    created_at,
                    now,
                ),
            )
        else:
            created_at = str(existing["created_at"])
            conn.execute(
                """
                UPDATE user_result_filters
                SET name = ?, query_json = ?, is_default = ?, updated_at = ?
                WHERE filter_id = ? AND username = ?
                """,
                (
                    normalized_name,
                    json.dumps(query, ensure_ascii=True),
                    1 if is_default else 0,
                    now,
                    next_filter_id,
                    username,
                ),
            )

        if is_default:
            conn.execute(
                """
                UPDATE user_result_filters
                SET is_default = 0
                WHERE username = ? AND filter_id != ?
                """,
                (username, next_filter_id),
            )

        conn.commit()

    return {
        "filter_id": next_filter_id,
        "username": username,
        "name": normalized_name,
        "query": query,
        "is_default": bool(is_default),
        "created_at": created_at,
        "updated_at": now,
    }


def delete_user_result_filter(username: str, filter_id: str) -> bool:
    _init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT is_default FROM user_result_filters WHERE username = ? AND filter_id = ?",
            (username, filter_id),
        ).fetchone()
        if row is None:
            return False

        was_default = bool(int(row["is_default"]))
        conn.execute(
            "DELETE FROM user_result_filters WHERE username = ? AND filter_id = ?",
            (username, filter_id),
        )

        if was_default:
            next_row = conn.execute(
                """
                SELECT filter_id
                FROM user_result_filters
                WHERE username = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (username,),
            ).fetchone()
            if next_row is not None:
                conn.execute(
                    "UPDATE user_result_filters SET is_default = 1 WHERE filter_id = ?",
                    (str(next_row["filter_id"]),),
                )

        conn.commit()
    return True


def count_legacy_ownerless_records() -> dict[str, int]:
    _init_db()
    with _connect() as conn:
        runs_row = conn.execute(
            "SELECT COUNT(*) AS total FROM runs WHERE username IS NULL OR username = ''"
        ).fetchone()
        uploads_row = conn.execute(
            "SELECT COUNT(*) AS total FROM uploads WHERE username IS NULL OR username = ''"
        ).fetchone()

    return {
        "runs": int(runs_row["total"]) if runs_row else 0,
        "uploads": int(uploads_row["total"]) if uploads_row else 0,
    }


def backfill_legacy_ownership(username: str) -> dict[str, int]:
    _init_db()
    owner = username.strip()
    if not owner:
        raise RuntimeError("username is required for backfill")

    migrated_runs = 0
    migrated_uploads = 0

    with _connect() as conn:
        run_rows = conn.execute(
            """
            SELECT run_id, payload_json
            FROM runs
            WHERE username IS NULL OR username = ''
            """
        ).fetchall()
        for row in run_rows:
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict):
                payload = {}
            payload["username"] = owner
            conn.execute(
                """
                UPDATE runs
                SET username = ?, payload_json = ?
                WHERE run_id = ?
                """,
                (owner, json.dumps(payload, ensure_ascii=True), str(row["run_id"])),
            )
            migrated_runs += 1

        upload_rows = conn.execute(
            """
            SELECT upload_id, payload_json
            FROM uploads
            WHERE username IS NULL OR username = ''
            """
        ).fetchall()
        for row in upload_rows:
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict):
                payload = {}
            payload["username"] = owner
            conn.execute(
                """
                UPDATE uploads
                SET username = ?, payload_json = ?
                WHERE upload_id = ?
                """,
                (owner, json.dumps(payload, ensure_ascii=True), str(row["upload_id"])),
            )
            migrated_uploads += 1

        conn.commit()

    return {
        "runs": migrated_runs,
        "uploads": migrated_uploads,
    }
