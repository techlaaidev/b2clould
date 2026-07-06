"""Derive Yamato payment fields from the business order form.

Maps three raw form columns to the values B2 needs:
- Product Number (#9)       -> item_name1 + total price
- Type of transaction (#10) -> payment kind (Daibiki = COD / BankTransfer = prepaid)
- Thanh toan status (#14) + So tien dat coc (#18) -> COD collect amount (代引金額)

Money decisions are driven ONLY by Type of transaction, never by the text
prefix inside Product Number (the prefix is a human label and is ignored).
"""

import logging
import os
import re
from datetime import datetime

logger = logging.getLogger("b2cloud.order_payment")

# 送り状種類 (label type) codes. Daibiki ships 宅急便コレクト (代引/COD, code 2):
# Yamato collects the 代引金額 (product price) from the receiver on delivery and
# remits it to the shop. BankTransfer is paid up front, so it ships 発払い (prepaid).
SERVICE_TYPE_PREPAID = "0"   # 発払い
SERVICE_TYPE_COD = "2"       # 宅急便コレクト / 代引 — Yamato collects product price (Daibiki)
FORM_PRINT_TYPE = "m5"

# Shipper fields copied from the account's registered Sender Master.
SHIPPER_FIELDS = [
    "shipper_code", "shipper_name", "shipper_name_kana", "shipper_telephone_display",
    "shipper_zip_code", "shipper_address1", "shipper_address2", "shipper_address3",
    "shipper_address4",
]
_SHIPPER_CACHE = {}

# Exact cell values used in the sheet.
DAIBIKI = "Daibiki"
BANK_TRANSFER = "BankTransfer"
DEPOSIT_MARKER = "DP"            # Thanh toan = DP  -> Daibiki with a deposit
PAID_MARKER = "Đã chuyển khoản"  # Thanh toan = paid -> BankTransfer completed

# Trailing price: last number after the final '-' with an optional 'y'/¥ suffix.
_TRAILING_PRICE = re.compile(r"-\s*([\d.,]+)\s*[y¥]?\s*$", re.IGNORECASE)
# Leading human payment label to strip from the item name (COD_, CK -, TF-, ...).
_LEADING_LABEL = re.compile(r"^(cod|ck|tf|dp|db)[\s_:.\-]+", re.IGNORECASE)


def _to_int(value):
    digits = re.sub(r"[.,\s]", "", str(value or ""))
    return int(digits) if digits.isdigit() else None


def parse_product_number(text):
    """Split a Product Number cell into (item_name, total_price).

    total_price is the trailing number after the final '-' (an optional 'y'/¥
    suffix is ignored) as int, or None when no trailing price is found.
    item_name is the remaining text with the leading payment label and the
    trailing price removed.
    """
    raw = (text or "").strip()
    price = None
    name_part = raw
    match = _TRAILING_PRICE.search(raw)
    if match:
        price = _to_int(match.group(1))
        name_part = raw[: match.start()].strip()
    name = _LEADING_LABEL.sub("", name_part).strip(" -_")
    return name, price


def compute_cod_amount(type_of_transaction, payment_status, deposit, total_price):
    """Return (amount, error).

    amount: integer yen to collect on delivery (代引金額); 0 for prepaid.
    error: a non-empty message when the row is invalid, else "".

    Rules (keyed only on Type of transaction):
      Daibiki (COD):
        status blank -> collect full total_price
        status DP    -> collect total_price - deposit (deposit is required)
      BankTransfer (prepaid):
        status "Đã chuyển khoản" -> collect 0 (already paid)
        status blank             -> invalid (not paid yet, do not ship)
    """
    ttype = (type_of_transaction or "").strip()
    status = (payment_status or "").strip()

    if ttype == DAIBIKI:
        if total_price is None:
            return 0, "Khong doc duoc gia tong tu Product Number"
        if status == "":
            return total_price, ""
        if status.upper() == DEPOSIT_MARKER:
            deposit_value = _to_int(deposit)
            if deposit_value is None:
                return 0, "Daibiki danh dau DP nhung thieu so tien dat coc (#18)"
            if deposit_value > total_price:
                return 0, "So tien dat coc lon hon gia tong"
            return total_price - deposit_value, ""
        return 0, f"Trang thai thanh toan khong hop le cho Daibiki: {status}"

    if ttype == BANK_TRANSFER:
        if status == PAID_MARKER:
            return 0, ""
        if status == "":
            return 0, "BankTransfer chua chuyen khoan"
        return 0, f"Trang thai thanh toan khong hop le cho BankTransfer: {status}"

    return 0, f"Type of transaction khong hop le: {type_of_transaction!r}"


