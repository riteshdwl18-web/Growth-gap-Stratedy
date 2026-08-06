from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from peewee import (
    AutoField,
    BooleanField,
    CharField,
    FloatField,
    ForeignKeyField,
    IntegrityError,
    IntegerField,
    Model,
    Proxy,
    TextField,
)
from playhouse.db_url import connect

from app.config import settings


RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
RUNS_DIR = RUNTIME_DIR / "runs"
RESULTS_DIR = RUNTIME_DIR / "results"
UPLOADS_DIR = RUNTIME_DIR / "uploads"
EXPORTS_DIR = RUNTIME_DIR / "exports"
LEGACY_SQLITE_PATH = RUNTIME_DIR / "app.db"


for directory in (RUNS_DIR, RESULTS_DIR, UPLOADS_DIR, EXPORTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)


_db_lock = threading.Lock()
_db_initialized = False
_db_proxy = Proxy()
_database = None


class BaseOrmModel(Model):
    class Meta:
        database = _db_proxy


class AppMetaRecord(BaseOrmModel):
    key = CharField(primary_key=True, max_length=120)
    value = TextField()

    class Meta:
        table_name = "app_meta"


class RunRecord(BaseOrmModel):
    run_id = CharField(primary_key=True, max_length=64)
    username = CharField(default="", index=True)
    status = CharField(max_length=40)
    created_at = CharField(max_length=64)
    payload_json = TextField()

    class Meta:
        table_name = "runs"
        indexes = ((("username", "created_at"), False),)


class ResultRecord(BaseOrmModel):
    id = AutoField()
    run = ForeignKeyField(RunRecord, backref="result_rows", column_name="run_id", on_delete="CASCADE")
    row_json = TextField()

    class Meta:
        table_name = "results"
        indexes = ((("run", "id"), False),)


class UploadRecord(BaseOrmModel):
    upload_id = CharField(primary_key=True, max_length=64)
    username = CharField(default="", index=True)
    created_at = CharField(max_length=64)
    valid = BooleanField(default=False)
    payload_json = TextField()

    class Meta:
        table_name = "uploads"
        indexes = ((("username", "created_at"), False),)


class UserRecord(BaseOrmModel):
    username = CharField(primary_key=True, max_length=120)
    password_hash = TextField()
    salt = TextField()
    created_at = CharField(max_length=64)

    class Meta:
        table_name = "users"


class SessionRecord(BaseOrmModel):
    token = CharField(primary_key=True, max_length=64)
    username = CharField(index=True)
    expires_at = CharField(max_length=64, index=True)
    created_at = CharField(max_length=64)

    class Meta:
        table_name = "sessions"


class PasswordResetTokenRecord(BaseOrmModel):
    token_hash = CharField(primary_key=True, max_length=128)
    username = CharField(index=True)
    expires_at = CharField(max_length=64, index=True)
    used_at = CharField(max_length=64, default="", index=True)
    created_at = CharField(max_length=64)

    class Meta:
        table_name = "password_reset_tokens"
        indexes = (
            (("username", "created_at"), False),
            (("username", "used_at"), False),
        )


class LivePriceCacheRecord(BaseOrmModel):
    symbol = CharField(primary_key=True, max_length=40)
    price = FloatField()
    quote_as_of = CharField(max_length=64)
    expires_at = CharField(max_length=64, index=True)
    updated_at = CharField(max_length=64)
    source = CharField(max_length=80)

    class Meta:
        table_name = "live_price_cache"


class UserResultFilterRecord(BaseOrmModel):
    filter_id = CharField(primary_key=True, max_length=64)
    username = CharField(index=True)
    name = CharField(max_length=60)
    query_json = TextField()
    is_default = BooleanField(default=False, index=True)
    created_at = CharField(max_length=64)
    updated_at = CharField(max_length=64)

    class Meta:
        table_name = "user_result_filters"
        indexes = (
            (("username", "name"), True),
            (("username", "is_default"), False),
        )


class TradingJournalEntryRecord(BaseOrmModel):
    entry_id = CharField(primary_key=True, max_length=64)
    username = CharField(index=True)
    trade_date = CharField(max_length=20, index=True)
    session = CharField(max_length=10, index=True)
    script = CharField(max_length=40, index=True)
    trade_strategy = CharField(max_length=80, default="")
    time_period = CharField(max_length=20, default="ShortTerm", index=True)
    side = CharField(max_length=10, index=True)
    quantity = IntegerField(default=0)
    entry_price = FloatField(default=0)
    entry_value = FloatField(default=0)
    exit_quantity = IntegerField(default=0)
    squareoff_date = CharField(max_length=20, default="", index=True)
    exit_price = FloatField(default=0)
    pnl = FloatField(default=0, index=True)
    gain_loss_pct = FloatField(default=0, index=True)
    sl = FloatField(default=0)
    sl_pct = FloatField(default=0)
    tp = FloatField(default=0)
    origination_logic = TextField(default="")
    comment = TextField(default="")
    karma = IntegerField(default=0)
    created_at = CharField(max_length=64)
    updated_at = CharField(max_length=64, index=True)

    class Meta:
        table_name = "trading_journal_entries"
        indexes = (
            (("username", "trade_date"), False),
            (("username", "updated_at"), False),
        )


