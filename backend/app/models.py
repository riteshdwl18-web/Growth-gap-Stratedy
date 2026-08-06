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
    stage: str = "queued"
    status_message: str = ""
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stopped_at: datetime | None = None
    cooldown_until: datetime | None = None
    input_universe: str
    output_mode: str
    refresh: bool
    processed: int = 0
    total: int = 0
    pass_count: int = 0
    fail_count: int = 0
    skipped_count: int = 0
    retry_count: int = 0


RunSortBy = Literal[
    "created_at",
    "status",
    "stage",
    "input_universe",
    "output_mode",
    "processed",
    "retry_count",
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


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AuthStatusResponse(BaseModel):
    authenticated: bool
    username: str | None = None
    signup_required: bool = False


class MessageResponse(BaseModel):
    message: str


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
    total_2y_growth_min: str = ""
    total_2y_growth_max: str = ""
    ttm_vs_end_fy_min: str = ""
    ttm_vs_end_fy_max: str = ""
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


class LivePriceQuoteResponse(BaseModel):
    symbol: str
    current_price: float | None = None
    quote_as_of: str | None = None
    source: str | None = None


JournalSessionType = Literal["Open", "Close"]
JournalSideType = Literal["Buy", "Sell"]
JournalTimePeriodType = Literal["ShortTerm", "LongTerm"]
JournalSortBy = Literal[
    "trade_date",
    "squareoff_date",
    "script",
    "trade_strategy",
    "time_period",
    "side",
    "quantity",
    "entry_price",
    "exit_price",
    "pnl",
    "gain_loss_pct",
    "karma",
    "updated_at",
]


class TradingJournalEntryBase(BaseModel):
    trade_date: str = Field(min_length=1, max_length=20)
    session: JournalSessionType
    script: str = Field(min_length=1, max_length=40)
    trade_strategy: str = Field(default="", max_length=80)
    time_period: JournalTimePeriodType = Field(default="ShortTerm")
    side: JournalSideType
    quantity: int = Field(ge=1)
    entry_price: float = Field(ge=0)
    entry_value: float = Field(ge=0)
    exit_quantity: int = Field(default=0, ge=0)
    squareoff_date: str = Field(default="", max_length=20)
    exit_price: float = Field(default=0, ge=0)
    pnl: float = Field(default=0)
    gain_loss_pct: float = Field(default=0)
    sl: float = Field(default=0, ge=0)
    sl_pct: float = Field(default=0)
    tp: float = Field(default=0, ge=0)
    origination_logic: str = Field(default="", max_length=500)
    comment: str = Field(default="", max_length=1000)
    karma: int = Field(default=0, ge=0, le=10)


class TradingJournalLotBase(BaseModel):
    lot_date: str = Field(min_length=1, max_length=20)
    quantity: int = Field(ge=1)
    price: float = Field(ge=0)
    note: str = Field(default="", max_length=200)


class TradingJournalLotResponse(TradingJournalLotBase):
    lot_id: int


class TradingJournalLotUpsertRequest(TradingJournalLotBase):
    pass


class TradingJournalEntryUpsertRequest(TradingJournalEntryBase):
    lots: list[TradingJournalLotUpsertRequest] = Field(default_factory=list)


class TradingJournalEntryResponse(TradingJournalEntryBase):
    entry_id: str
    lots: list[TradingJournalLotResponse] = Field(default_factory=list)
    open_quantity: int = Field(default=0, ge=0)
    realized_pnl: float = Field(default=0)
    unrealized_pnl: float = Field(default=0)
    current_price: float | None = None
    live_price_as_of: str | None = None
    created_at: datetime
    updated_at: datetime


class TradingJournalEntryListResponse(BaseModel):
    items: list[TradingJournalEntryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
