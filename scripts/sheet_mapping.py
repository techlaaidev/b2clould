"""Map Google Sheet display headers <-> internal snake_case fields.

The sheet keeps its human headers (Name, Address, Type of transaction, ...);
this layer translates them to the internal fields the pipeline uses, and
translates results back to the sheet's status/error columns for write-back.
"""

import hashlib
import re

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
# Chỉ nhận đúng "YAMATO" — cách viết cũ "JAMATO" đã bị loại bỏ (menu
# "Sửa dropdown Đơn vị giao hàng" trên sheet tự đổi JAMATO -> YAMATO).
CARRIER_YAMATO = {"YAMATO"}
CARRIER_JAPANPOST = "JAPANPOST"

# Internal status -> "Trạng thái khởi tạo". Phải khớp ĐÚNG chữ hoa/thường với
# dropdown trên sheet: "Đã tạo đơn" / "Chờ tạo đơn" / "Không tạo đơn".
# "Đã tạo đơn" chỉ khi đơn đã được XÁC NHẬN có trên Yamato B2 (tra thấy trong
# lịch sử, có mã vận đơn thật). Đã phát hành nhưng Yamato chưa ghi nhận xong
# (PENDING) hoặc mới lưu nháp (SAVED) đều là "Chờ tạo đơn".
STATUS_VI = {
    "CREATED": "Đã tạo đơn",
    "PENDING": "Chờ tạo đơn",
    "SAVED": "Chờ tạo đơn",
    "READY": "Chờ tạo đơn",
    "NEW": "Chờ tạo đơn",
    "INVALID": "Không tạo đơn",
    "ERROR": "Không tạo đơn",
    "SKIPPED": "Không tạo đơn",
}

