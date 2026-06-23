"""Map Google Sheet display headers <-> internal snake_case fields.

The sheet keeps its human headers (Name, Address, Type of transaction, ...);
this layer translates them to the internal fields the pipeline uses, and
translates results back to the sheet's status/error columns for write-back.
"""

import hashlib

# Sheet header -> internal field (input direction).
INPUT_MAP = {
    "Name": "consignee_name",
    "Postcode": "consignee_zip_code",
    "Address": "consignee_address",
    "Mobile": "consignee_telephone_display",
    "Email": "notification_email_address",
    "Date": "delivery_date",
    "Time": "delivery_time_zone",
    "Product Number": "product_number",
    "Type of transaction": "type_of_transaction",
    "Back account": "bank_account",
    "Bank Account": "bank_account",
    "Orderdate": "order_date",
    "Order Date": "order_date",
    "Thanh toán": "payment_status",
    "Mã vận đơn": "tracking_number",
    "Ghi chú": "note",
    "Số tiền đặt cọc": "deposit_amount",
    "Đơn vị giao hàng": "carrier",
    "Link url file csv xử lí mã vận đơn": "tracking_csv_url",
}

# Carrier values that route through Yamato/B2. JAPANPOST is handled elsewhere.
CARRIER_YAMATO = {"JAMATO", "YAMATO", ""}
CARRIER_JAPANPOST = "JAPANPOST"

# Internal status -> "Trạng thái khởi tạo" (3 values).
STATUS_VI = {
    "CREATED": "đã tạo đơn",
    "SAVED": "đã tạo đơn",
    "READY": "chờ tạo đơn",
    "NEW": "chờ tạo đơn",
    "INVALID": "không tạo đơn",
    "ERROR": "không tạo đơn",
    "SKIPPED": "không tạo đơn",
}


def map_input_row(display_row):
    """Translate a sheet row (display headers) into internal snake_case fields."""
    internal = {}
    for header, value in display_row.items():
        field = INPUT_MAP.get((header or "").strip())
        if field:
            internal[field] = value
    return internal


def generate_order_id(row):
    """Stable id derived from row content, so dedup works across runs."""
    basis = "|".join([
        (row.get("consignee_name") or "").strip(),
        (row.get("consignee_telephone_display") or "").strip(),
        (row.get("product_number") or "").strip(),
        (row.get("order_date") or "").strip(),
    ])
    return "AUTO-" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def map_output_row(row):
    """Translate an internal result row into the sheet's status/error columns."""
    status = (row.get("status") or "").upper()
    error = row.get("error_message") or ""
    out = {
        "Mã vận đơn": row.get("tracking_number", ""),
        "Trạng thái khởi tạo": STATUS_VI.get(status, ""),
        "Cột bị lỗi": row.get("error_column", ""),
        "Tên lỗi": error,
    }
    if status in ("CREATED", "SAVED"):
        out["Trạng thái tạo đơn hàng tự động trên yamato"] = "Thành công"
    elif status == "ERROR":
        out["Trạng thái tạo đơn hàng tự động trên yamato"] = "thất bại"
    if row.get("tracking_csv_url"):
        out["Link url file csv xử lí mã vận đơn"] = row["tracking_csv_url"]
    if row.get("pdf_url"):
        out["pdf_url"] = row["pdf_url"]
    return out
