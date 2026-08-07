from datetime import datetime, timezone
import csv
import io

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.config import settings
from app.models import (
    AuthStatusResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    HealthResponse,
    JournalSortBy,
    LivePriceQuoteResponse,
    LoginRequest,
    ResultFilterQuery,
    RunCreateRequest,
    RunListResponse,
    RunResultSortBy,
    RunResultsPageResponse,
    RunSortBy,
    RunSortOrder,
    RunSummary,
    UploadStatusResponse,
    UploadWorkflowRunRequest,
    UploadRunCreateRequest,
    UploadValidationResponse,
    SignupRequest,
    TradingJournalEntryListResponse,
    TradingJournalEntryResponse,
    TradingJournalEntryUpsertRequest,
    TradingJournalLotResponse,
    UserResultFilterListResponse,
    MessageResponse,
    ResetPasswordRequest,
    UserResultFilterResponse,
    UserResultFilterUpsertRequest,
)
from app.services.auth import (
    SESSION_COOKIE_NAME,
    change_password,
    create_user,
    create_session,
    get_session_username,
    has_any_user,
    invalidate_session,
    is_valid_email,
    normalize_email,
    request_password_reset,
    reset_password_with_token,
    verify_credentials,
)
from app.services.screener import (
    build_results_csv_payload,
    create_run,
    create_run_from_upload,
    create_retry_run_from_failed,
    generate_run_csv,
    get_run,
    get_run_results,
    get_live_price_quote,
    get_live_price_quotes,
    list_run_industry_groups,
    list_runs,
    query_run_results,
    query_runs,
    stop_run,
)
from app.services.uploads import (
    get_upload_payload,
    get_uploaded_dataset,
    validate_and_store_upload,
)
from app.storage import (
    backfill_legacy_ownership,
    create_trading_journal_entry,
    count_legacy_ownerless_records,
    delete_trading_journal_entry,
    list_trading_journal_entries,
    delete_user_result_filter,
    list_user_result_filters,
    save_user_result_filter,
    update_trading_journal_entry,
)


app = FastAPI(title=settings.app_name, version=settings.app_version)

MAX_USER_RESULT_FILTERS = 5


def _to_local_datetime(value: object) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now().astimezone()

    # Accept ISO timestamps that end with UTC "Z".
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now().astimezone()

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone()


def _cookie_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {
        "httponly": True,
        "samesite": settings.session_cookie_samesite,
        "secure": settings.session_cookie_secure,
        "max_age": settings.session_ttl_minutes * 60,
        "path": "/",
    }
    if settings.session_cookie_domain:
        kwargs["domain"] = settings.session_cookie_domain
    return kwargs

def _auth_username(request: Request) -> str:
    username = str(getattr(request.state, "auth_username", "")).strip()
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return username

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)

    if path.startswith("/api/auth/") or path == "/health":
        return await call_next(request)

    if not path.startswith("/api/"):
        return await call_next(request)

    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    username = get_session_username(token)
    if not username:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    request.state.auth_username = username
    return await call_next(request)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.utcnow())


