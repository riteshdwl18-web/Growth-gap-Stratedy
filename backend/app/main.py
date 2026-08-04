from datetime import datetime
import csv
import io

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse

from app.config import settings
from app.models import (
    AuthStatusResponse,
    HealthResponse,
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
    UserResultFilterListResponse,
    UserResultFilterResponse,
    UserResultFilterUpsertRequest,
)
from app.services.auth import (
    SESSION_COOKIE_NAME,
    begin_google_oauth,
    complete_google_oauth,
    create_user,
    create_session,
    get_session_username,
    is_google_oauth_available,
    has_any_user,
    invalidate_session,
    verify_credentials,
)
from app.services.screener import (
    build_results_csv_payload,
    create_run,
    create_run_from_upload,
    generate_run_csv,
    get_run,
    get_run_results,
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
    count_legacy_ownerless_records,
    delete_user_result_filter,
    list_user_result_filters,
    save_user_result_filter,
)


app = FastAPI(title=settings.app_name, version=settings.app_version)

MAX_USER_RESULT_FILTERS = 5

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

    username = payload.username.strip()
    if not verify_credentials(username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_session(username)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.session_ttl_minutes * 60,
    )
    return AuthStatusResponse(authenticated=True, username=username, signup_required=False)


@app.post("/api/auth/signup", response_model=AuthStatusResponse)
def signup(payload: SignupRequest, response: Response) -> AuthStatusResponse:
    username = payload.username.strip()
    password = payload.password
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    created = create_user(username, password)
    if not created:
        raise HTTPException(status_code=409, detail="Username already exists")

    token = create_session(username)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.session_ttl_minutes * 60,
    )
    return AuthStatusResponse(authenticated=True, username=username, signup_required=False)


@app.get("/api/auth/google/start")
def google_oauth_start(redirect_uri: str = Query(default="http://localhost:5173/dashboard")) -> RedirectResponse:
    if not is_google_oauth_available():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")

    try:
        auth_url = begin_google_oauth(redirect_uri)
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return RedirectResponse(url=auth_url)


@app.get("/api/auth/google/callback")
def google_oauth_callback(code: str = Query(default=""), state: str = Query(default="")) -> RedirectResponse:
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing OAuth callback parameters")

    try:
        username, frontend_redirect = complete_google_oauth(code=code, state=state)
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    token = create_session(username)
    response = RedirectResponse(url=frontend_redirect)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.session_ttl_minutes * 60,
    )
    return response


@app.post("/api/auth/logout", response_model=AuthStatusResponse)
def logout(request: Request, response: Response) -> AuthStatusResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    invalidate_session(token)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", samesite="lax")
    return AuthStatusResponse(authenticated=False, username=None, signup_required=not has_any_user())


@app.get("/api/auth/me", response_model=AuthStatusResponse)
def me(request: Request) -> AuthStatusResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    username = get_session_username(token)
    if not username:
        return AuthStatusResponse(
            authenticated=False,
            username=None,
            signup_required=not has_any_user(),
        )
    return AuthStatusResponse(authenticated=True, username=username, signup_required=False)


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


@app.get("/api/runs/{run_id}/download.csv")
def download_run_csv(run_id: str, request: Request) -> FileResponse:
    username = _auth_username(request)
    run = get_run(run_id, username=username)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "completed":
        raise HTTPException(status_code=409, detail="CSV is available only for completed runs")

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
        created_at=datetime.fromisoformat(str(payload.get("created_at", datetime.utcnow().isoformat()))),
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
        created_at=datetime.fromisoformat(str(item.get("created_at", datetime.utcnow().isoformat()))),
        updated_at=datetime.fromisoformat(str(item.get("updated_at", datetime.utcnow().isoformat()))),
    )


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
