from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.models import ALLOWED_INPUT_HEADERS, UploadValidationResponse
from app.storage import load_upload, now_iso, save_upload


@dataclass
class UploadedDataset:
    upload_id: str
    username: str
    filename: str
    created_at: datetime
    rows: list[dict[str, str]]


# In-memory store for MVP; replace with database/object storage in production.
UPLOADED_DATASETS: dict[str, UploadedDataset] = {}


def get_uploaded_dataset(upload_id: str, username: str | None = None) -> UploadedDataset | None:
    in_memory = UPLOADED_DATASETS.get(upload_id)
    if in_memory is not None and (username is None or in_memory.username == username):
        return in_memory

    payload = load_upload(upload_id, username=username)
    if not payload:
        return None

    created_at = datetime.fromisoformat(payload.get("created_at", now_iso()))
    return UploadedDataset(
        upload_id=upload_id,
        username=str(payload.get("username", "")),
        filename=str(payload.get("filename", "upload.csv")),
        created_at=created_at,
        rows=list(payload.get("rows") or []),
    )


def get_upload_payload(upload_id: str, username: str | None = None) -> dict | None:
    payload = load_upload(upload_id, username=username)
    if not payload:
        return None
    return payload


def validate_and_store_upload(filename: str, content: bytes, username: str) -> UploadValidationResponse:
    if not content:
        return UploadValidationResponse(
            filename=filename,
            valid=False,
            allowed_headers=ALLOWED_INPUT_HEADERS,
            detected_headers=[],
            errors=["Uploaded file is empty."],
        )

    decoded_text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(decoded_text))

    if not reader.fieldnames:
        return UploadValidationResponse(
            filename=filename,
            valid=False,
            allowed_headers=ALLOWED_INPUT_HEADERS,
            detected_headers=[],
            errors=["Could not detect CSV headers."],
        )

    detected_headers = [str(h).strip() for h in reader.fieldnames if h is not None]
    missing_headers = [h for h in ALLOWED_INPUT_HEADERS if h not in detected_headers]
    unexpected_headers = [h for h in detected_headers if h not in ALLOWED_INPUT_HEADERS]

    if missing_headers or unexpected_headers:
        return UploadValidationResponse(
            filename=filename,
            valid=False,
            allowed_headers=ALLOWED_INPUT_HEADERS,
            detected_headers=detected_headers,
            missing_headers=missing_headers,
            unexpected_headers=unexpected_headers,
            errors=["Header mismatch. Only the allowed headers are accepted."],
        )

    accepted_rows: list[dict[str, str]] = []
    rejected_rows = 0
    total_rows = 0

    for raw_row in reader:
        if raw_row is None:
            continue

        total_rows += 1
        normalized = {
            header: str(raw_row.get(header, "") or "").strip()
            for header in ALLOWED_INPUT_HEADERS
        }

        if not any(normalized.values()):
            # Ignore fully blank lines so row counters remain practical.
            total_rows -= 1
            continue

        if not normalized["NSE Code"]:
            rejected_rows += 1
            continue

        accepted_rows.append(normalized)

    upload_id = str(uuid4())
    UPLOADED_DATASETS[upload_id] = UploadedDataset(
        upload_id=upload_id,
        username=username,
        filename=filename,
        created_at=datetime.utcnow(),
        rows=accepted_rows,
    )
    save_upload(
        upload_id,
        {
            "upload_id": upload_id,
            "username": username,
            "filename": filename,
            "created_at": now_iso(),
            "valid": True,
            "total_rows": total_rows,
            "accepted_rows": len(accepted_rows),
            "rejected_rows": rejected_rows,
            "allowed_headers": ALLOWED_INPUT_HEADERS,
            "detected_headers": detected_headers,
            "rows": accepted_rows,
        },
        username=username,
    )

    return UploadValidationResponse(
        upload_id=upload_id,
        filename=filename,
        valid=True,
        allowed_headers=ALLOWED_INPUT_HEADERS,
        detected_headers=detected_headers,
        total_rows=total_rows,
        accepted_rows=len(accepted_rows),
        rejected_rows=rejected_rows,
        preview_rows=accepted_rows[:5],
    )
