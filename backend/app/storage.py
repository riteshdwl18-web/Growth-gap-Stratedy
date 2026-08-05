from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
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
        return _database

    with _db_lock:
        if _db_initialized:
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
                    LivePriceCacheRecord,
                    UserResultFilterRecord,
                ],
                safe=True,
            )
            _bootstrap_from_legacy_once()

        _db_initialized = True
        return _database


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
