import base64
import logging
import os
import threading
import time
import traceback
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import b2cloud
from scripts.orders_csv import OUTPUT_COLUMNS, create_shipment, validate_local
from scripts.order_payment import apply_account_defaults
from scripts.sheet_mapping import (
    CARRIER_YAMATO,
    generate_order_id,
    map_input_row,
    map_output_row,
)


app = FastAPI(title="B2 Cloud API", version="1.0.0")
logger = logging.getLogger("b2cloud.api")

_SESSION = None
_SESSION_LOCK = threading.RLock()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled error for %s %s: %s\n%s",
        request.method,
        request.url.path,
        exc,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc) or exc.__class__.__name__,
            "error_type": exc.__class__.__name__,
        },
    )


class RowsRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)


class CreateOrdersRequest(RowsRequest):
    issue_pdf: bool = True
    include_pdf_base64: bool = True


class TrackingRequest(BaseModel):
    view: str = "history"
    service_type: str = ""
    consignee_name: str = ""
    tracking_number: str = ""


def require_api_key(x_api_key: str = Header(default="")):
    expected = os.environ.get("B2_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="B2_API_KEY is not configured.")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key.")


def b2_credentials() -> tuple[str, str, str, str]:
    code = os.environ.get("B2_CUSTOMER_CODE", "").strip()
    password = os.environ.get("B2_CUSTOMER_PASSWORD", "").strip()
    cls_code = os.environ.get("B2_CUSTOMER_CLS_CODE", "").strip()
    login_user = os.environ.get("B2_LOGIN_USER_ID", "").strip()
    if not code or not password:
        raise HTTPException(
            status_code=500,
            detail="B2_CUSTOMER_CODE and B2_CUSTOMER_PASSWORD are not configured.",
        )
    return code, password, cls_code, login_user


def get_b2_session(force_login: bool = False):
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is not None and not force_login:
            return _SESSION
        _SESSION = b2cloud.login(*b2_credentials())
        return _SESSION


def with_b2_session(operation):
    with _SESSION_LOCK:
        session = get_b2_session()
        try:
            return operation(session)
        except HTTPException:
            raise
        except Exception as first_error:
            logger.warning("B2 operation failed; retrying after login: %s", first_error)
            session = get_b2_session(force_login=True)
            return operation(session)


def feed_entries(feed: dict[str, Any]) -> list[dict[str, Any]]:
    entries = feed.get("feed", {}).get("entry", [])
    if isinstance(entries, dict):
        return [entries]
    return entries or []


def normalize_order_row(row: dict[str, Any]) -> dict[str, str]:
    normalized = {column: str(row.get(column, "") or "").strip() for column in OUTPUT_COLUMNS}
    if not normalized["order_id"]:
        normalized["order_id"] = generate_order_id(normalized)
    if not normalized["status"]:
        normalized["status"] = "NEW"
    if not normalized["service_type"]:
        normalized["service_type"] = "3"
    if not normalized["shipment_date"]:
        normalized["shipment_date"] = datetime.now().strftime("%Y/%m/%d")
    if not normalized["print_type"]:
        normalized["print_type"] = normalized["service_type"]
    if not normalized["is_using_center_service"]:
        normalized["is_using_center_service"] = "0"
    return normalized


def set_order_error(row: dict[str, str], message: str, status: str = "INVALID"):
    row["status"] = status
    row["error_message"] = message
    row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return row


def extract_tracking(feed: dict[str, Any]) -> str:
    for entry in feed_entries(feed):
        tracking = entry.get("shipment", {}).get("tracking_number", "")
        if tracking:
            return tracking
    return ""


def matching_order_entries(feed: dict[str, Any], order_id: str) -> list[dict[str, Any]]:
    matches = []
    for entry in feed_entries(feed):
        shipment = entry.get("shipment", {})
        if str(shipment.get("shipment_number", "")).strip() == order_id:
            matches.append(entry)
    return matches


def extract_tracking_for_order(feed: dict[str, Any], order_id: str) -> str:
    for entry in matching_order_entries(feed, order_id):
        tracking = entry.get("shipment", {}).get("tracking_number", "")
        if tracking:
            return tracking
    return ""


