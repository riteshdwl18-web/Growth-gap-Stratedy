from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from ..celery_app import celery_app
from ..models import RunCreateRequest, UploadRunCreateRequest, RunSummary
from ..storage import (
    append_result,
    export_csv_path,
    list_runs_payloads,
    load_live_price_cache,
    load_results,
    load_run,
    now_iso,
    save_live_price_cache,
    save_results,
    save_run,
)


LIVE_PRICE_HTTP_TIMEOUT_SECONDS = 2.5
LIVE_PRICE_MAX_WORKERS = 8
LIVE_PRICE_CACHE_TTL_HOURS = 24


def _start_local_fallback_worker(run_id: str) -> None:
    """Run processing in a local background thread if Celery broker is unavailable."""
    worker = threading.Thread(target=execute_run_task, args=(run_id,), daemon=True)
    worker.start()


def _resolve_swingtrading_path() -> Path:
    """Locate SwingTrading project path for engine imports.

    Preferred layout:
      GrowthGapStrategy/SwingTrading
    Legacy layout (still supported):
      Desktop/SwingTrading (sibling of GrowthGapStrategy)
    """
    current = Path(__file__).resolve()
    repo_root = current.parents[3]
    candidates = [
        repo_root / "SwingTrading",
        repo_root.parent / "SwingTrading",
    ]

    for candidate in candidates:
        if (candidate / "stock_screener.py").exists():
            return candidate

    raise FileNotFoundError(
        "SwingTrading engine not found. Expected one of: "
        f"{candidates[0]} or {candidates[1]}"
    )


def _get_stock_screener_module():
    """Import SwingTrading stock_screener module for production strategy logic."""
    swing_path = _resolve_swingtrading_path()
    if str(swing_path) not in sys.path:
        sys.path.insert(0, str(swing_path))
    return importlib.import_module("stock_screener")


def create_run(payload: RunCreateRequest, username: str) -> RunSummary:
    _ensure_no_active_run(username)
    run_id = str(uuid4())
    payload_dict = {
        "run_id": run_id,
        "status": "queued",
        "created_at": now_iso(),
        "username": username,
        "stopped_at": None,
        "input_universe": payload.input_universe,
        "output_mode": payload.output_mode,
        "refresh": payload.refresh,
        "processed": 0,
        "total": 0,
        "pass_count": 0,
        "fail_count": 0,
        "skipped_count": 0,
        "stop_requested": False,
        "source_type": "universe",
        "source_ref": payload.input_universe,
    }
    save_run(run_id, payload_dict)
    save_results(run_id, [])
    try:
        task = celery_app.send_task("app.tasks.process_run_task", args=[run_id])
        payload_dict["task_id"] = task.id
    except Exception as err:
        payload_dict["task_id"] = None
        payload_dict["enqueue_warning"] = f"Celery unavailable, using local fallback: {err}"
        _start_local_fallback_worker(run_id)
    save_run(run_id, payload_dict)
    return _to_run_summary(payload_dict)


def create_run_from_upload(
    upload_id: str,
    filename: str,
    total_rows: int,
    payload: UploadRunCreateRequest,
    username: str,
) -> RunSummary:
    _ensure_no_active_run(username)
    run_id = str(uuid4())
    payload_dict = {
        "run_id": run_id,
        "status": "queued",
        "created_at": now_iso(),
        "username": username,
        "stopped_at": None,
        "input_universe": f"upload:{filename}",
        "output_mode": payload.output_mode,
        "refresh": payload.refresh,
        "processed": 0,
        "total": total_rows,
        "pass_count": 0,
        "fail_count": 0,
        "skipped_count": 0,
        "stop_requested": False,
        "source_type": "upload",
        "source_ref": upload_id,
    }
    save_run(run_id, payload_dict)
    save_results(run_id, [])
    try:
        task = celery_app.send_task("app.tasks.process_run_task", args=[run_id])
        payload_dict["task_id"] = task.id
    except Exception as err:
        payload_dict["task_id"] = None
        payload_dict["enqueue_warning"] = f"Celery unavailable, using local fallback: {err}"
        _start_local_fallback_worker(run_id)
    save_run(run_id, payload_dict)
    return _to_run_summary(payload_dict)


