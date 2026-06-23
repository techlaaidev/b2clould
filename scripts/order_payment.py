"""Derive Yamato payment fields from the business order form.

Maps three raw form columns to the values B2 needs:
- Product Number (#9)       -> item_name1 + total price
- Type of transaction (#10) -> payment kind (Daibiki = COD / BankTransfer = prepaid)
- Thanh toan status (#14) + So tien dat coc (#18) -> COD collect amount (代引金額)

Money decisions are driven ONLY by Type of transaction, never by the text
prefix inside Product Number (the prefix is a human label and is ignored).
"""

import os
import re
from datetime import datetime

# Form orders are always 宅急便 (non-DM): BankTransfer ships 発払い, Daibiki COD.
FORM_SERVICE_TYPE = "0"
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

    amount, error = compute_cod_amount(
        ttype,
        row.get("payment_status"),
        row.get("deposit_amount"),
        total_price,
    )
    if error:
        return error

    if ttype == DAIBIKI:
        row["payment_method"] = "COD"
        row["label_type"] = "COD"
        row["amount"] = str(amount)
        row["cod_amount"] = str(amount)
    else:  # BANK_TRANSFER, already confirmed paid (else compute returned an error)
        row["payment_method"] = "BANK_TRANSFER"
        row["label_type"] = "Prepaid"
        row["amount"] = "0"
        row["bank_transfer_confirmed"] = "yes"
    return ""


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
    row["service_type"] = FORM_SERVICE_TYPE
    if (row.get("print_type") or "").strip() in ("", "3", FORM_SERVICE_TYPE):
        row["print_type"] = FORM_PRINT_TYPE
    if ttype == BANK_TRANSFER and not (row.get("bank_account") or "").strip():
        return "BankTransfer thiếu Back account (#11)"
    return derive_payment_fields(row)


# Leading banchi part: digits / fullwidth digits / hyphens / 番地号丁目の.
_BANCHI_RE = re.compile(r"^([0-9０-９\-－―ー\s番地号丁目の]+)(.*)$")


def split_consignee_address(session, postcode, full_address):
    """Split a combined Japanese address into (address1, address2, address3, address4).

    Uses B2's postal lookup for prefecture/city/town, then a heuristic to separate
    the banchi (street number) from the building name so address3 stays within
    B2's length limit (building goes to address4).
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
    except Exception:
        pass
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