@app.post("/api/auth/login", response_model=AuthStatusResponse)
def login(payload: LoginRequest, response: Response) -> AuthStatusResponse:
    if not has_any_user():
        raise HTTPException(status_code=409, detail="No account found. Please sign up first.")

    email = normalize_email(payload.email)
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Email is invalid")
    if not verify_credentials(email, payload.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_session(email)
    response.set_cookie(key=SESSION_COOKIE_NAME, value=token, **_cookie_kwargs())
    return AuthStatusResponse(
        authenticated=True,
        email=email,
        username=email,
        signup_required=False,
    )


@app.post("/api/auth/signup", response_model=AuthStatusResponse)
def signup(payload: SignupRequest, response: Response) -> AuthStatusResponse:
    email = normalize_email(payload.email)
    password = payload.password
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Email is invalid")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    created = create_user(email, password)
    if not created:
        raise HTTPException(status_code=409, detail="Email already exists")

    token = create_session(email)
    response.set_cookie(key=SESSION_COOKIE_NAME, value=token, **_cookie_kwargs())
    return AuthStatusResponse(
        authenticated=True,
        email=email,
        username=email,
        signup_required=False,
    )


@app.post("/api/auth/logout", response_model=AuthStatusResponse)
def logout(request: Request, response: Response) -> AuthStatusResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    invalidate_session(token)
    delete_kwargs: dict[str, object] = {
        "key": SESSION_COOKIE_NAME,
        "path": "/",
        "samesite": settings.session_cookie_samesite,
        "secure": settings.session_cookie_secure,
    }
    if settings.session_cookie_domain:
        delete_kwargs["domain"] = settings.session_cookie_domain
    response.delete_cookie(**delete_kwargs)
    return AuthStatusResponse(
        authenticated=False,
        email=None,
        username=None,
        signup_required=not has_any_user(),
    )


@app.get("/api/auth/me", response_model=AuthStatusResponse)
def me(request: Request) -> AuthStatusResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    email = get_session_username(token)
    if not email:
        return AuthStatusResponse(
            authenticated=False,
            email=None,
            username=None,
            signup_required=not has_any_user(),
        )
    return AuthStatusResponse(
        authenticated=True,
        email=email,
        username=email,
        signup_required=False,
    )


@app.post("/api/auth/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest) -> MessageResponse:
    # Do not leak account existence.
    if is_valid_email(payload.email):
        request_password_reset(payload.email)
    return MessageResponse(message="If the account exists, a reset link has been sent.")


@app.post("/api/auth/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest) -> MessageResponse:
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    updated = reset_password_with_token(payload.token, payload.new_password)
    if not updated:
        raise HTTPException(status_code=400, detail="Reset token is invalid or expired")
    return MessageResponse(message="Password reset successful. Please login again.")


@app.post("/api/auth/change-password", response_model=MessageResponse)
def change_password_endpoint(payload: ChangePasswordRequest, request: Request) -> MessageResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    username = get_session_username(token)
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    updated = change_password(username, payload.current_password, payload.new_password)
    if not updated:
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    return MessageResponse(message="Password updated successfully")


@app.post("/api/runs", response_model=RunSummary)
def start_run(payload: RunCreateRequest, request: Request) -> RunSummary:
    username = _auth_username(request)
    try:
        return create_run(payload, username=username)
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


@app.get("/api/runs", response_model=RunListResponse)
def fetch_runs(
    request: Request,
    search: str = Query(default="", max_length=200),
    status: str = Query(default="all", max_length=30),
    created_from: str = Query(default="", max_length=30),
    created_to: str = Query(default="", max_length=30),
    sort_by: RunSortBy = Query(default="created_at"),
    sort_order: RunSortOrder = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> RunListResponse:
    username = _auth_username(request)
    items, total = list_runs(
        username=username,
        search=search,
        status=status,
        created_from=created_from,
        created_to=created_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return RunListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@app.get("/api/runs/export.csv")
def export_runs_csv(
    request: Request,
    search: str = Query(default="", max_length=200),
    status: str = Query(default="all", max_length=30),
    created_from: str = Query(default="", max_length=30),
    created_to: str = Query(default="", max_length=30),
    sort_by: RunSortBy = Query(default="created_at"),
    sort_order: RunSortOrder = Query(default="desc"),
) -> StreamingResponse:
    username = _auth_username(request)
    runs = query_runs(
        username=username,
        search=search,
        status=status,
        created_from=created_from,
        created_to=created_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=[
            "Run ID",
            "Status",
            "Created At",
            "Stopped At",
            "Input Universe",
            "Output Mode",
            "Refresh",
            "Processed",
            "Total",
            "PASS Count",
            "FAIL Count",
            "Skipped Count",
        ],
    )
    writer.writeheader()
    for run in runs:
        writer.writerow(
            {
                "Run ID": run.run_id,
                "Status": run.status,
                "Created At": run.created_at.isoformat(),
                "Stopped At": run.stopped_at.isoformat() if run.stopped_at else "",
                "Input Universe": run.input_universe,
                "Output Mode": run.output_mode,
                "Refresh": run.refresh,
                "Processed": run.processed,
                "Total": run.total,
                "PASS Count": run.pass_count,
                "FAIL Count": run.fail_count,
                "Skipped Count": run.skipped_count,
            }
        )

    output = io.BytesIO(csv_buffer.getvalue().encode("utf-8"))
    headers = {"Content-Disposition": "attachment; filename=filtered_runs.csv"}
    return StreamingResponse(output, media_type="text/csv", headers=headers)


@app.get("/api/runs/{run_id}", response_model=RunSummary)
def fetch_run(run_id: str, request: Request) -> RunSummary:
    username = _auth_username(request)
    run = get_run(run_id, username=username)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/runs/{run_id}/stop", response_model=RunSummary)
def stop_existing_run(run_id: str, request: Request) -> RunSummary:
    username = _auth_username(request)
    run = stop_run(run_id, username=username)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/runs/{run_id}/retry-failed", response_model=RunSummary)
def retry_failed_rows(run_id: str, request: Request) -> RunSummary:
    username = _auth_username(request)
    try:
        return create_retry_run_from_failed(source_run_id=run_id, username=username)
    except RuntimeError as err:
        message = str(err)
        if message == "Source run not found":
            raise HTTPException(status_code=404, detail=message) from err
        raise HTTPException(status_code=409, detail=message) from err


@app.get("/api/runs/{run_id}/download.csv")
def download_run_csv(run_id: str, request: Request) -> FileResponse:
    username = _auth_username(request)
    run = get_run(run_id, username=username)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in {"completed", "partial_completed"}:
        raise HTTPException(status_code=409, detail="CSV is available only for completed or partial completed runs")

    csv_path = generate_run_csv(run_id, username=username)
    if csv_path is None:
        raise HTTPException(status_code=404, detail="CSV generation failed")

    return FileResponse(
        path=str(csv_path),
        media_type="text/csv",
        filename=f"growth_gap_results_{run_id}.csv",
    )


@app.get("/api/runs/{run_id}/results", response_model=RunResultsPageResponse)
def fetch_run_results(
    request: Request,
    run_id: str,
    search: str = Query(default="", max_length=200),
    final_status: str = Query(default="all", max_length=30),
    market_cap_min: str = Query(default="", max_length=30),
    market_cap_max: str = Query(default="", max_length=30),
    industry_group: str = Query(default="", max_length=120),
    total_2y_growth_min: str = Query(default="", max_length=30),
    total_2y_growth_max: str = Query(default="", max_length=30),
    ttm_vs_end_fy_min: str = Query(default="", max_length=30),
    ttm_vs_end_fy_max: str = Query(default="", max_length=30),
    combined_growth_min: str = Query(default="", max_length=30),
    combined_growth_max: str = Query(default="", max_length=30),
    roce_min: str = Query(default="", max_length=30),
    roce_max: str = Query(default="", max_length=30),
    away_min: str = Query(default="", max_length=30),
    away_max: str = Query(default="", max_length=30),
    live_price: bool = Query(default=False),
    sort_by: RunResultSortBy = Query(default="name"),
    sort_order: RunSortOrder = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> RunResultsPageResponse:
    username = _auth_username(request)
    results = get_run_results(
        username=username,
        run_id=run_id,
        search=search,
        final_status=final_status,
        market_cap_min=market_cap_min,
        market_cap_max=market_cap_max,
        industry_group=industry_group,
        total_2y_growth_min=total_2y_growth_min,
        total_2y_growth_max=total_2y_growth_max,
        ttm_vs_end_fy_min=ttm_vs_end_fy_min,
        ttm_vs_end_fy_max=ttm_vs_end_fy_max,
        combined_growth_min=combined_growth_min,
        combined_growth_max=combined_growth_max,
        roce_min=roce_min,
        roce_max=roce_max,
        away_min=away_min,
        away_max=away_max,
        live_price=live_price,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    if results is None:
        raise HTTPException(status_code=404, detail="Run not found")
    items, total = results
    total_pages = max(1, (total + page_size - 1) // page_size)
    return RunResultsPageResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@app.get("/api/market/quote", response_model=LivePriceQuoteResponse)
def fetch_market_quote(
    request: Request,
    symbol: str = Query(..., min_length=1, max_length=40),
    refresh: bool = Query(default=True),
) -> LivePriceQuoteResponse:
    _auth_username(request)
    quote = get_live_price_quote(symbol=symbol, force_refresh=refresh)
    return LivePriceQuoteResponse(**quote)


@app.get("/api/runs/{run_id}/industry-groups", response_model=list[str])
def fetch_run_industry_groups(run_id: str, request: Request) -> list[str]:
    username = _auth_username(request)
    groups = list_run_industry_groups(run_id, username=username)
    if groups is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return groups


@app.get("/api/runs/{run_id}/results/export.csv")
def export_run_results_csv(
    request: Request,
    run_id: str,
    search: str = Query(default="", max_length=200),
    final_status: str = Query(default="all", max_length=30),
    market_cap_min: str = Query(default="", max_length=30),
    market_cap_max: str = Query(default="", max_length=30),
    industry_group: str = Query(default="", max_length=120),
    total_2y_growth_min: str = Query(default="", max_length=30),
    total_2y_growth_max: str = Query(default="", max_length=30),
    ttm_vs_end_fy_min: str = Query(default="", max_length=30),
    ttm_vs_end_fy_max: str = Query(default="", max_length=30),
    combined_growth_min: str = Query(default="", max_length=30),
    combined_growth_max: str = Query(default="", max_length=30),
    roce_min: str = Query(default="", max_length=30),
    roce_max: str = Query(default="", max_length=30),
    away_min: str = Query(default="", max_length=30),
    away_max: str = Query(default="", max_length=30),
    live_price: bool = Query(default=False),
    sort_by: RunResultSortBy = Query(default="name"),
    sort_order: RunSortOrder = Query(default="asc"),
) -> StreamingResponse:
    username = _auth_username(request)
    rows = query_run_results(
        username=username,
        run_id=run_id,
        search=search,
        final_status=final_status,
        market_cap_min=market_cap_min,
        market_cap_max=market_cap_max,
        industry_group=industry_group,
        total_2y_growth_min=total_2y_growth_min,
        total_2y_growth_max=total_2y_growth_max,
        ttm_vs_end_fy_min=ttm_vs_end_fy_min,
        ttm_vs_end_fy_max=ttm_vs_end_fy_max,
        combined_growth_min=combined_growth_min,
        combined_growth_max=combined_growth_max,
        roce_min=roce_min,
        roce_max=roce_max,
        away_min=away_min,
        away_max=away_max,
        live_price=live_price,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    if rows is None:
        raise HTTPException(status_code=404, detail="Run not found")

    fieldnames, csv_rows = build_results_csv_payload(rows)

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in csv_rows:
        writer.writerow(row)

    output = io.BytesIO(csv_buffer.getvalue().encode("utf-8"))
    headers = {"Content-Disposition": f"attachment; filename=run_{run_id}_filtered_results.csv"}
    return StreamingResponse(output, media_type="text/csv", headers=headers)


@app.post("/api/uploads/validate", response_model=UploadValidationResponse)
async def validate_upload(request: Request, file: UploadFile = File(...)) -> UploadValidationResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    content = await file.read()
    return validate_and_store_upload(file.filename, content, username=_auth_username(request))


@app.post("/api/runs/from-upload/{upload_id}", response_model=RunSummary)
def start_run_from_upload(upload_id: str, payload: UploadRunCreateRequest, request: Request) -> RunSummary:
    username = _auth_username(request)
    dataset = get_uploaded_dataset(upload_id, username=username)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Upload not found. Validate file again.")

    try:
        return create_run_from_upload(
            upload_id=upload_id,
            filename=dataset.filename,
            total_rows=len(dataset.rows),
            payload=payload,
            username=username,
        )
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


@app.get("/api/uploads/{upload_id}/status", response_model=UploadStatusResponse)
def fetch_upload_status(upload_id: str, request: Request) -> UploadStatusResponse:
    payload = get_upload_payload(upload_id, username=_auth_username(request))
    if payload is None:
        raise HTTPException(status_code=404, detail="Upload not found. Validate file again.")

    return UploadStatusResponse(
        upload_id=str(payload.get("upload_id", upload_id)),
        filename=str(payload.get("filename", "upload.csv")),
        created_at=_to_local_datetime(payload.get("created_at", datetime.utcnow().isoformat())),
        valid=bool(payload.get("valid", False)),
        total_rows=int(payload.get("total_rows", 0)),
        accepted_rows=int(payload.get("accepted_rows", 0)),
        rejected_rows=int(payload.get("rejected_rows", 0)),
    )


@app.post("/api/workflows/upload-run", response_model=RunSummary)
def start_workflow_run(payload: UploadWorkflowRunRequest, request: Request) -> RunSummary:
    if not payload.confirm_run:
        raise HTTPException(status_code=400, detail="confirm_run must be true to start workflow run")

    username = _auth_username(request)
    upload_payload = get_upload_payload(payload.upload_id, username=username)
    if upload_payload is None:
        raise HTTPException(status_code=404, detail="Upload not found. Validate file again.")
    if not bool(upload_payload.get("valid", False)):
        raise HTTPException(status_code=400, detail="Upload is not valid for workflow execution.")

    dataset = get_uploaded_dataset(payload.upload_id, username=username)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Upload data unavailable. Validate file again.")
    if len(dataset.rows) == 0:
        raise HTTPException(status_code=400, detail="Validated upload has no accepted rows to process.")

    try:
        return create_run_from_upload(
            upload_id=payload.upload_id,
            filename=dataset.filename,
            total_rows=len(dataset.rows),
            payload=UploadRunCreateRequest(
                output_mode=payload.output_mode,
                refresh=payload.refresh,
            ),
            username=username,
        )
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err


def _to_user_result_filter_response(item: dict) -> UserResultFilterResponse:
    return UserResultFilterResponse(
        filter_id=str(item.get("filter_id", "")),
        name=str(item.get("name", "")),
        query=ResultFilterQuery(**dict(item.get("query", {}))),
        is_default=bool(item.get("is_default", False)),
        created_at=_to_local_datetime(item.get("created_at", datetime.utcnow().isoformat())),
        updated_at=_to_local_datetime(item.get("updated_at", datetime.utcnow().isoformat())),
    )


def _to_trading_journal_response(item: dict) -> TradingJournalEntryResponse:
    return TradingJournalEntryResponse(
        entry_id=str(item.get("entry_id", "")),
        trade_date=str(item.get("trade_date", "")),
        session=str(item.get("session", "Open")),
        script=str(item.get("script", "")),
        trade_strategy=str(item.get("trade_strategy", "")),
        time_period=str(item.get("time_period", "ShortTerm")) or "ShortTerm",
        side=str(item.get("side", "Buy")),
        quantity=int(item.get("quantity", 0)),
        entry_price=float(item.get("entry_price", 0)),
        entry_value=float(item.get("entry_value", 0)),
        exit_quantity=int(item.get("exit_quantity", 0)),
        squareoff_date=str(item.get("squareoff_date", "")),
        exit_price=float(item.get("exit_price", 0)),
        pnl=float(item.get("pnl", 0)),
        gain_loss_pct=float(item.get("gain_loss_pct", 0)),
        sl=float(item.get("sl", 0)),
        sl_pct=float(item.get("sl_pct", 0)),
        tp=float(item.get("tp", 0)),
        origination_logic=str(item.get("origination_logic", "")),
        comment=str(item.get("comment", "")),
        karma=int(item.get("karma", 0)),
        lots=[TradingJournalLotResponse(**dict(lot)) for lot in item.get("lots", []) if isinstance(lot, dict)],
        open_quantity=int(item.get("open_quantity", 0)),
        realized_pnl=float(item.get("realized_pnl", 0)),
        unrealized_pnl=float(item.get("unrealized_pnl", 0)),
        current_price=(float(item.get("current_price")) if item.get("current_price") is not None else None),
        live_price_as_of=(str(item.get("live_price_as_of", "")).strip() or None),
        created_at=_to_local_datetime(item.get("created_at", datetime.utcnow().isoformat())),
        updated_at=_to_local_datetime(item.get("updated_at", datetime.utcnow().isoformat())),
    )


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round2(value: float) -> float:
    return round(value + 1e-9, 2)


def _is_closed_trade(item: dict) -> bool:
    session = str(item.get("session", "")).strip().lower()
    if session == "close":
        return True

    squareoff_date = str(item.get("squareoff_date", "")).strip()
    if squareoff_date and _to_float(item.get("exit_quantity", 0.0), 0.0) >= _to_float(item.get("quantity", 0.0), 0.0):
        return True

    return _to_float(item.get("exit_quantity", 0.0), 0.0) > 0 and _to_float(item.get("exit_quantity", 0.0), 0.0) >= _to_float(item.get("quantity", 0.0), 0.0)


def _enrich_open_trade_calculations(item: dict, current_price: float | None) -> None:
    if current_price is None or _is_closed_trade(item):
        return

    quantity = max(0.0, _to_float(item.get("quantity", 0.0), 0.0))
    exit_quantity = max(0.0, _to_float(item.get("exit_quantity", 0.0), 0.0))
    entry_price = max(0.0, _to_float(item.get("entry_price", 0.0), 0.0))
    if quantity <= 0 or entry_price <= 0 or current_price <= 0:
        return

    open_quantity = max(quantity - min(exit_quantity, quantity), 0.0)
    side = str(item.get("side", "Buy")).strip().lower()
    realized_pnl = 0.0
    if exit_quantity > 0:
        realized_qty = min(exit_quantity, quantity)
        realized_price = max(0.0, _to_float(item.get("exit_price", 0.0), 0.0))
        if realized_price > 0:
            realized_per_unit = (entry_price - realized_price) if side == "sell" else (realized_price - entry_price)
            realized_pnl = _round2(realized_per_unit * realized_qty)

    unrealized_per_unit = (entry_price - current_price) if side == "sell" else (current_price - entry_price)
    unrealized_pnl = _round2(unrealized_per_unit * open_quantity) if open_quantity > 0 else 0.0
    pnl = _round2(realized_pnl + unrealized_pnl)

    entry_value = _to_float(item.get("entry_value", 0.0), 0.0)
    if entry_value <= 0:
        entry_value = _round2(quantity * entry_price)
        item["entry_value"] = entry_value

    gain_loss_pct = _round2((pnl / entry_value) * 100) if entry_value > 0 else 0.0
    item["pnl"] = pnl
    item["gain_loss_pct"] = gain_loss_pct
    item["open_quantity"] = int(open_quantity)
    item["realized_pnl"] = realized_pnl
    item["unrealized_pnl"] = unrealized_pnl


@app.get("/api/user/result-filters", response_model=UserResultFilterListResponse)
def fetch_user_result_filters(request: Request) -> UserResultFilterListResponse:
    username = str(getattr(request.state, "auth_username", "")).strip()
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    items = list_user_result_filters(username)
    return UserResultFilterListResponse(
        items=[_to_user_result_filter_response(item) for item in items],
        max_items=MAX_USER_RESULT_FILTERS,
    )


@app.post("/api/user/result-filters", response_model=UserResultFilterResponse)
def create_user_result_filter(
    request: Request,
    payload: UserResultFilterUpsertRequest,
) -> UserResultFilterResponse:
    username = str(getattr(request.state, "auth_username", "")).strip()
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        saved = save_user_result_filter(
            username=username,
            name=payload.name,
            query=payload.query.model_dump(),
            is_default=payload.is_default,
            max_filters=MAX_USER_RESULT_FILTERS,
        )
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err

    return _to_user_result_filter_response(saved)


@app.put("/api/user/result-filters/{filter_id}", response_model=UserResultFilterResponse)
def update_user_result_filter(
    filter_id: str,
    request: Request,
    payload: UserResultFilterUpsertRequest,
) -> UserResultFilterResponse:
    username = str(getattr(request.state, "auth_username", "")).strip()
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    existing = list_user_result_filters(username)
    if not any(str(item.get("filter_id", "")) == filter_id for item in existing):
        raise HTTPException(status_code=404, detail="Favorite filter not found")

    saved = save_user_result_filter(
        username=username,
        name=payload.name,
        query=payload.query.model_dump(),
        is_default=payload.is_default,
        max_filters=MAX_USER_RESULT_FILTERS,
        filter_id=filter_id,
    )
    return _to_user_result_filter_response(saved)


@app.delete("/api/user/result-filters/{filter_id}")
def remove_user_result_filter(filter_id: str, request: Request) -> dict[str, bool]:
    username = str(getattr(request.state, "auth_username", "")).strip()
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    deleted = delete_user_result_filter(username=username, filter_id=filter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Favorite filter not found")
    return {"deleted": True}


@app.get("/api/journal/entries", response_model=TradingJournalEntryListResponse)
def fetch_trading_journal_entries(
    request: Request,
    search: str = Query(default="", max_length=200),
    session: str = Query(default="all", max_length=10),
    trade_strategy: str = Query(default="all", max_length=80),
    time_period: str = Query(default="all", max_length=20),
    sort_by: JournalSortBy = Query(default="trade_date"),
    sort_order: RunSortOrder = Query(default="desc"),
    include_live_price: bool = Query(default=False),
    refresh_live_price: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> TradingJournalEntryListResponse:
    username = _auth_username(request)
    items, total = list_trading_journal_entries(
        username=username,
        search=search,
        session=session,
        trade_strategy=trade_strategy,
        time_period=time_period,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )

    if include_live_price and items:
        symbols = [
            str(item.get("script", "")).strip().upper()
            for item in items
            if str(item.get("script", "")).strip() and not _is_closed_trade(item)
        ]
        quote_map = get_live_price_quotes(symbols=symbols, force_refresh=refresh_live_price)
        enriched_items: list[dict] = []
        for item in items:
            next_item = dict(item)
            symbol = str(item.get("script", "")).strip().upper()
            quote = quote_map.get(symbol, {})
            next_item["current_price"] = quote.get("current_price") if not _is_closed_trade(next_item) else None
            next_item["live_price_as_of"] = quote.get("quote_as_of") if not _is_closed_trade(next_item) else None
            _enrich_open_trade_calculations(next_item, next_item.get("current_price"))
            enriched_items.append(next_item)
        items = enriched_items

    total_pages = max(1, (total + page_size - 1) // page_size)
    return TradingJournalEntryListResponse(
        items=[_to_trading_journal_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@app.post("/api/journal/entries", response_model=TradingJournalEntryResponse)
def add_trading_journal_entry(
    request: Request,
    payload: TradingJournalEntryUpsertRequest,
) -> TradingJournalEntryResponse:
    username = _auth_username(request)
    saved = create_trading_journal_entry(username=username, payload=payload.model_dump())
    return _to_trading_journal_response(saved)


@app.put("/api/journal/entries/{entry_id}", response_model=TradingJournalEntryResponse)
def edit_trading_journal_entry(
    entry_id: str,
    request: Request,
    payload: TradingJournalEntryUpsertRequest,
) -> TradingJournalEntryResponse:
    username = _auth_username(request)
    saved = update_trading_journal_entry(username=username, entry_id=entry_id, payload=payload.model_dump())
    if saved is None:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return _to_trading_journal_response(saved)


@app.delete("/api/journal/entries/{entry_id}")
def remove_trading_journal_entry(entry_id: str, request: Request) -> dict[str, bool]:
    username = _auth_username(request)
    deleted = delete_trading_journal_entry(username=username, entry_id=entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return {"deleted": True}


@app.get("/api/journal/entries/export.csv")
def export_trading_journal_entries_csv(
    request: Request,
    search: str = Query(default="", max_length=200),
    session: str = Query(default="all", max_length=10),
    trade_strategy: str = Query(default="all", max_length=80),
    time_period: str = Query(default="all", max_length=20),
    sort_by: JournalSortBy = Query(default="trade_date"),
    sort_order: RunSortOrder = Query(default="desc"),
) -> StreamingResponse:
    username = _auth_username(request)
    rows, _ = list_trading_journal_entries(
        username=username,
        search=search,
        session=session,
        trade_strategy=trade_strategy,
        time_period=time_period,
        sort_by=sort_by,
        sort_order=sort_order,
        page=1,
        page_size=5000,
    )

    csv_buffer = io.StringIO()
    fieldnames = [
        "Date",
        "Open/Close",
        "Script",
        "Trade Strategy",
        "Time Period",
        "Buy/Sell",
        "Quantity",
        "Entry Price",
        "Entry Value",
        "SquareOff Date",
        "Exit Price",
        "Profit/Loss",
        "% Gain/Loss",
        "SL",
        "SL %",
        "TP",
        "Origination Logic",
        "Comment",
        "Karma",
    ]
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "Date": row.get("trade_date", ""),
                "Open/Close": row.get("session", ""),
                "Script": row.get("script", ""),
                "Trade Strategy": row.get("trade_strategy", ""),
                "Time Period": row.get("time_period", ""),
                "Buy/Sell": row.get("side", ""),
                "Quantity": row.get("quantity", 0),
                "Entry Price": row.get("entry_price", 0),
                "Entry Value": row.get("entry_value", 0),
                "SquareOff Date": row.get("squareoff_date", ""),
                "Exit Price": row.get("exit_price", 0),
                "Profit/Loss": row.get("pnl", 0),
                "% Gain/Loss": row.get("gain_loss_pct", 0),
                "SL": row.get("sl", 0),
                "SL %": row.get("sl_pct", 0),
                "TP": row.get("tp", 0),
                "Origination Logic": row.get("origination_logic", ""),
                "Comment": row.get("comment", ""),
                "Karma": row.get("karma", 0),
            }
        )

    output = io.BytesIO(csv_buffer.getvalue().encode("utf-8"))
    headers = {"Content-Disposition": "attachment; filename=trading_journal_entries.csv"}
    return StreamingResponse(output, media_type="text/csv", headers=headers)


@app.post("/api/admin/backfill-legacy-ownership")
def admin_backfill_legacy_ownership(request: Request) -> dict[str, object]:
    username = str(getattr(request.state, "auth_username", "")).strip()
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if username != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    before = count_legacy_ownerless_records()
    migrated = backfill_legacy_ownership(username=username)
    after = count_legacy_ownerless_records()

    return {
        "target_username": username,
        "before": before,
        "migrated": migrated,
        "after": after,
    }
