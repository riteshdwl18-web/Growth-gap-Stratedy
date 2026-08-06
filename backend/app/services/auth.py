from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from uuid import uuid4

from app.config import settings
from app.storage import (
    cleanup_password_reset_tokens,
    consume_password_reset_token,
    count_users,
    delete_session,
    delete_sessions_for_user,
    load_session,
    load_user,
    save_password_reset_token,
    save_session,
    save_user,
    update_user_password,
)

SESSION_COOKIE_NAME = "ggs_session"
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
LOGGER = logging.getLogger(__name__)


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return digest.hex()


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_smtp_configured() -> bool:
    return bool(
        settings.smtp_host
        and settings.smtp_port > 0
        and settings.smtp_username
        and settings.smtp_password
        and settings.smtp_from_email
    )


def _build_password_reset_link(token: str) -> str:
    base = settings.frontend_base_url.rstrip("/")
    return f"{base}/reset-password?token={token}"


def _send_password_reset_email(recipient_email: str, reset_link: str) -> None:
    if not _is_smtp_configured():
        LOGGER.warning("SMTP is not configured; skipping password reset email delivery")
        return

    message = EmailMessage()
    message["Subject"] = "Reset your Growth Gap Strategy password"
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = recipient_email
    message.set_content(
        "You requested a password reset.\n\n"
        f"Open this link to reset your password: {reset_link}\n\n"
        f"This link expires in {settings.password_reset_ttl_minutes} minutes.\n"
        "If you did not request this reset, you can ignore this email."
    )

    try:
        if settings.smtp_use_tls:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
            return

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.ehlo()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        LOGGER.exception("SMTP authentication failed while sending password reset email")
    except smtplib.SMTPException:
        LOGGER.exception("SMTP error while sending password reset email")


def has_any_user() -> bool:
    return count_users() > 0


def normalize_email(username: str) -> str:
    return username.strip().lower()


def is_valid_email(username: str) -> bool:
    return EMAIL_RE.fullmatch(normalize_email(username)) is not None


def create_user(username: str, password: str) -> bool:
    username_norm = normalize_email(username)
    if not username_norm or not is_valid_email(username_norm):
        return False
    if load_user(username_norm) is not None:
        return False

    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    save_user(username_norm, password_hash, salt)
    return True


def verify_credentials(username: str, password: str) -> bool:
    user = load_user(normalize_email(username))
    if user is None:
        return False

    actual_hash = str(user.get("password_hash", ""))
    salt = str(user.get("salt", ""))
    expected_hash = _hash_password(password, salt)
    return hmac.compare_digest(actual_hash, expected_hash)


def change_password(username: str, current_password: str, new_password: str) -> bool:
    username_norm = normalize_email(username)
    if not username_norm:
        return False
    if not verify_credentials(username_norm, current_password):
        return False

    salt = secrets.token_hex(16)
    password_hash = _hash_password(new_password, salt)
    changed = update_user_password(username_norm, password_hash, salt)
    if changed:
        delete_sessions_for_user(username_norm)
    return changed


def request_password_reset(email: str) -> None:
    email_norm = normalize_email(email)
    if not email_norm or not is_valid_email(email_norm):
        return

    user = load_user(email_norm)
    if user is None:
        return

    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_reset_token(raw_token)
    expires_at = (datetime.utcnow() + timedelta(minutes=settings.password_reset_ttl_minutes)).isoformat()
    save_password_reset_token(token_hash, email_norm, expires_at)
    cleanup_password_reset_tokens()

    reset_link = _build_password_reset_link(raw_token)
    _send_password_reset_email(email_norm, reset_link)


def reset_password_with_token(token: str, new_password: str) -> bool:
    token_clean = token.strip()
    if not token_clean:
        return False

    token_hash = _hash_reset_token(token_clean)
    username = consume_password_reset_token(token_hash)
    if not username:
        return False

    salt = secrets.token_hex(16)
    password_hash = _hash_password(new_password, salt)
    changed = update_user_password(username, password_hash, salt)
    if not changed:
        return False

    delete_sessions_for_user(username)
    return True


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