def derive_payment_fields(row):
    """Fill item_name1 / payment_method / amount from the business form columns.

    Returns an error message string ("" when valid). No-op (returns "") when
    type_of_transaction is blank, so rows that already use the clean English
    columns (payment_method/cod_amount) are left untouched.
    """
    ttype = (row.get("type_of_transaction") or "").strip()
    if not ttype:
        return ""

    item_name, total_price = parse_product_number(row.get("product_number"))
    if item_name and not (row.get("item_name1") or "").strip():
        row["item_name1"] = item_name

    if ttype == DAIBIKI:
        # Ships 着払い (service_type 5): the receiver pays the delivery fee to
        # Yamato. Yamato does NOT collect the product price, so there is no
        # 代引金額 — amount/cod_amount stay empty (mirrors a working 着払い order).
        row["payment_method"] = "Chakubarai"
        row["label_type"] = "Chakubarai"
        row["amount"] = ""
        row["cod_amount"] = ""
        return ""

    # BANK_TRANSFER, already confirmed paid (else compute returns an error)
    amount, error = compute_cod_amount(
        ttype,
        row.get("payment_status"),
        row.get("deposit_amount"),
        total_price,
    )
    if error:
        return error
    row["payment_method"] = "BANK_TRANSFER"
    row["label_type"] = "Prepaid"
    row["amount"] = "0"
    row["bank_transfer_confirmed"] = "yes"
    return ""