# Internal status -> "Trạng thái tạo đơn hàng tự động trên yamato".
# Không có trong map -> giữ nguyên giá trị đang có trên sheet.
YAMATO_AUTO_STATUS_VI = {
    "CREATED": "Thành công",
    "PENDING": "Đang chờ Yamato xác nhận",
    "INVALID": "Thất bại",
    "ERROR": "Thất bại",
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


# Internal field -> the sheet column the user actually edits. Split/derived
# fields (address1/2/3, item_name1, shipment_date) point back at their source
# column so a missing-field error names a cell the user can fix.
FIELD_TO_HEADER = {
    "consignee_name": "Name",
    "consignee_zip_code": "Postcode",
    "consignee_address": "Address",
    "consignee_address1": "Address",
    "consignee_address2": "Address",
    "consignee_address3": "Address",
    "consignee_telephone_display": "Mobile",
    "shipment_date": "Date",
    "delivery_date": "Date",
    "delivery_time_zone": "Time",
    "product_number": "Product Number",
    "item_name1": "Product Number",
    "type_of_transaction": "Type of transaction",
    "bank_account": "Back account",
    "order_date": "Order Date",
    "payment_status": "Thanh toán",
    "deposit_amount": "Số tiền đặt cọc",
    "carrier": "Đơn vị giao hàng",
}


def _offending_fields(error):
    """Every internal field named in a (possibly multi-part) error message."""
    fields = re.findall(r"([a-z_][a-z_0-9]*) is required", error)
    fields += re.findall(r"'error_property_name': '([^']+)'", error)
    return fields


# Từ khoá trong thông điệp lỗi tiếng Việt -> cột trên sheet cần sửa, để cột
# "Cột bị lỗi" luôn chỉ đúng chỗ dù lỗi không theo dạng "X is required".
_KEYWORD_COLUMNS = [
    ("Product Number", "Product Number"),
    ("đặt cọc", "Số tiền đặt cọc"),
    ("Thanh toán", "Thanh toán"),
    ("chuyển khoản", "Thanh toán"),
    ("Type of transaction", "Type of transaction"),
    ("Bank Account", "Bank Account"),
    ("Đơn vị giao hàng", "Đơn vị giao hàng"),
]


def _error_columns(error):
    """Comma-joined sheet columns the user must fix, in order, no duplicates."""
    cols = []
    for field in _offending_fields(error):
        header = FIELD_TO_HEADER.get(field, field)
        if header and header not in cols:
            cols.append(header)
    # Address-split failure has no "X is required" marker but is an Address issue.
    if ("tách được" in error or "consignee_address" in error) and "Address" not in cols:
        cols.append("Address")
    for keyword, header in _KEYWORD_COLUMNS:
        if keyword in error and header not in cols:
            cols.append(header)
    return ", ".join(cols)


# Cụm từ tiếng Nhật hay gặp trong error_description của Yamato B2 -> tiếng Việt.
_B2_DESC_VI = [
    ("長すぎ", "quá dài"),
    ("入力してください", "đang bị thiếu"),
    ("入力して下さい", "đang bị thiếu"),
    ("必須", "đang bị thiếu"),
    ("正しくありません", "không hợp lệ"),
    ("不正", "không hợp lệ"),
    ("誤り", "không hợp lệ"),
    ("存在しません", "không tồn tại"),
    ("利用できません", "không dùng được (tài khoản chưa đăng ký dịch vụ này)"),
    ("契約", "tài khoản chưa đăng ký dịch vụ này"),
]


def format_b2_error(error):
    """Một lỗi Yamato B2 (dict hoặc chuỗi) -> (thông điệp tiếng Việt, cột trên sheet).

    Lỗi B2 dạng {'error_property_name': ..., 'error_code': 'ESxxxxxx',
    'error_description': '<tiếng Nhật>'}; người dùng cuối chỉ cần biết CỘT nào
    bị lỗi và lỗi GÌ bằng tiếng Việt — mã ES giữ lại để tra cứu khi cần.
    """
    if isinstance(error, dict):
        prop = str(error.get("error_property_name") or "").strip()
        code = str(error.get("error_code") or "").strip()
        desc = str(error.get("error_description") or "").strip()
    else:
        text = str(error or "")

        def _pick(key):
            match = re.search(rf"'{key}':\s*'([^']*)'", text)
            return match.group(1).strip() if match else ""

        prop = _pick("error_property_name")
        code = _pick("error_code")
        desc = _pick("error_description")
        if not (prop or code or desc):
            return text, _error_columns(text)

    reason = next((vi for key, vi in _B2_DESC_VI if key in desc), "bị Yamato từ chối")
    column = FIELD_TO_HEADER.get(prop, prop)
    message = f"Cột {column}: dữ liệu {reason}" if column else f"Dữ liệu {reason}"
    if code:
        message += f" (mã lỗi Yamato {code})"
    return message, column


def b2_errors_to_vi(errors):
    """Danh sách lỗi Yamato B2 -> ("lỗi 1; lỗi 2", "Cột A, Cột B") tiếng Việt."""
    messages = []
    columns = []
    for error in errors or []:
        message, column = format_b2_error(error)
        if message and message not in messages:
            messages.append(message)
        for col in (column or "").split(","):
            col = col.strip()
            if col and col not in columns:
                columns.append(col)
    return "; ".join(messages), ", ".join(columns)


def _vi_error(error):
    """Vietnamese-friendly error text. Missing-field lines name the sheet column;
    other messages (B2 API errors, address split) pass through unchanged."""
    parts = [p.strip() for p in error.split(";") if p.strip()]
    out = []
    for part in parts:
        match = re.match(r"([a-z_][a-z_0-9]*) is required", part)
        if match:
            col = FIELD_TO_HEADER.get(match.group(1), match.group(1))
            part = f"Thiếu trường bắt buộc: {col}"
        if part not in out:  # collapse duplicates (e.g. address3 + address both -> Address)
            out.append(part)
    return "; ".join(out)


def map_output_row(row):
    """Translate an internal result row into the sheet's status/error columns."""
    status = (row.get("status") or "").upper()
    error = row.get("error_message") or ""
    out = {
        "Mã vận đơn": row.get("tracking_number", ""),
        "Trạng thái khởi tạo": STATUS_VI.get(status, ""),
        "Cột bị lỗi": row.get("error_column", "") or _error_columns(error),
        "Tên lỗi": _vi_error(error),
    }
    auto_status = YAMATO_AUTO_STATUS_VI.get(status)
    if auto_status:
        out["Trạng thái tạo đơn hàng tự động trên yamato"] = auto_status
    if row.get("tracking_csv_url"):
        out["Link url file csv xử lí mã vận đơn"] = row["tracking_csv_url"]
    if row.get("pdf_url"):
        out["pdf_url"] = row["pdf_url"]
    return out