def history_params(
    service_type: str = "",
    consignee_name: str = "",
    tracking_number: str = "",
) -> dict[str, str]:
    params = {}
    if service_type:
        params["service_type"] = service_type
    if consignee_name:
        params["consignee_name"] = consignee_name
    if tracking_number:
        params["tracking_number"] = tracking_number
    return params


def load_entries(session, view: str, params: dict[str, str]):
    if view == "new":
        feed = b2cloud.get_new(session, params=params or None)
    elif view == "deleted":
        feed = b2cloud.get_history_deleted(session)
    else:
        feed = b2cloud.search_history(session, **params)
    return feed_entries(feed), feed


def find_issued_tracking(session, row: dict[str, str]) -> str:
    """Look up the real tracking number B2 assigns when a draft is issued.

    print_issue replaces the UMN/OMN placeholder with the real 送り状番号, but
    B2's history is not indexed instantly. Retry with a short backoff so we
    return the real number instead of the placeholder. Searches by order_id
    (exact) first, then by the full consignee name (B2 matches full names only).
    """
    order_id = row.get("order_id", "")
    consignee_name = row.get("consignee_name", "")
    for attempt in range(6):
        if order_id:
            feed = b2cloud.search_history(session, shipment_number=order_id)
            tracking = extract_tracking_for_order(feed, order_id)
            if tracking:
                return tracking
        if consignee_name:
            feed = b2cloud.search_history(session, consignee_name=consignee_name)
            tracking = extract_tracking(feed)
            if tracking:
                return tracking
        time.sleep(1.5)
    return ""


def find_existing_shipment(session, row: dict[str, str]) -> tuple[str | None, str]:
    order_id = row.get("order_id", "")
    if not order_id:
        return None, ""

    history = b2cloud.search_history(session, shipment_number=order_id)
    history_entries = matching_order_entries(history, order_id)
    if history_entries:
        tracking = history_entries[0].get("shipment", {}).get("tracking_number", "")
        return "CREATED", tracking

    saved = b2cloud.get_new(session, params={"shipment_number": order_id})
    saved_entries = matching_order_entries(saved, order_id)
    if saved_entries:
        tracking = saved_entries[0].get("shipment", {}).get("tracking_number", "")
        return "SAVED", tracking

    return None, ""