def list_runs(
    username: str,
    search: str = "",
    status: str = "all",
    sort_by: str = "created_at",
    sort_order: str = "desc",
    created_from: str = "",
    created_to: str = "",
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[RunSummary], int]:
    sorted_runs = query_runs(
        username=username,
        search=search,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order,
        created_from=created_from,
        created_to=created_to,
    )
    total = len(sorted_runs)
    start = (page - 1) * page_size
    end = start + page_size
    return sorted_runs[start:end], total


def query_runs(
    username: str,
    search: str = "",
    status: str = "all",
    sort_by: str = "created_at",
    sort_order: str = "desc",
    created_from: str = "",
    created_to: str = "",
) -> list[RunSummary]:
    runs = [_to_run_summary(item) for item in list_runs_payloads(username=username)]
    filtered_runs = _filter_runs(
        runs,
        search=search,
        status=status,
        created_from=created_from,
        created_to=created_to,
    )
    return _sort_runs(filtered_runs, sort_by=sort_by, sort_order=sort_order)


def get_run(run_id: str, username: str) -> RunSummary | None:
    payload = load_run(run_id)
    if not payload:
        return None
    owner = str(payload.get("username", ""))
    if owner != username:
        return None
    return _to_run_summary(payload)


def get_run_results(
    username: str,
    run_id: str,
    search: str = "",
    final_status: str = "all",
    market_cap_min: str = "",
    market_cap_max: str = "",
    industry_group: str = "",
    combined_growth_min: str = "",
    combined_growth_max: str = "",
    roce_min: str = "",
    roce_max: str = "",
    away_min: str = "",
    away_max: str = "",
    live_price: bool = False,
    sort_by: str = "name",
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[dict], int] | None:
    sorted_rows = query_run_results(
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
        live_price=False,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    if sorted_rows is None:
        return None
    total = len(sorted_rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = sorted_rows[start:end]
    page_rows = _apply_live_price_snapshot(page_rows, force_refresh=live_price)
    return page_rows, total


def query_run_results(
    username: str,
    run_id: str,
    search: str = "",
    final_status: str = "all",
    market_cap_min: str = "",
    market_cap_max: str = "",
    industry_group: str = "",
    combined_growth_min: str = "",
    combined_growth_max: str = "",
    roce_min: str = "",
    roce_max: str = "",
    away_min: str = "",
    away_max: str = "",
    live_price: bool = False,
    sort_by: str = "name",
    sort_order: str = "asc",
) -> list[dict] | None:
    run = load_run(run_id)
    if not run:
        return None
    owner = str(run.get("username", ""))
    if owner != username:
        return None
    rows = load_results(run_id)
    filtered_rows = _filter_results(
        rows,
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
    )
    if live_price:
        filtered_rows = _apply_live_price_snapshot(filtered_rows, force_refresh=True)
    return _sort_results(filtered_rows, sort_by=sort_by, sort_order=sort_order)


def list_run_industry_groups(run_id: str, username: str) -> list[str] | None:
    run = load_run(run_id)
    if not run:
        return None
    owner = str(run.get("username", ""))
    if owner != username:
        return None

    rows = load_results(run_id)
    unique: dict[str, str] = {}
    for row in rows:
        raw_value = str(row.get("industry_group", "")).strip()
        if not raw_value:
            continue
        key = raw_value.lower()
        if key not in unique:
            unique[key] = raw_value

    return sorted(unique.values(), key=lambda value: value.lower())


def stop_run(run_id: str, username: str) -> RunSummary | None:
    run = load_run(run_id)
    if not run:
        return None
    owner = str(run.get("username", ""))
    if owner != username:
        return None

    if run["status"] in {"completed", "failed", "stopped"}:
        return _to_run_summary(run)

    run["stop_requested"] = True
    run["status"] = "stopped"
    run["stopped_at"] = run.get("stopped_at") or now_iso()

    save_run(run_id, run)
    return _to_run_summary(run)


def _is_stop_requested(run_id: str) -> bool:
    run = load_run(run_id)
    if not run:
        return True
    return bool(run.get("stop_requested"))


def _load_rows_from_universe(input_universe: str) -> list[dict[str, str]]:
    module = _get_stock_screener_module()
    if input_universe not in module.INPUT_FILES:
        raise ValueError(f"Unknown input universe: {input_universe}")

    input_path = module.INPUT_FILES[input_universe]
    symbols = module.load_symbols_from_csv(input_path)
    rows: list[dict[str, str]] = []
    for name, symbol, industry in symbols:
        nse_code = symbol.replace(".NS", "").strip()
        rows.append(
            {
                "Name": name,
                "BSE Code": "",
                "NSE Code": nse_code,
                "ISIN Code": "",
                "Industry Group": industry,
            }
        )
    return rows


def _load_rows_from_upload(upload_id: str, username: str) -> list[dict[str, str]]:
    from .uploads import get_uploaded_dataset

    dataset = get_uploaded_dataset(upload_id, username=username)
    if dataset is None:
        raise ValueError("Upload not found")
    return dataset.rows


def execute_run_task(run_id: str) -> None:
    run = load_run(run_id)
    if not run:
        return

    try:
        run_username = str(run.get("username", ""))
        if run.get("source_type") == "upload":
            rows = _load_rows_from_upload(str(run.get("source_ref", "")), run_username)
        else:
            rows = _load_rows_from_universe(str(run.get("source_ref", "")))

        _execute_rows(run_id, rows, bool(run.get("refresh", False)))
    except Exception as err:
        run = load_run(run_id)
        if not run:
            return
        run["status"] = "failed"
        run["skipped_count"] = max(int(run.get("skipped_count", 0)), 1)
        save_run(run_id, run)
        append_result(
            run_id,
            {
                "name": str(run.get("source_ref", "")),
                "symbol": "",
                "final_status": "",
                "error": str(err),
            },
        )


def _execute_rows(run_id: str, rows: list[dict[str, str]], refresh: bool) -> None:
    try:
        module = _get_stock_screener_module()
    except Exception as err:
        run = load_run(run_id)
        if run is not None:
            run["status"] = "failed"
            run["skipped_count"] = max(int(run.get("skipped_count", 0)), 1)
            save_run(run_id, run)
            append_result(
                run_id,
                {
                    "name": "",
                    "symbol": "",
                    "final_status": "",
                    "error": f"Failed to load SwingTrading engine: {err}",
                },
            )
        return

    run = load_run(run_id)
    if not run:
        return
    if run.get("status") == "stopped" or _is_stop_requested(run_id):
        run["status"] = "stopped"
        run["stopped_at"] = run.get("stopped_at") or now_iso()
        save_run(run_id, run)
        return
    run["status"] = "running"
    run["total"] = len(rows)
    save_run(run_id, run)

    for row in rows:
        if _is_stop_requested(run_id):
            run = load_run(run_id)
            if run is not None:
                run["status"] = "stopped"
                run["stopped_at"] = run.get("stopped_at") or now_iso()
                save_run(run_id, run)
            return

        nse_code = (row.get("NSE Code") or "").strip()
        name = (row.get("Name") or "").strip()
        industry = (row.get("Industry Group") or "").strip()

        if not nse_code:
            result = {
                "name": name,
                "symbol": "",
                "final_status": "",
                "error": "NSE Code missing",
            }
            run = load_run(run_id)
            if run is None:
                return
            run["processed"] = int(run.get("processed", 0)) + 1
            run["skipped_count"] = int(run.get("skipped_count", 0)) + 1
            save_run(run_id, run)
            append_result(run_id, result)
            continue

        symbol = f"{nse_code}.NS"
        try:
            result = module.check_sales_cagr(symbol, refresh=refresh)
            result["name"] = name
            result["industry_group"] = industry
            result_status = str(result.get("final_status") or "").upper()
            has_error = bool(result.get("error"))
        except Exception as err:
            result = {
                "name": name,
                "symbol": symbol,
                "industry_group": industry,
                "final_status": "",
                "error": str(err),
            }
            result_status = ""
            has_error = True

        run = load_run(run_id)
        if run is None:
            return

        run["processed"] = int(run.get("processed", 0)) + 1
        if has_error:
            run["skipped_count"] = int(run.get("skipped_count", 0)) + 1
        elif result_status == "PASS":
            run["pass_count"] = int(run.get("pass_count", 0)) + 1
        else:
            run["fail_count"] = int(run.get("fail_count", 0)) + 1

        save_run(run_id, run)
        append_result(run_id, result)

    run = load_run(run_id)
    if run and run.get("status") not in {"failed", "stopped"}:
        run["status"] = "completed"
        save_run(run_id, run)


def generate_run_csv(run_id: str, username: str) -> Path | None:
    run = load_run(run_id)
    if not run:
        return None
    owner = str(run.get("username", ""))
    if owner != username:
        return None
    if run.get("status") != "completed":
        return None

    rows = load_results(run_id)
    output_path = export_csv_path(run_id)
    fieldnames, csv_rows = build_results_csv_payload(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        for row in csv_rows:
            writer.writerow(row)
    return output_path


def build_results_csv_payload(rows: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    base_fy_label, end_fy_label = _resolve_export_fy_labels(rows)
    base_rev_col = f"Base Rev {base_fy_label} (Cr)" if base_fy_label else "Base Rev (Cr)"
    end_rev_col = f"End Rev {end_fy_label} (Cr)" if end_fy_label else "End Rev (Cr)"

    fieldnames = [
        "Name",
        "Symbol",
        "Mark.Cap",
        "Industry Group",
        base_rev_col,
        end_rev_col,
        "Total 2Y Growth (%)",
        "TTM Rev (Cr)",
        "TTM vs End FY (%)",
        "Combined Growth (%)",
        "Final Status",
        "Current Price (INR)",
        "Entry Price (INR)",
        "% Away",
        "ROCE (%)",
        "Error",
    ]

    csv_rows: list[dict[str, Any]] = []
    for row in rows:
        csv_rows.append(
            {
                "Name": row.get("name", ""),
                "Symbol": row.get("symbol", ""),
                "Mark.Cap": row.get("market_cap_cr", ""),
                "Industry Group": row.get("industry_group", ""),
                base_rev_col: row.get("base_rev_cr", ""),
                end_rev_col: row.get("end_rev_cr", ""),
                "Total 2Y Growth (%)": row.get("total_2y_growth_pct", ""),
                "TTM Rev (Cr)": row.get("ttm_rev_cr", ""),
                "TTM vs End FY (%)": row.get("ttm_vs_end_fy_pct", ""),
                "Combined Growth (%)": row.get("combined_growth_pct", ""),
                "Final Status": row.get("final_status", ""),
                "Current Price (INR)": row.get("current_price", ""),
                "Entry Price (INR)": row.get("price_2y_ago", ""),
                "% Away": row.get("price_2y_change_pct", ""),
                "ROCE (%)": row.get("roce_pct", ""),
                "Error": row.get("error", ""),
            }
        )

    return fieldnames, csv_rows


def _resolve_export_fy_labels(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    base_fy_label: str | None = None
    end_fy_label: str | None = None
    for row in sorted(rows, key=lambda item: str(item.get("end_fy") or ""), reverse=True):
        base_fy = row.get("base_fy")
        end_fy = row.get("end_fy")
        if base_fy and end_fy:
            base_fy_label = str(base_fy)
            end_fy_label = str(end_fy)
            break
    return base_fy_label, end_fy_label


def _to_run_summary(payload: dict) -> RunSummary:
    stopped_at_raw = payload.get("stopped_at")
    return RunSummary(
        run_id=str(payload.get("run_id")),
        status=str(payload.get("status", "queued")),
        created_at=_parse_iso_datetime_utc(payload.get("created_at", now_iso())),
        stopped_at=_parse_iso_datetime_utc(stopped_at_raw) if stopped_at_raw else None,
        input_universe=str(payload.get("input_universe", "")),
        output_mode=str(payload.get("output_mode", "csv")),
        refresh=bool(payload.get("refresh", False)),
        processed=int(payload.get("processed", 0)),
        total=int(payload.get("total", 0)),
        pass_count=int(payload.get("pass_count", 0)),
        fail_count=int(payload.get("fail_count", 0)),
        skipped_count=int(payload.get("skipped_count", 0)),
    )


def _filter_runs(
    runs: list[RunSummary],
    search: str,
    status: str,
    created_from: str,
    created_to: str,
) -> list[RunSummary]:
    next_runs = runs
    status_norm = status.strip().lower()
    if status_norm and status_norm != "all":
        next_runs = [run for run in next_runs if run.status.strip().lower() == status_norm]

    from_dt = _parse_datetime_filter(created_from, is_end=False)
    to_dt = _parse_datetime_filter(created_to, is_end=True)
    if from_dt:
        next_runs = [run for run in next_runs if run.created_at >= from_dt]
    if to_dt:
        next_runs = [run for run in next_runs if run.created_at <= to_dt]

    search_norm = search.strip().lower()
    if not search_norm:
        return next_runs

    return [
        run
        for run in next_runs
        if search_norm in run.run_id.lower()
        or search_norm in run.status.lower()
        or search_norm in run.input_universe.lower()
        or search_norm in run.output_mode.lower()
        or search_norm in run.created_at.isoformat().lower()
    ]


def _sort_runs(runs: list[RunSummary], sort_by: str, sort_order: str) -> list[RunSummary]:
    reverse = sort_order.lower() == "desc"
    key_map = {
        "created_at": lambda run: run.created_at,
        "status": lambda run: run.status.lower(),
        "input_universe": lambda run: run.input_universe.lower(),
        "output_mode": lambda run: run.output_mode.lower(),
        "processed": lambda run: run.processed,
        "pass_count": lambda run: run.pass_count,
        "fail_count": lambda run: run.fail_count,
        "skipped_count": lambda run: run.skipped_count,
    }
    key_fn = key_map.get(sort_by, key_map["created_at"])
    return sorted(runs, key=key_fn, reverse=reverse)


def _filter_results(
    rows: list[dict[str, Any]],
    search: str,
    final_status: str,
    market_cap_min: str,
    market_cap_max: str,
    industry_group: str,
    combined_growth_min: str,
    combined_growth_max: str,
    roce_min: str,
    roce_max: str,
    away_min: str,
    away_max: str,
) -> list[dict[str, Any]]:
    next_rows = rows
    status_norm = final_status.strip().lower()
    if status_norm and status_norm != "all":
        next_rows = [
            row
            for row in next_rows
            if str(row.get("final_status", "")).strip().lower() == status_norm
        ]

    market_cap_min_value = _parse_optional_float(market_cap_min)
    market_cap_max_value = _parse_optional_float(market_cap_max)
    combined_growth_min_value = _parse_optional_float(combined_growth_min)
    combined_growth_max_value = _parse_optional_float(combined_growth_max)
    roce_min_value = _parse_optional_float(roce_min)
    roce_max_value = _parse_optional_float(roce_max)
    away_min_value = _parse_optional_float(away_min)
    away_max_value = _parse_optional_float(away_max)
    industry_group_values = [
        value.strip().lower() for value in industry_group.split(",") if value.strip()
    ]

    def _row_within_range(value: Any, min_value: float | None, max_value: float | None) -> bool:
        numeric = _safe_float_or_none(value)
        if numeric is None:
            return False
        if min_value is not None and numeric < min_value:
            return False
        if max_value is not None and numeric > max_value:
            return False
        return True

    if market_cap_min_value is not None or market_cap_max_value is not None:
        next_rows = [
            row
            for row in next_rows
            if _row_within_range(row.get("market_cap_cr"), market_cap_min_value, market_cap_max_value)
        ]

    if combined_growth_min_value is not None or combined_growth_max_value is not None:
        next_rows = [
            row
            for row in next_rows
            if _row_within_range(
                row.get("combined_growth_pct"),
                combined_growth_min_value,
                combined_growth_max_value,
            )
        ]

    if roce_min_value is not None or roce_max_value is not None:
        next_rows = [
            row
            for row in next_rows
            if _row_within_range(row.get("roce_pct"), roce_min_value, roce_max_value)
        ]

    if away_min_value is not None or away_max_value is not None:
        next_rows = [
            row
            for row in next_rows
            if _row_within_range(row.get("price_2y_change_pct"), away_min_value, away_max_value)
        ]

    if industry_group_values and "all" not in industry_group_values:
        allowed_groups = set(industry_group_values)
        next_rows = [
            row
            for row in next_rows
            if str(row.get("industry_group", "")).strip().lower() in allowed_groups
        ]

    search_norm = search.strip().lower()
    if not search_norm:
        return next_rows

    def _matches(row: dict[str, Any]) -> bool:
        searchable = [
            str(row.get("name", "")),
            str(row.get("symbol", "")),
            str(row.get("final_status", "")),
            str(row.get("industry_group", "")),
            str(row.get("error", "")),
        ]
        combined = " ".join(searchable).lower()
        return search_norm in combined

    return [row for row in next_rows if _matches(row)]


def _sort_results(rows: list[dict[str, Any]], sort_by: str, sort_order: str) -> list[dict[str, Any]]:
    reverse = sort_order.lower() == "desc"

    def _text_key(field: str):
        return lambda row: str(row.get(field, "")).lower()

    def _float_key(field: str):
        return lambda row: _safe_float(row.get(field))

    key_map = {
        "name": _text_key("name"),
        "symbol": _text_key("symbol"),
        "market_cap_cr": _float_key("market_cap_cr"),
        "industry_group": _text_key("industry_group"),
        "base_rev_cr": _float_key("base_rev_cr"),
        "end_rev_cr": _float_key("end_rev_cr"),
        "final_status": _text_key("final_status"),
        "total_2y_growth_pct": _float_key("total_2y_growth_pct"),
        "ttm_rev_cr": _float_key("ttm_rev_cr"),
        "ttm_vs_end_fy_pct": _float_key("ttm_vs_end_fy_pct"),
        "combined_growth_pct": _float_key("combined_growth_pct"),
        "current_price": _float_key("current_price"),
        "price_2y_ago": _float_key("price_2y_ago"),
        "price_2y_change_pct": _float_key("price_2y_change_pct"),
        "roce_pct": _float_key("roce_pct"),
        "error": _text_key("error"),
    }
    key_fn = key_map.get(sort_by, key_map["name"])
    return sorted(rows, key=key_fn, reverse=reverse)


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return float("-inf")
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _safe_float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_optional_float(raw_value: str) -> float | None:
    text = raw_value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _apply_live_price_snapshot(rows: list[dict[str, Any]], force_refresh: bool = False) -> list[dict[str, Any]]:
    if not rows:
        return rows

    symbols: list[str] = []
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if symbol:
            symbols.append(symbol)

    captured_at = now_iso()
    live_map = _fetch_live_prices(symbols, force_refresh=force_refresh)

    stamped_rows: list[dict[str, Any]] = []
    for row in rows:
        next_row = dict(row)
        next_row["live_price_as_of"] = captured_at
        symbol = str(row.get("symbol", "")).strip().upper()
        live_value = live_map.get(symbol)
        if live_value is None:
            stamped_rows.append(next_row)
            continue

        next_row["current_price"] = round(live_value, 2)

        entry_value = _safe_float_or_none(row.get("price_2y_ago"))
        if entry_value is not None and entry_value != 0:
            next_row["price_2y_change_pct"] = round(((live_value - entry_value) / entry_value) * 100, 1)

        stamped_rows.append(next_row)

    return stamped_rows


def _fetch_live_prices(symbols: list[str], force_refresh: bool = False) -> dict[str, float]:
    unique_symbols = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    if not unique_symbols:
        return {}

    cache_hits = load_live_price_cache(unique_symbols)
    prices: dict[str, float] = {
        symbol: float(payload["price"])
        for symbol, payload in cache_hits.items()
        if payload.get("price") is not None
    }

    if not force_refresh:
        # Normal list loading path: serve from DB cache only.
        return prices

    now_utc = datetime.utcnow()
    now_utc_iso = now_utc.isoformat()

    # Manual refresh path: fetch all symbols from provider, keep cached value when a fetch fails.
    symbols_to_fetch = list(unique_symbols)
    if not symbols_to_fetch:
        return prices

    fresh_prices: dict[str, float] = {}
    max_workers = min(LIVE_PRICE_MAX_WORKERS, len(symbols_to_fetch))
    if max_workers <= 1:
        for symbol in symbols_to_fetch:
            live_value = _fetch_google_finance_price(symbol)
            if live_value is not None:
                fresh_prices[symbol] = live_value
                prices[symbol] = live_value
        if fresh_prices:
            save_live_price_cache(
                fresh_prices,
                quote_as_of=now_utc_iso,
                expires_at=(now_utc + timedelta(hours=LIVE_PRICE_CACHE_TTL_HOURS)).isoformat(),
            )
        return prices

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_symbol = {
            pool.submit(_fetch_google_finance_price, symbol): symbol for symbol in symbols_to_fetch
        }
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                live_value = future.result()
            except Exception:
                live_value = None
            if live_value is not None:
                prices[symbol] = live_value
                fresh_prices[symbol] = live_value

    if fresh_prices:
        save_live_price_cache(
            fresh_prices,
            quote_as_of=now_utc_iso,
            expires_at=(now_utc + timedelta(hours=LIVE_PRICE_CACHE_TTL_HOURS)).isoformat(),
        )

    return prices


def _fetch_google_finance_price(symbol: str) -> float | None:
    for quote_ticker in _google_finance_quote_tickers(symbol):
        url = f"https://www.google.com/finance/quote/{quote_ticker}"
        try:
            request = urllib_request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    )
                },
            )
            with urllib_request.urlopen(request, timeout=LIVE_PRICE_HTTP_TIMEOUT_SECONDS) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except (urllib_error.URLError, TimeoutError, ValueError, OSError):
            continue

        value = _parse_google_finance_price(html)
        if value is not None:
            return value

    return None


def _parse_iso_datetime_utc(raw_value: Any) -> datetime:
    text = str(raw_value).strip()
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _google_finance_quote_tickers(symbol: str) -> list[str]:
    symbol_norm = symbol.strip().upper()
    if not symbol_norm:
        return []

    if symbol_norm.endswith(".NS"):
        base = symbol_norm[:-3]
        return [f"{base}:NSE"]

    if symbol_norm.endswith(".BO"):
        base = symbol_norm[:-3]
        return [f"{base}:BOM"]

    # If exchange suffix is missing, try NSE first, then BSE.
    return [f"{symbol_norm}:NSE", f"{symbol_norm}:BOM"]


def _parse_google_finance_price(html: str) -> float | None:
    patterns = [
        r'itemprop="price"\s+content="([0-9][0-9,]*\.?[0-9]*)"',
        r'"price"\s*:\s*"?([0-9][0-9,]*\.?[0-9]*)"?',
        r'class="YMlKec fxKbKc"[^>]*>([0-9][0-9,]*\.?[0-9]*)<',
    ]

    for pattern in patterns:
        match = re.search(pattern, html)
        if not match:
            continue
        raw_value = match.group(1).replace(",", "").strip()
        try:
            return float(raw_value)
        except ValueError:
            continue

    return None


def _parse_datetime_filter(raw_value: str, is_end: bool) -> datetime | None:
    text = raw_value.strip()
    if not text:
        return None

    try:
        if "T" in text:
            return _parse_iso_datetime_utc(text)

        parsed = datetime.fromisoformat(f"{text}T00:00:00")
        if is_end:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return _parse_iso_datetime_utc(parsed)
    except ValueError:
        return None


def _find_active_run_payload(username: str) -> dict[str, Any] | None:
    for payload in list_runs_payloads(username=username):
        status = str(payload.get("status", "")).strip().lower()
        if status in {"queued", "running"}:
            return payload
    return None


def _ensure_no_active_run(username: str) -> None:
    active = _find_active_run_payload(username)
    if not active:
        return

    active_id = str(active.get("run_id", "unknown"))
    active_status = str(active.get("status", "running"))
    raise RuntimeError(
        f"Only one run is allowed at a time. Active run {active_id} is currently {active_status}."
    )
