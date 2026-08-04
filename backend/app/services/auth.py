from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from threading import Lock
from urllib import parse as url_parse
from urllib import request as urllib_request
from uuid import uuid4

from app.config import settings
from app.storage import count_users, delete_session, load_session, load_user, save_session, save_user

SESSION_COOKIE_NAME = "ggs_session"

_oauth_states: dict[str, tuple[str, datetime]] = {}
_oauth_states_lock = Lock()


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return digest.hex()


def has_any_user() -> bool:
    return count_users() > 0


def create_user(username: str, password: str) -> bool:
    username_norm = username.strip()
    if not username_norm:
        return False
    if load_user(username_norm) is not None:
        return False

    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    save_user(username_norm, password_hash, salt)
    return True


def verify_credentials(username: str, password: str) -> bool:
    user = load_user(username.strip())
    if user is None:
        return False

    actual_hash = str(user.get("password_hash", ""))
    salt = str(user.get("salt", ""))
    expected_hash = _hash_password(password, salt)
    return hmac.compare_digest(actual_hash, expected_hash)


def is_google_oauth_available() -> bool:
    return bool(
        settings.google_oauth_enabled
        and settings.google_client_id.strip()
        and settings.google_client_secret.strip()
        and settings.google_redirect_uri.strip()
    )


def _is_allowed_redirect(redirect_url: str) -> bool:
    parsed = url_parse.urlparse(redirect_url)
    if not parsed.scheme or not parsed.netloc:
        return False
    origin = f"{parsed.scheme}://{parsed.netloc}".lower()
    allowed = {item.strip().lower() for item in settings.cors_origins}
    return origin in allowed


def begin_google_oauth(frontend_redirect_url: str) -> str:
    if not is_google_oauth_available():
        raise RuntimeError("Google sign-in is not configured")
    if not _is_allowed_redirect(frontend_redirect_url):
        raise RuntimeError("Redirect URL is not allowed")

    state = secrets.token_urlsafe(24)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.oauth_state_ttl_minutes)
    with _oauth_states_lock:
        _oauth_states[state] = (frontend_redirect_url, expires_at)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + url_parse.urlencode(params)


def _consume_oauth_state(state: str) -> str | None:
    now = datetime.utcnow()
    with _oauth_states_lock:
        record = _oauth_states.pop(state, None)
        if not record:
            return None
        redirect_url, expires_at = record
        if expires_at <= now:
            return None
        return redirect_url


def _http_json(url: str, method: str = "GET", data: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> dict:
    encoded_data = None
    request_headers: dict[str, str] = {"User-Agent": "GrowthGapStrategy/1.0"}
    if headers:
        request_headers.update(headers)

    if data is not None:
        encoded_data = url_parse.urlencode(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    req = urllib_request.Request(url, data=encoded_data, headers=request_headers, method=method)
    with urllib_request.urlopen(req, timeout=15) as response:
        content = response.read().decode("utf-8", errors="ignore")
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise RuntimeError("Invalid response from OAuth provider")
    return payload


def complete_google_oauth(code: str, state: str) -> tuple[str, str]:
    redirect_url = _consume_oauth_state(state)
    if not redirect_url:
        raise RuntimeError("Invalid or expired OAuth state")
    if not is_google_oauth_available():
        raise RuntimeError("Google sign-in is not configured")

    token_payload = _http_json(
        "https://oauth2.googleapis.com/token",
        method="POST",
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
    )

    access_token = str(token_payload.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError("Google token exchange failed")

    profile_payload = _http_json(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    email = str(profile_payload.get("email", "")).strip().lower()
    if not email:
        raise RuntimeError("Google profile email not available")

    if load_user(email) is None:
        # Create a local identity placeholder for OAuth users.
        create_user(email, secrets.token_urlsafe(24))

    return email, redirect_url


def create_session(username: str) -> str:
    token = uuid4().hex
    expires_at = datetime.utcnow() + timedelta(minutes=settings.session_ttl_minutes)
    save_session(token, username, expires_at.isoformat())
    return token


def invalidate_session(token: str) -> None:
    if not token:
        return
    delete_session(token)


def get_session_username(token: str) -> str | None:
    if not token:
        return None

    record = load_session(token)
    if record is None:
        return None

    expires_at_raw = str(record.get("expires_at", "")).strip()
    username = str(record.get("username", "")).strip()
    if not username or not expires_at_raw:
        delete_session(token)
        return None

    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except ValueError:
        delete_session(token)
        return None

    if expires_at <= datetime.utcnow():
        delete_session(token)
        return None

    return username
