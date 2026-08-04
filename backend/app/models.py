from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ALLOWED_INPUT_HEADERS = [
    "Name",
    "BSE Code",
    "NSE Code",
    "ISIN Code",
    "Industry Group",
]


class RunCreateRequest(BaseModel):
    input_universe: str = Field(default="nifty-500-v2")
    output_mode: Literal["csv"] = Field(default="csv")
    refresh: bool = Field(default=True)


class UploadRunCreateRequest(BaseModel):
    output_mode: Literal["csv"] = Field(default="csv")
    refresh: bool = Field(default=True)


class UploadWorkflowRunRequest(BaseModel):
    upload_id: str
    output_mode: Literal["csv"] = Field(default="csv")
    refresh: bool = Field(default=True)
    confirm_run: bool = Field(default=False)


class RunSummary(BaseModel):
    run_id: str
    status: str
    created_at: datetime
    stopped_at: datetime | None = None
    input_universe: str
    output_mode: str
    refresh: bool
    processed: int = 0
    total: int = 0
    pass_count: int = 0
    fail_count: int = 0
    skipped_count: int = 0


RunSortBy = Literal[
    "created_at",
    "status",
    "input_universe",
    "output_mode",
    "processed",
    "pass_count",
    "fail_count",
    "skipped_count",
]
RunSortOrder = Literal["asc", "desc"]


class RunListResponse(BaseModel):
    items: list[RunSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


RunResultSortBy = Literal[
    "name",
    "symbol",
    "market_cap_cr",
    "industry_group",
    "base_rev_cr",
    "end_rev_cr",
    "total_2y_growth_pct",
    "ttm_rev_cr",
    "ttm_vs_end_fy_pct",
    "combined_growth_pct",
    "final_status",
    "current_price",
    "price_2y_ago",
    "price_2y_change_pct",
    "roce_pct",
    "error",
]


class RunResultsPageResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class SignupRequest(BaseModel):
    username: str
    password: str


class AuthStatusResponse(BaseModel):
    authenticated: bool
    username: str | None = None
    signup_required: bool = False


class UploadValidationResponse(BaseModel):
    upload_id: str | None = None
    filename: str
    valid: bool
    allowed_headers: list[str]
    detected_headers: list[str]
    missing_headers: list[str] = Field(default_factory=list)
    unexpected_headers: list[str] = Field(default_factory=list)
    total_rows: int = 0
    accepted_rows: int = 0
    rejected_rows: int = 0
    errors: list[str] = Field(default_factory=list)
    preview_rows: list[dict[str, str]] = Field(default_factory=list)


class UploadStatusResponse(BaseModel):
    upload_id: str
    filename: str
    created_at: datetime
    valid: bool
    total_rows: int
    accepted_rows: int
    rejected_rows: int


class ResultFilterQuery(BaseModel):
    search: str = ""
    final_status: str = "all"
    market_cap_min: str = ""
    market_cap_max: str = ""
    industry_group: str = ""
    combined_growth_min: str = ""
    combined_growth_max: str = ""
    roce_min: str = ""
    roce_max: str = ""
    away_min: str = ""
    away_max: str = ""
    sort_by: str = "name"
    sort_order: RunSortOrder = "asc"
    page_size: int = 25


class UserResultFilterUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    query: ResultFilterQuery
    is_default: bool = False


class UserResultFilterResponse(BaseModel):
    filter_id: str
    name: str
    query: ResultFilterQuery
    is_default: bool
    created_at: datetime
    updated_at: datetime


class UserResultFilterListResponse(BaseModel):
    items: list[UserResultFilterResponse]
    max_items: int = 5