class TradingJournalLotRecord(BaseOrmModel):
    lot_id = AutoField()
    entry = ForeignKeyField(
        TradingJournalEntryRecord,
        backref="lot_rows",
        column_name="entry_id",
        on_delete="CASCADE",
    )
    lot_date = CharField(max_length=20)
    quantity = IntegerField(default=0)
    price = FloatField(default=0)
    note = TextField(default="")
    created_at = CharField(max_length=64)

    class Meta:
        table_name = "trading_journal_lots"
        indexes = ((("entry", "lot_date"), False),)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _encode_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True)


def _decode_json(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _ensure_database():
    global _database, _db_initialized
    if _db_initialized:
        _ensure_trading_journal_schema()
        return _database

    with _db_lock:
        if _db_initialized:
            _ensure_trading_journal_schema()
            return _database

        database_url = settings.database_url.strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL must be configured for PostgreSQL storage")
        if not database_url.lower().startswith(("postgres://", "postgresql://")):
            raise RuntimeError("DATABASE_URL must use a PostgreSQL scheme")

        _database = connect(database_url)
        _db_proxy.initialize(_database)

        with _database.connection_context():
            _database.create_tables(
                [
                    AppMetaRecord,
                    RunRecord,
                    ResultRecord,
                    UploadRecord,
                    UserRecord,
                    SessionRecord,
                    PasswordResetTokenRecord,
                    LivePriceCacheRecord,
                    UserResultFilterRecord,
                    TradingJournalEntryRecord,
                    TradingJournalLotRecord,
                ],
                safe=True,
            )
            _bootstrap_from_legacy_once()
            _ensure_trading_journal_schema()

        _db_initialized = True
        return _database


def _ensure_trading_journal_schema() -> None:
    if _database is None:
        return

    try:
        columns = [column.name for column in _database.get_columns("trading_journal_entries")]
    except Exception:
        return

    if "exit_quantity" not in columns:
        try:
            _database.execute_sql(
                "ALTER TABLE trading_journal_entries ADD COLUMN exit_quantity INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass

    if "trade_strategy" not in columns:
        try:
            _database.execute_sql(
                "ALTER TABLE trading_journal_entries ADD COLUMN trade_strategy VARCHAR(80) NOT NULL DEFAULT ''"
            )
        except Exception:
            pass

    if "time_period" not in columns:
        try:
            _database.execute_sql(
                "ALTER TABLE trading_journal_entries ADD COLUMN time_period VARCHAR(20) NOT NULL DEFAULT 'ShortTerm'"
            )
        except Exception:
            pass


def _db_context():
    return _ensure_database().connection_context()


def _meta_get(key: str) -> str | None:
    record = AppMetaRecord.get_or_none(AppMetaRecord.key == key)
    if record is None:
        return None
    return record.value


def _meta_set(key: str, value: str) -> None:
    AppMetaRecord.insert(key=key, value=value).on_conflict(
        conflict_target=[AppMetaRecord.key],
        update={AppMetaRecord.value: value},
    ).execute()


def _sqlite_has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _bootstrap_from_legacy_once() -> None:
    if _meta_get("migrated_from_legacy") == "1":
        return

    _migrate_from_legacy_sqlite()
    _migrate_from_json_files_if_needed()
    _meta_set("migrated_from_legacy", "1")


def _migrate_from_legacy_sqlite() -> None:
    if not LEGACY_SQLITE_PATH.exists():
        return

    conn = sqlite3.connect(LEGACY_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if _sqlite_has_table(conn, "app_meta"):
            for row in conn.execute("SELECT key, value FROM app_meta"):
                _meta_set(str(row["key"]), str(row["value"]))

        if _sqlite_has_table(conn, "runs"):
            for row in conn.execute("SELECT run_id, username, status, created_at, payload_json FROM runs"):
                RunRecord.insert(
                    run_id=str(row["run_id"]),
                    username=str(row["username"] or ""),
                    status=str(row["status"] or "queued"),
                    created_at=str(row["created_at"] or now_iso()),
                    payload_json=str(row["payload_json"] or "{}"),
                ).on_conflict(
                    conflict_target=[RunRecord.run_id],
                    update={
                        RunRecord.username: str(row["username"] or ""),
                        RunRecord.status: str(row["status"] or "queued"),
                        RunRecord.created_at: str(row["created_at"] or now_iso()),
                        RunRecord.payload_json: str(row["payload_json"] or "{}"),
                    },
                ).execute()

        if _sqlite_has_table(conn, "results"):
            ResultRecord.delete().execute()
            for row in conn.execute("SELECT run_id, row_json FROM results ORDER BY id ASC"):
                ResultRecord.create(
                    run=str(row["run_id"]),
                    row_json=str(row["row_json"] or "{}"),
                )

        if _sqlite_has_table(conn, "uploads"):
            for row in conn.execute("SELECT upload_id, username, created_at, valid, payload_json FROM uploads"):
                UploadRecord.insert(
                    upload_id=str(row["upload_id"]),
                    username=str(row["username"] or ""),
                    created_at=str(row["created_at"] or now_iso()),
                    valid=bool(int(row["valid"] or 0)),
                    payload_json=str(row["payload_json"] or "{}"),
                ).on_conflict(
                    conflict_target=[UploadRecord.upload_id],
                    update={
                        UploadRecord.username: str(row["username"] or ""),
                        UploadRecord.created_at: str(row["created_at"] or now_iso()),
                        UploadRecord.valid: bool(int(row["valid"] or 0)),
                        UploadRecord.payload_json: str(row["payload_json"] or "{}"),
                    },
                ).execute()

        if _sqlite_has_table(conn, "users"):
            for row in conn.execute("SELECT username, password_hash, salt, created_at FROM users"):
                UserRecord.insert(
                    username=str(row["username"]),
                    password_hash=str(row["password_hash"]),
                    salt=str(row["salt"]),
                    created_at=str(row["created_at"] or now_iso()),
                ).on_conflict(
                    conflict_target=[UserRecord.username],
                    update={
                        UserRecord.password_hash: str(row["password_hash"]),
                        UserRecord.salt: str(row["salt"]),
                        UserRecord.created_at: str(row["created_at"] or now_iso()),
                    },
                ).execute()

        if _sqlite_has_table(conn, "sessions"):
            for row in conn.execute("SELECT token, username, expires_at, created_at FROM sessions"):
                SessionRecord.insert(
                    token=str(row["token"]),
                    username=str(row["username"]),
                    expires_at=str(row["expires_at"]),
                    created_at=str(row["created_at"] or now_iso()),
                ).on_conflict(
                    conflict_target=[SessionRecord.token],
                    update={
                        SessionRecord.username: str(row["username"]),
                        SessionRecord.expires_at: str(row["expires_at"]),
                        SessionRecord.created_at: str(row["created_at"] or now_iso()),
                    },
                ).execute()

        if _sqlite_has_table(conn, "live_price_cache"):
            for row in conn.execute(
                "SELECT symbol, price, quote_as_of, expires_at, updated_at, source FROM live_price_cache"
            ):
                LivePriceCacheRecord.insert(
                    symbol=str(row["symbol"]),
                    price=float(row["price"]),
                    quote_as_of=str(row["quote_as_of"]),
                    expires_at=str(row["expires_at"]),
                    updated_at=str(row["updated_at"] or now_iso()),
                    source=str(row["source"] or "google_finance"),
                ).on_conflict(
                    conflict_target=[LivePriceCacheRecord.symbol],
                    update={
                        LivePriceCacheRecord.price: float(row["price"]),
                        LivePriceCacheRecord.quote_as_of: str(row["quote_as_of"]),
                        LivePriceCacheRecord.expires_at: str(row["expires_at"]),
                        LivePriceCacheRecord.updated_at: str(row["updated_at"] or now_iso()),
                        LivePriceCacheRecord.source: str(row["source"] or "google_finance"),
                    },
                ).execute()

        if _sqlite_has_table(conn, "user_result_filters"):
            for row in conn.execute(
                "SELECT filter_id, username, name, query_json, is_default, created_at, updated_at FROM user_result_filters"
            ):
                UserResultFilterRecord.insert(
                    filter_id=str(row["filter_id"]),
                    username=str(row["username"]),
                    name=str(row["name"]),
                    query_json=str(row["query_json"] or "{}"),
                    is_default=bool(int(row["is_default"] or 0)),
                    created_at=str(row["created_at"] or now_iso()),
                    updated_at=str(row["updated_at"] or now_iso()),
                ).on_conflict(
                    conflict_target=[UserResultFilterRecord.filter_id],
                    update={
                        UserResultFilterRecord.username: str(row["username"]),
                        UserResultFilterRecord.name: str(row["name"]),
                        UserResultFilterRecord.query_json: str(row["query_json"] or "{}"),
                        UserResultFilterRecord.is_default: bool(int(row["is_default"] or 0)),
                        UserResultFilterRecord.created_at: str(row["created_at"] or now_iso()),
                        UserResultFilterRecord.updated_at: str(row["updated_at"] or now_iso()),
                    },
                ).execute()
    finally:
        conn.close()


def _migrate_from_json_files_if_needed() -> None:
    if RunRecord.select().count() == 0:
        for path in RUNS_DIR.glob("*.json"):
            payload = _read_json(path, None)
            if not isinstance(payload, dict):
                continue
            run_id = str(payload.get("run_id") or path.stem)
            save_run(run_id, payload)

    if ResultRecord.select().count() == 0:
        for path in RESULTS_DIR.glob("*.json"):
            rows = _read_json(path, [])
            if not isinstance(rows, list):
                continue
            filtered_rows = [row for row in rows if isinstance(row, dict)]
            save_results(path.stem, filtered_rows)

    if UploadRecord.select().count() == 0:
        for path in UPLOADS_DIR.glob("*.json"):
            payload = _read_json(path, None)
            if not isinstance(payload, dict):
                continue
            upload_id = str(payload.get("upload_id") or path.stem)
            save_upload(upload_id, payload, username=str(payload.get("username", "")))


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
    username = str(payload.get("username", ""))
    status = str(payload.get("status", "queued"))
    created_at = str(payload.get("created_at", now_iso()))
    with _db_context():
        RunRecord.insert(
            run_id=run_id,
            username=username,
            status=status,
            created_at=created_at,
            payload_json=_encode_json(payload),
        ).on_conflict(
            conflict_target=[RunRecord.run_id],
            update={
                RunRecord.username: username,
                RunRecord.status: status,
                RunRecord.created_at: created_at,
                RunRecord.payload_json: _encode_json(payload),
            },
        ).execute()


def load_run(run_id: str) -> dict[str, Any] | None:
    with _db_context():
        record = RunRecord.get_or_none(RunRecord.run_id == run_id)
        if record is None:
            return None
        return _decode_json(record.payload_json, {})


def list_runs_payloads(username: str | None = None) -> list[dict[str, Any]]:
    with _db_context():
        query = RunRecord.select()
        if username is not None:
            query = query.where(RunRecord.username == username)
        return [_decode_json(record.payload_json, {}) for record in query]


def save_results(run_id: str, rows: list[dict[str, Any]]) -> None:
    with _db_context():
        ResultRecord.delete().where(ResultRecord.run == run_id).execute()
        if not rows:
            return
        ResultRecord.insert_many(
            [{"run": run_id, "row_json": _encode_json(row)} for row in rows]
        ).execute()


def load_results(run_id: str) -> list[dict[str, Any]]:
    with _db_context():
        query = ResultRecord.select().where(ResultRecord.run == run_id).order_by(ResultRecord.id.asc())
        return [_decode_json(record.row_json, {}) for record in query]


def append_result(run_id: str, row: dict[str, Any]) -> None:
    with _db_context():
        ResultRecord.create(run=run_id, row_json=_encode_json(row))


def save_upload(upload_id: str, payload: dict[str, Any], username: str) -> None:
    created_at = str(payload.get("created_at", now_iso()))
    valid = bool(payload.get("valid", False))
    with _db_context():
        UploadRecord.insert(
            upload_id=upload_id,
            username=username,
            created_at=created_at,
            valid=valid,
            payload_json=_encode_json(payload),
        ).on_conflict(
            conflict_target=[UploadRecord.upload_id],
            update={
                UploadRecord.username: username,
                UploadRecord.created_at: created_at,
                UploadRecord.valid: valid,
                UploadRecord.payload_json: _encode_json(payload),
            },
        ).execute()


def load_upload(upload_id: str, username: str | None = None) -> dict[str, Any] | None:
    with _db_context():
        query = UploadRecord.select().where(UploadRecord.upload_id == upload_id)
        if username is not None:
            query = query.where(UploadRecord.username == username)
        record = query.get_or_none()
        if record is None:
            return None
        return _decode_json(record.payload_json, {})


def count_users() -> int:
    with _db_context():
        return UserRecord.select().count()


def load_user(username: str) -> dict[str, Any] | None:
    with _db_context():
        record = UserRecord.get_or_none(UserRecord.username == username)
        if record is None:
            return None
        return {
            "username": record.username,
            "password_hash": record.password_hash,
            "salt": record.salt,
            "created_at": record.created_at,
        }


def save_user(username: str, password_hash: str, salt: str) -> None:
    created_at = now_iso()
    with _db_context():
        UserRecord.create(
            username=username,
            password_hash=password_hash,
            salt=salt,
            created_at=created_at,
        )


def update_user_password(username: str, password_hash: str, salt: str) -> bool:
    with _db_context():
        updated = (
            UserRecord.update(password_hash=password_hash, salt=salt)
            .where(UserRecord.username == username)
            .execute()
        )
        return updated > 0


def save_session(token: str, username: str, expires_at: str) -> None:
    created_at = now_iso()
    with _db_context():
        SessionRecord.insert(
            token=token,
            username=username,
            expires_at=expires_at,
            created_at=created_at,
        ).on_conflict(
            conflict_target=[SessionRecord.token],
            update={
                SessionRecord.username: username,
                SessionRecord.expires_at: expires_at,
                SessionRecord.created_at: created_at,
            },
        ).execute()
        SessionRecord.delete().where(SessionRecord.expires_at <= created_at).execute()


def load_session(token: str) -> dict[str, Any] | None:
    with _db_context():
        record = SessionRecord.get_or_none(SessionRecord.token == token)
        if record is None:
            return None
        return {
            "token": record.token,
            "username": record.username,
            "expires_at": record.expires_at,
            "created_at": record.created_at,
        }


def delete_session(token: str) -> None:
    with _db_context():
        SessionRecord.delete().where(SessionRecord.token == token).execute()


def delete_sessions_for_user(username: str) -> None:
    with _db_context():
        SessionRecord.delete().where(SessionRecord.username == username).execute()


def save_password_reset_token(token_hash: str, username: str, expires_at: str) -> None:
    created_at = now_iso()
    with _db_context():
        PasswordResetTokenRecord.insert(
            token_hash=token_hash,
            username=username,
            expires_at=expires_at,
            used_at="",
            created_at=created_at,
        ).on_conflict(
            conflict_target=[PasswordResetTokenRecord.token_hash],
            update={
                PasswordResetTokenRecord.username: username,
                PasswordResetTokenRecord.expires_at: expires_at,
                PasswordResetTokenRecord.used_at: "",
                PasswordResetTokenRecord.created_at: created_at,
            },
        ).execute()


def consume_password_reset_token(token_hash: str) -> str | None:
    now = now_iso()
    with _db_context():
        record = PasswordResetTokenRecord.get_or_none(
            (PasswordResetTokenRecord.token_hash == token_hash)
            & ((PasswordResetTokenRecord.used_at.is_null()) | (PasswordResetTokenRecord.used_at == ""))
            & (PasswordResetTokenRecord.expires_at > now)
        )
        if record is None:
            return None

        updated = (
            PasswordResetTokenRecord.update(used_at=now)
            .where(
                (PasswordResetTokenRecord.token_hash == token_hash)
                & ((PasswordResetTokenRecord.used_at.is_null()) | (PasswordResetTokenRecord.used_at == ""))
            )
            .execute()
        )
        if updated <= 0:
            return None

        return record.username


def cleanup_password_reset_tokens(retain_days: int = 7) -> None:
    if retain_days < 1:
        retain_days = 1
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retain_days)).isoformat()
    now = now_iso()
    with _db_context():
        PasswordResetTokenRecord.delete().where(PasswordResetTokenRecord.expires_at <= now).execute()
        PasswordResetTokenRecord.delete().where(
            (PasswordResetTokenRecord.used_at.is_null(False))
            & (PasswordResetTokenRecord.used_at != "")
            & (PasswordResetTokenRecord.created_at < cutoff)
        ).execute()


def load_live_price_cache(symbols: list[str]) -> dict[str, dict[str, Any]]:
    clean_symbols = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    if not clean_symbols:
        return {}

    with _db_context():
        query = LivePriceCacheRecord.select().where(LivePriceCacheRecord.symbol.in_(clean_symbols))
        return {
            record.symbol: {
                "price": float(record.price),
                "quote_as_of": record.quote_as_of,
                "expires_at": record.expires_at,
                "source": record.source,
            }
            for record in query
        }


def save_live_price_cache(
    quotes: dict[str, float],
    quote_as_of: str,
    expires_at: str,
    source: str = "google_finance",
) -> None:
    if not quotes:
        return

    updated_at = now_iso()
    with _db_context():
        for symbol, price in quotes.items():
            normalized_symbol = symbol.strip().upper()
            if not normalized_symbol:
                continue
            LivePriceCacheRecord.insert(
                symbol=normalized_symbol,
                price=float(price),
                quote_as_of=quote_as_of,
                expires_at=expires_at,
                updated_at=updated_at,
                source=source,
            ).on_conflict(
                conflict_target=[LivePriceCacheRecord.symbol],
                update={
                    LivePriceCacheRecord.price: float(price),
                    LivePriceCacheRecord.quote_as_of: quote_as_of,
                    LivePriceCacheRecord.expires_at: expires_at,
                    LivePriceCacheRecord.updated_at: updated_at,
                    LivePriceCacheRecord.source: source,
                },
            ).execute()
        LivePriceCacheRecord.delete().where(LivePriceCacheRecord.expires_at <= updated_at).execute()


def list_user_result_filters(username: str) -> list[dict[str, Any]]:
    with _db_context():
        query = (
            UserResultFilterRecord.select()
            .where(UserResultFilterRecord.username == username)
            .order_by(UserResultFilterRecord.is_default.desc(), UserResultFilterRecord.updated_at.desc())
        )
        return [
            {
                "filter_id": record.filter_id,
                "username": record.username,
                "name": record.name,
                "query": _decode_json(record.query_json, {}),
                "is_default": bool(record.is_default),
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
            for record in query
        ]


def save_user_result_filter(
    username: str,
    name: str,
    query: dict[str, Any],
    is_default: bool,
    max_filters: int = 5,
    filter_id: str | None = None,
) -> dict[str, Any]:
    now = now_iso()
    normalized_name = name.strip()
    if not normalized_name:
        raise RuntimeError("Favorite name is required")

    next_filter_id = (filter_id or uuid4().hex).strip()
    if not next_filter_id:
        raise RuntimeError("Filter id is required")

    with _db_context():
        existing = UserResultFilterRecord.get_or_none(
            (UserResultFilterRecord.filter_id == next_filter_id)
            & (UserResultFilterRecord.username == username)
        )

        if existing is None:
            total = UserResultFilterRecord.select().where(UserResultFilterRecord.username == username).count()
            if total >= max_filters:
                raise RuntimeError(f"You can save up to {max_filters} favorite filters")
            created_at = now
            record = UserResultFilterRecord(
                filter_id=next_filter_id,
                username=username,
                name=normalized_name,
                query_json=_encode_json(query),
                is_default=bool(is_default),
                created_at=created_at,
                updated_at=now,
            )
        else:
            created_at = existing.created_at
            record = existing
            record.name = normalized_name
            record.query_json = _encode_json(query)
            record.is_default = bool(is_default)
            record.updated_at = now

        try:
            record.save(force_insert=existing is None)
        except IntegrityError as err:
            raise RuntimeError("Favorite filter name already exists") from err

        if is_default:
            (
                UserResultFilterRecord.update(is_default=False)
                .where(
                    (UserResultFilterRecord.username == username)
                    & (UserResultFilterRecord.filter_id != next_filter_id)
                )
                .execute()
            )

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
    with _db_context():
        record = UserResultFilterRecord.get_or_none(
            (UserResultFilterRecord.username == username)
            & (UserResultFilterRecord.filter_id == filter_id)
        )
        if record is None:
            return False

        was_default = bool(record.is_default)
        record.delete_instance()

        if was_default:
            next_record = (
                UserResultFilterRecord.select()
                .where(UserResultFilterRecord.username == username)
                .order_by(UserResultFilterRecord.updated_at.desc())
                .first()
            )
            if next_record is not None:
                next_record.is_default = True
                next_record.save()

        return True


def count_legacy_ownerless_records() -> dict[str, int]:
    with _db_context():
        return {
            "runs": RunRecord.select().where((RunRecord.username.is_null()) | (RunRecord.username == "")).count(),
            "uploads": UploadRecord.select().where((UploadRecord.username.is_null()) | (UploadRecord.username == "")).count(),
        }


def backfill_legacy_ownership(username: str) -> dict[str, int]:
    owner = username.strip()
    if not owner:
        raise RuntimeError("username is required for backfill")

    migrated_runs = 0
    migrated_uploads = 0

    with _db_context():
        for record in RunRecord.select().where((RunRecord.username.is_null()) | (RunRecord.username == "")):
            payload = _decode_json(record.payload_json, {})
            if not isinstance(payload, dict):
                payload = {}
            payload["username"] = owner
            record.username = owner
            record.payload_json = _encode_json(payload)
            record.save()
            migrated_runs += 1

        for record in UploadRecord.select().where((UploadRecord.username.is_null()) | (UploadRecord.username == "")):
            payload = _decode_json(record.payload_json, {})
            if not isinstance(payload, dict):
                payload = {}
            payload["username"] = owner
            record.username = owner
            record.payload_json = _encode_json(payload)
            record.save()
            migrated_uploads += 1

    return {
        "runs": migrated_runs,
        "uploads": migrated_uploads,
    }


def _as_journal_entry_payload(record: TradingJournalEntryRecord) -> dict[str, Any]:
    return {
        "entry_id": record.entry_id,
        "trade_date": record.trade_date,
        "session": record.session,
        "script": record.script,
        "trade_strategy": record.trade_strategy,
        "time_period": record.time_period,
        "side": record.side,
        "quantity": int(record.quantity),
        "entry_price": float(record.entry_price),
        "entry_value": float(record.entry_value),
        "exit_quantity": int(record.exit_quantity),
        "squareoff_date": record.squareoff_date,
        "exit_price": float(record.exit_price),
        "pnl": float(record.pnl),
        "gain_loss_pct": float(record.gain_loss_pct),
        "sl": float(record.sl),
        "sl_pct": float(record.sl_pct),
        "tp": float(record.tp),
        "origination_logic": record.origination_logic,
        "comment": record.comment,
        "karma": int(record.karma),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "lots": _load_trading_journal_lots(str(record.entry_id)),
    }


def _as_journal_lot_payload(record: TradingJournalLotRecord) -> dict[str, Any]:
    return {
        "lot_id": int(record.lot_id),
        "lot_date": record.lot_date,
        "quantity": int(record.quantity),
        "price": float(record.price),
        "note": record.note,
    }


def _normalize_trading_journal_lots(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_lots = payload.get("lots")
    normalized: list[dict[str, Any]] = []

    if isinstance(raw_lots, list):
        for raw in raw_lots:
            if not isinstance(raw, dict):
                continue
            quantity = int(raw.get("quantity", 0))
            price = float(raw.get("price", 0))
            if quantity <= 0:
                continue
            normalized.append(
                {
                    "lot_date": str(raw.get("lot_date", payload.get("trade_date", ""))).strip(),
                    "quantity": quantity,
                    "price": price,
                    "note": str(raw.get("note", "")).strip(),
                }
            )

    if normalized:
        return normalized

    quantity = int(payload.get("quantity", 0))
    price = float(payload.get("entry_price", 0))
    if quantity <= 0:
        return []

    return [
        {
            "lot_date": str(payload.get("trade_date", "")).strip(),
            "quantity": quantity,
            "price": price,
            "note": "",
        }
    ]


def _normalize_exit_quantity(payload: dict[str, Any]) -> int:
    try:
        return max(0, int(payload.get("exit_quantity", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _summarize_trading_journal_lots(payload: dict[str, Any]) -> dict[str, float | int]:
    lots = _normalize_trading_journal_lots(payload)
    total_quantity = sum(int(lot["quantity"]) for lot in lots)
    total_entry_value = sum(float(lot["quantity"]) * float(lot["price"]) for lot in lots)
    avg_entry_price = (total_entry_value / total_quantity) if total_quantity > 0 else 0.0
    exit_quantity = min(_normalize_exit_quantity(payload), total_quantity)
    exit_price = float(payload.get("exit_price", 0) or 0)
    pnl = float(payload.get("pnl", 0) or 0)
    gain_loss_pct = float(payload.get("gain_loss_pct", 0) or 0)
    realized_pnl = 0.0
    remaining_quantity = max(total_quantity - exit_quantity, 0)

    if exit_price > 0 and exit_quantity > 0 and total_quantity > 0 and avg_entry_price > 0:
        side = str(payload.get("side", "Buy")).strip().lower()
        pnl_per_unit = (avg_entry_price - exit_price) if side == "sell" else (exit_price - avg_entry_price)
        realized_pnl = round(pnl_per_unit * exit_quantity, 2)
        pnl = round(realized_pnl, 2)
        gain_loss_pct = round((pnl / total_entry_value) * 100, 2) if total_entry_value > 0 else 0.0

    return {
        "quantity": total_quantity,
        "entry_price": round(avg_entry_price, 2),
        "entry_value": round(total_entry_value, 2),
        "exit_quantity": exit_quantity,
        "pnl": round(pnl, 2),
        "gain_loss_pct": round(gain_loss_pct, 2),
        "realized_pnl": round(realized_pnl, 2),
        "open_quantity": remaining_quantity,
    }


def _save_trading_journal_lots(entry_id: str, lots: list[dict[str, Any]], created_at: str) -> None:
    TradingJournalLotRecord.delete().where(TradingJournalLotRecord.entry == entry_id).execute()
    if not lots:
        return

    TradingJournalLotRecord.insert_many(
        [
            {
                "entry": entry_id,
                "lot_date": str(lot.get("lot_date", "")).strip(),
                "quantity": int(lot.get("quantity", 0)),
                "price": float(lot.get("price", 0)),
                "note": str(lot.get("note", "")).strip(),
                "created_at": created_at,
            }
            for lot in lots
            if int(lot.get("quantity", 0)) > 0
        ]
    ).execute()


def _load_trading_journal_lots(entry_id: str) -> list[dict[str, Any]]:
    with _db_context():
        query = TradingJournalLotRecord.select().where(TradingJournalLotRecord.entry == entry_id).order_by(TradingJournalLotRecord.lot_id.asc())
        return [_as_journal_lot_payload(record) for record in query]


def _load_trading_journal_lots_map(entry_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    clean_entry_ids = [str(entry_id).strip() for entry_id in entry_ids if str(entry_id).strip()]
    if not clean_entry_ids:
        return {}

    with _db_context():
        query = (
            TradingJournalLotRecord.select()
            .where(TradingJournalLotRecord.entry.in_(clean_entry_ids))
            .order_by(TradingJournalLotRecord.entry_id.asc(), TradingJournalLotRecord.lot_id.asc())
        )
        grouped: dict[str, list[dict[str, Any]]] = {entry_id: [] for entry_id in clean_entry_ids}
        for record in query:
            grouped.setdefault(str(record.entry_id), []).append(_as_journal_lot_payload(record))
        return grouped


def create_trading_journal_entry(username: str, payload: dict[str, Any]) -> dict[str, Any]:
    now = now_iso()
    entry_id = uuid4().hex
    script = str(payload.get("script", "")).strip().upper()
    lots = _normalize_trading_journal_lots(payload)
    summary = _summarize_trading_journal_lots(payload)
    with _db_context():
        record = TradingJournalEntryRecord.create(
            entry_id=entry_id,
            username=username,
            trade_date=str(payload.get("trade_date", "")).strip(),
            session=str(payload.get("session", "Open")).strip(),
            script=script,
            trade_strategy=str(payload.get("trade_strategy", "")).strip(),
            time_period=str(payload.get("time_period", "ShortTerm")).strip() or "ShortTerm",
            side=str(payload.get("side", "Buy")).strip(),
            quantity=int(summary["quantity"]),
            entry_price=float(summary["entry_price"]),
            entry_value=float(summary["entry_value"]),
            squareoff_date=str(payload.get("squareoff_date", "")).strip(),
            exit_price=float(payload.get("exit_price", 0)),
            pnl=float(summary["pnl"]),
            gain_loss_pct=float(summary["gain_loss_pct"]),
            sl=float(payload.get("sl", 0)),
            sl_pct=float(payload.get("sl_pct", 0)),
            tp=float(payload.get("tp", 0)),
            origination_logic=str(payload.get("origination_logic", "")).strip(),
            comment=str(payload.get("comment", "")).strip(),
            karma=int(payload.get("karma", 0)),
            created_at=now,
            updated_at=now,
        )
        _save_trading_journal_lots(entry_id, lots, now)
        return _as_journal_entry_payload(record)


def update_trading_journal_entry(username: str, entry_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    now = now_iso()
    lots = _normalize_trading_journal_lots(payload)
    summary = _summarize_trading_journal_lots(payload)
    with _db_context():
        record = TradingJournalEntryRecord.get_or_none(
            (TradingJournalEntryRecord.username == username)
            & (TradingJournalEntryRecord.entry_id == entry_id)
        )
        if record is None:
            return None

        record.trade_date = str(payload.get("trade_date", "")).strip()
        record.session = str(payload.get("session", "Open")).strip()
        record.script = str(payload.get("script", "")).strip().upper()
        record.trade_strategy = str(payload.get("trade_strategy", "")).strip()
        record.time_period = str(payload.get("time_period", "ShortTerm")).strip() or "ShortTerm"
        record.side = str(payload.get("side", "Buy")).strip()
        record.quantity = int(summary["quantity"])
        record.entry_price = float(summary["entry_price"])
        record.entry_value = float(summary["entry_value"])
        record.exit_quantity = int(summary["exit_quantity"])
        record.squareoff_date = str(payload.get("squareoff_date", "")).strip()
        record.exit_price = float(payload.get("exit_price", 0))
        record.pnl = float(summary["pnl"])
        record.gain_loss_pct = float(summary["gain_loss_pct"])
        record.sl = float(payload.get("sl", 0))
        record.sl_pct = float(payload.get("sl_pct", 0))
        record.tp = float(payload.get("tp", 0))
        record.origination_logic = str(payload.get("origination_logic", "")).strip()
        record.comment = str(payload.get("comment", "")).strip()
        record.karma = int(payload.get("karma", 0))
        record.updated_at = now
        record.save()
        _save_trading_journal_lots(entry_id, lots, now)
        return _as_journal_entry_payload(record)


def delete_trading_journal_entry(username: str, entry_id: str) -> bool:
    with _db_context():
        deleted = (
            TradingJournalEntryRecord.delete()
            .where(
                (TradingJournalEntryRecord.username == username)
                & (TradingJournalEntryRecord.entry_id == entry_id)
            )
            .execute()
        )
        return bool(deleted)


def list_trading_journal_entries(
    username: str,
    search: str = "",
    session: str = "all",
    trade_strategy: str = "all",
    time_period: str = "all",
    sort_by: str = "trade_date",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[dict[str, Any]], int]:
    with _db_context():
        query = TradingJournalEntryRecord.select().where(TradingJournalEntryRecord.username == username)

        search_clean = search.strip().lower()
        if search_clean:
            query = query.where(
                (TradingJournalEntryRecord.script.contains(search_clean))
                | (TradingJournalEntryRecord.trade_strategy.contains(search_clean))
                | (TradingJournalEntryRecord.time_period.contains(search_clean))
                | (TradingJournalEntryRecord.origination_logic.contains(search_clean))
                | (TradingJournalEntryRecord.comment.contains(search_clean))
            )

        session_clean = session.strip().lower()
        if session_clean in {"open", "close"}:
            query = query.where(TradingJournalEntryRecord.session == session_clean.capitalize())

        strategy_clean = trade_strategy.strip()
        if strategy_clean in {"RS55", "Growth-Gap", "Range-Bound"}:
            query = query.where(TradingJournalEntryRecord.trade_strategy == strategy_clean)
        elif strategy_clean.lower() == "other":
            query = query.where(
                (TradingJournalEntryRecord.trade_strategy != "")
                & (~(TradingJournalEntryRecord.trade_strategy.in_(["RS55", "Growth-Gap", "Range-Bound"])))
            )

        period_clean = time_period.strip()
        if period_clean in {"ShortTerm", "LongTerm"}:
            query = query.where(TradingJournalEntryRecord.time_period == period_clean)

        total = query.count()

        sort_map = {
            "trade_date": TradingJournalEntryRecord.trade_date,
            "squareoff_date": TradingJournalEntryRecord.squareoff_date,
            "script": TradingJournalEntryRecord.script,
            "trade_strategy": TradingJournalEntryRecord.trade_strategy,
            "time_period": TradingJournalEntryRecord.time_period,
            "side": TradingJournalEntryRecord.side,
            "quantity": TradingJournalEntryRecord.quantity,
            "entry_price": TradingJournalEntryRecord.entry_price,
            "exit_price": TradingJournalEntryRecord.exit_price,
            "pnl": TradingJournalEntryRecord.pnl,
            "gain_loss_pct": TradingJournalEntryRecord.gain_loss_pct,
            "karma": TradingJournalEntryRecord.karma,
            "updated_at": TradingJournalEntryRecord.updated_at,
        }
        sort_field = sort_map.get(sort_by, TradingJournalEntryRecord.trade_date)
        ordered = sort_field.desc() if sort_order.strip().lower() == "desc" else sort_field.asc()

        items = query.order_by(ordered).paginate(page, page_size)
        item_list = list(items)
        lot_map = _load_trading_journal_lots_map([item.entry_id for item in item_list])
        return (
            [_as_journal_entry_payload(item) | {"lots": lot_map.get(str(item.entry_id), [])} for item in item_list],
            total,
        )