def normalize_delivery_date(value):
    """Convert a delivery date to B2 format (YYYY/MM/DD).

    Accepts DD/MM/YYYY or YYYY/MM/DD. Returns "" when unparseable or in the past
    (delivery_date is optional; B2 then uses its "shortest day" default).
    """
    text = (value or "").strip()
    if not text:
        return ""
    parsed = None
    for fmt in ("%d/%m/%Y", "%Y/%m/%d", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if parsed is None or parsed.date() < datetime.now().date():
        return ""
    return parsed.strftime("%Y/%m/%d")


# Yamato B2 delivery time-zone codes (配達時間帯). "" = no preference.
TIME_ZONE_CODES = {"", "0812", "1416", "1618", "1820", "1921"}
_TIME_SEP = re.compile(r"[~〜\-–—―]")


def normalize_delivery_time(value):
    """Convert a free-text delivery time to a Yamato B2 time-zone code.

    The sheet's Time column holds human text ("09:00~12:00", "18.00–20.00");
    B2 only accepts its slot codes. Maps the text to the matching slot, passes
    a valid code through unchanged, and returns "" (no preference) when the
    text doesn't map to any slot.

    Slots: 0812=午前中, 1416=14-16, 1618=16-18, 1820=18-20, 1921=19-21.
    """
    text = (value or "").strip()
    if text in TIME_ZONE_CODES:
        return text
    if "午前" in text:
        return "0812"

    parts = _TIME_SEP.split(text)

    def first_hour(part):
        match = re.search(r"\d{1,2}", part or "")
        return int(match.group()) if match else None

    start = first_hour(parts[0])
    end = first_hour(parts[1]) if len(parts) > 1 else start
    if start is None:
        return ""
    if start < 12 or (end is not None and end <= 12):
        return "0812"
    if start in (14, 15):
        return "1416"
    if start in (16, 17):
        return "1618"
    if start == 18:
        return "1820"
    if start >= 19:
        return "1921"
    return ""  # 12-14 slot no longer exists in 宅急便


def prepare_form_order(row):
    """Turn a business-form row into a ready Yamato 宅急便 row.

    Sets service_type/print_type for non-DM, then derives the payment fields.
    Returns an error message ("" when valid). No-op (returns "") when
    type_of_transaction is blank, so legacy rows that use the clean English
    columns are untouched.

    Shipper / invoice are not enforced here: B2 fills the sender from the
    logged-in account, and check_shipment is the source of truth for anything
    it actually requires.
    """
    ttype = (row.get("type_of_transaction") or "").strip()
    if not ttype:
        return ""
    row["delivery_date"] = normalize_delivery_date(row.get("delivery_date"))
    row["delivery_time_zone"] = normalize_delivery_time(row.get("delivery_time_zone"))
    row["service_type"] = SERVICE_TYPE_CHAKUBARAI if ttype == DAIBIKI else SERVICE_TYPE_PREPAID
    if (row.get("print_type") or "").strip() in ("", "3", "0", "2"):
        row["print_type"] = FORM_PRINT_TYPE
    if ttype == BANK_TRANSFER and not (row.get("bank_account") or "").strip():
        return "BankTransfer thiếu Back account (#11)"
    return derive_payment_fields(row)


# Leading banchi part: digits / fullwidth digits / hyphens / 番地号丁目の.
_BANCHI_RE = re.compile(r"^([0-9０-９\-－―ー\s番地号丁目の]+)(.*)$")

# Tách tỉnh/thành từ địa chỉ Nhật khi API bưu điện B2 không trả kết quả.
# Tỉnh (address1): 都道府県 (đặc biệt 北海道, 京都府/大阪府). Thành phố/quận (address2): tới 市/区/郡 đầu tiên.
_PREF_RE = re.compile(r"^(北海道|東京都|(?:京都|大阪)府|.{1,4}?県)(.*)$")
_CITY_RE = re.compile(r"^(.+?[市区郡])(.*)$")


def _split_jp_prefecture_city(full):
    """Regex fallback: (prefecture, city, rest) từ địa chỉ Nhật, không cần API.
    Trả ("", "", full) khi không khớp mẫu tỉnh/thành."""
    m = _PREF_RE.match(full)
    if not m:
        return "", "", full
    pref, rest = m.group(1), m.group(2)
    mc = _CITY_RE.match(rest)
    if not mc:
        return pref, "", rest
    return pref, mc.group(1), mc.group(2)


def split_consignee_address(session, postcode, full_address):
    """Split a combined Japanese address into (address1, address2, address3, address4).

    Uses B2's postal lookup for prefecture/city/town, then a heuristic to separate
    the banchi (street number) from the building name so address3 stays within
    B2's length limit (building goes to address4). Nếu API bưu điện B2 lỗi/rỗng
    (address1 hoặc address2 trống), fallback sang tách bằng regex (_split_jp_prefecture_city).
    """
    full = (full_address or "").strip()
    code = re.sub(r"\D", "", postcode or "")
    a1 = a2 = town = ""
    try:
        import b2cloud.utilities
        feed = b2cloud.utilities.get_postal(session, code)
        postal = b2cloud.utilities.choice_postal(feed, full)
        if postal:
            a1 = postal["address"]["address1"]
            a2 = postal["address"]["address2"]
            town = postal["address"]["address3"]
    except Exception as exc:
        # KHÔNG nuốt lỗi lặng lẽ nữa — log để thấy vì sao tra bưu điện thất bại.
        logger.warning("Tra bưu điện B2 lỗi cho mã '%s': %s", code, exc)

    # Fallback regex khi API không cho tỉnh/thành (nguyên nhân gốc của INVALID:2).
    if not a1 or not a2:
        r1, r2, _ = _split_jp_prefecture_city(full)
        if not a1:
            a1 = r1
        if not a2:
            a2 = r2
        if not a1 or not a2:
            logger.warning("Không tách được tỉnh/thành từ địa chỉ: %r (mã bưu điện %s)", full, code)

    rest = full
    for piece in (a1, a2):
        if piece and rest.startswith(piece):
            rest = rest[len(piece):]
    if town and rest.startswith(town):
        rest = rest[len(town):]
    match = _BANCHI_RE.match(rest)
    banchi = match.group(1).strip() if match else rest
    building = match.group(2).strip() if match else ""
    address3 = (town + banchi).strip() or rest
    return a1, a2, address3, building


def apply_account_defaults(session, row):
    """Fill shipper + invoice for a non-DM form order from the B2 account.

    - shipper_* come from the account's registered Sender Master (依頼主マスタ),
      fetched once and cached, so the user never types sender info.
    - invoice_code defaults to B2_INVOICE_CODE or the login customer code; the
      billing "-01" suffix is invoice_freight_no (運賃管理番号), default "01".
    No-op for rows without type_of_transaction (legacy / DM rows).
    """
    if not (row.get("type_of_transaction") or "").strip():
        return

    # Split a combined consignee address when the split fields are empty.
    if not (row.get("consignee_address1") or "").strip() and (row.get("consignee_address") or "").strip():
        a1, a2, a3, a4 = split_consignee_address(
            session, row.get("consignee_zip_code"), row.get("consignee_address")
        )
        row["consignee_address1"] = a1
        row["consignee_address2"] = a2
        row["consignee_address3"] = a3
        if a4 and not (row.get("consignee_address4") or "").strip():
            row["consignee_address4"] = a4

    if "shipper" not in _SHIPPER_CACHE:
        try:
            import b2cloud.utilities
            _SHIPPER_CACHE["shipper"] = b2cloud.utilities.get_shipper(session)
        except Exception:
            _SHIPPER_CACHE["shipper"] = {}
    shipper = _SHIPPER_CACHE["shipper"]
    for field in SHIPPER_FIELDS:
        if shipper.get(field) and not (row.get(field) or "").strip():
            row[field] = shipper[field]

    if not (row.get("invoice_code") or "").strip():
        row["invoice_code"] = (
            os.environ.get("B2_INVOICE_CODE", "").strip()
            or os.environ.get("B2_CUSTOMER_CODE", "").strip()
        )
    if not (row.get("invoice_freight_no") or "").strip():
        row["invoice_freight_no"] = os.environ.get("B2_INVOICE_FREIGHT_NO", "01").strip()