def validate_order_rows(session, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    output = []
    for item in rows:
        row = normalize_order_row(map_input_row(item))
        if (row.get("carrier") or "").upper() not in CARRIER_YAMATO:
            row["status"] = "SKIPPED"
            row["error_message"] = "Đơn JAPANPOST - không xử lý trên Yamato"
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            output.append(row)
            continue
        if row.get("tracking_number"):
            row["status"] = "CREATED"
            row["error_message"] = ""
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            output.append(row)
            continue

        apply_account_defaults(session, row)
        errors = validate_local(row)
        if errors:
            output.append(set_order_error(row, "; ".join(errors)))
            continue

        try:
            existing_status, existing_tracking = find_existing_shipment(session, row)
        except Exception as exc:
            output.append(set_order_error(row, f"Failed to check existing shipment: {exc}", "ERROR"))
            continue

        if existing_status:
            row["status"] = existing_status
            row["tracking_number"] = existing_tracking
            row["error_message"] = "Order already exists in B2 Cloud."
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            output.append(row)
            continue

        shipment = create_shipment(row)
        result = b2cloud.check_shipment(session, shipment)
        if result["success"]:
            row["status"] = "READY"
            row["error_message"] = ""
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            row = set_order_error(row, "; ".join(str(error) for error in result["errors"]))
        output.append(row)
    for row in output:
        row.update(map_output_row(row))
    return output


def create_order_shipments(
    session,
    rows: list[dict[str, Any]],
    issue_pdf: bool,
    include_pdf_base64: bool,
) -> list[dict[str, str]]:
    output = []
    for item in rows:
        row = normalize_order_row(map_input_row(item))
        row["pdf_base64"] = ""
        if (row.get("carrier") or "").upper() not in CARRIER_YAMATO:
            row["status"] = "SKIPPED"
            row["error_message"] = "Đơn JAPANPOST - không xử lý trên Yamato"
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            output.append(row)
            continue
        if row.get("tracking_number"):
            row["status"] = "CREATED"
            row["error_message"] = ""
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            output.append(row)
            continue
        if row.get("status") not in {"READY", "NEW"}:
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            output.append(row)
            continue

        apply_account_defaults(session, row)
        errors = validate_local(row)
        if errors:
            output.append(set_order_error(row, "; ".join(errors)))
            continue

        try:
            existing_status, existing_tracking = find_existing_shipment(session, row)
            if existing_status == "CREATED":
                # Already issued in B2 (a real tracking number exists) — do not
                # re-create; just report the existing order.
                row["status"] = "CREATED"
                row["tracking_number"] = existing_tracking
                row["error_message"] = f"Order already issued in B2 Cloud: {row['order_id']}"
                row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                output.append(row)
                continue

            if existing_status == "SAVED":
                # A draft was saved earlier (未発行) but never issued. Reuse that
                # draft and issue it below instead of skipping it forever, so it
                # finally gets a real tracking number.
                saved = b2cloud.get_new(session, params={"shipment_number": row["order_id"]})
                saved = {"feed": {"entry": matching_order_entries(saved, row["order_id"])}}
            else:
                shipment = create_shipment(row)
                checked = b2cloud.post_new_checkonly(session, [shipment])
                checked_errors = feed_entries(checked)[0].get("error", []) if feed_entries(checked) else []
                if checked_errors:
                    output.append(set_order_error(row, "; ".join(str(error) for error in checked_errors)))
                    continue
                saved = b2cloud.post_new(session, checked)

            row["tracking_number"] = extract_tracking(saved)
            row["status"] = "SAVED"
            row["error_message"] = ""

            if issue_pdf:
                pdf_data = b2cloud.print_issue(
                    session,
                    row.get("print_type") or row["service_type"],
                    saved,
                )
                if include_pdf_base64:
                    row["pdf_base64"] = base64.b64encode(pdf_data).decode("ascii")
                    row["pdf_filename"] = f"{row['order_id'] or 'shipment'}.pdf"
                tracking = find_issued_tracking(session, row)
                if tracking:
                    row["tracking_number"] = tracking
                row["status"] = "CREATED"
            row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as exc:
            row = set_order_error(row, str(exc), status="ERROR")
        output.append(row)
    for row in output:
        row.update(map_output_row(row))
    return output


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/session/status", dependencies=[Depends(require_api_key)])
def session_status():
    return {"authorized": True, "b2_session_cached": _SESSION is not None}


@app.post("/api/session/login", dependencies=[Depends(require_api_key)])
def session_login():
    get_b2_session(force_login=True)
    return {"ok": True, "b2_session_cached": True}


@app.get("/api/entries", dependencies=[Depends(require_api_key)])
def entries(
    view: str = Query(default="history"),
    service_type: str = Query(default=""),
    consignee_name: str = Query(default=""),
    tracking_number: str = Query(default=""),
):
    params = history_params(service_type, consignee_name, tracking_number)
    return with_b2_session(lambda session: {"entries": load_entries(session, view, params)[0]})


@app.post("/api/tracking", dependencies=[Depends(require_api_key)])
def update_tracking(request: TrackingRequest):
    params = history_params(
        request.service_type,
        request.consignee_name,
        request.tracking_number,
    )

    def operation(session):
        entries, feed = load_entries(session, request.view, params)
        if not entries:
            return {"entries": []}
        updated = b2cloud.put_tracking(session, feed)
        return {"entries": feed_entries(updated)}

    return with_b2_session(operation)


@app.post("/api/orders/validate", dependencies=[Depends(require_api_key)])
def validate_orders(request: RowsRequest):
    if not isinstance(request.rows, list):
        raise HTTPException(status_code=400, detail="rows must be a list.")
    return with_b2_session(lambda session: {"rows": validate_order_rows(session, request.rows)})


@app.post("/api/orders/create", dependencies=[Depends(require_api_key)])
def create_orders(request: CreateOrdersRequest):
    if not isinstance(request.rows, list):
        raise HTTPException(status_code=400, detail="rows must be a list.")
    return with_b2_session(
        lambda session: {
            "rows": create_order_shipments(
                session,
                request.rows,
                request.issue_pdf,
                request.include_pdf_base64,
            )
        }
    )
