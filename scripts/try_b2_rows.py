"""Diagnostic: map real sheet rows, normalize, and run B2 check_shipment.

Run with B2 credentials in the environment (the same ones set on Render):

    B2_CUSTOMER_CODE=... B2_CUSTOMER_PASSWORD=... python scripts/try_b2_rows.py

It does NOT save anything to B2 (check only). For each row it prints whether B2
accepts the shipment and, if not, which fields B2 complains about.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import b2cloud
import b2cloud.utilities
from scripts.orders_csv import create_shipment, login_from_env
from scripts.order_payment import prepare_form_order

# Sheet display header -> internal field name.
COLUMN_MAP = {
    "Name": "consignee_name",
    "Postcode": "consignee_zip_code",
    "Address": "consignee_address_full",
    "Mobile": "consignee_telephone_display",
    "Email": "notification_email_address",
    "Date": "delivery_date",
    "Time": "delivery_time_zone",
    "Product Number": "product_number",
    "Type of transaction": "type_of_transaction",
    "Bank Account": "bank_account",
    "Order Date": "order_date",
    "Thanh toán": "payment_status",
    "Giao hàng": "delivery_status",
    "Mã vận đơn": "tracking_number",
    "Ghi chú": "note",
    "Số tiền đặt cọc": "deposit_amount",
}

# Two real rows from the sheet (display headers).
ROWS = [
    {
        "Name": "Naziha Al Sakinah",
        "Postcode": "762-0025",
        "Address": "香川県坂出市川津町2126番地1永井新宿舎A棟101号",
        "Mobile": "82213012108",
        "Email": "nazihaas1999@gmail.com",
        "Date": "08/04/2026",
        "Time": "09:00~12:00",
        "Product Number": "COD_iPad 11 128GB WIFI BNIB blue - 61300",
        "Type of transaction": "Daibiki",
        "Order Date": "2026/04/05",
        "Mã vận đơn": "311247036166",
    },
    {
        "Name": "fabian dani pratama",
        "Postcode": "7815602",
        "Address": "kochi ken konan shi yasucho chigire 961-11 nojima beikokuten",
        "Mobile": "",
        "Date": "07/04/2026",
        "Time": "18.00-20.00",
        "Product Number": "COD - iPhone 17 512GB BNIB Sage - 167300",
        "Type of transaction": "Daibiki",
        "Order Date": "2026/04/06",
        "Mã vận đơn": "311247036170",
    },
]


def map_row(display_row):
    return {COLUMN_MAP[k]: v for k, v in display_row.items() if k in COLUMN_MAP}


def to_iso_date(value):
    """DD/MM/YYYY -> YYYY/MM/DD; passes through YYYY/MM/DD."""
    value = (value or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value)
    if m:
        d, mo, y = m.groups()
        return f"{y}/{int(mo):02d}/{int(d):02d}"
    return value


def split_address(session, postcode, full_address):
    code = re.sub(r"\D", "", postcode or "")
    a1 = a2 = ""
    rest = full_address or ""
    try:
        feed = b2cloud.utilities.get_postal(session, code)
        postal = b2cloud.utilities.choice_postal(feed, full_address)
        if postal:
            a1 = postal["address"]["address1"]
            a2 = postal["address"]["address2"]
            for piece in (a1, a2):
                if piece and rest.startswith(piece):
                    rest = rest[len(piece):]
    except Exception as exc:  # postcode lookup failed -> let B2 report the gap
        print(f"    (get_postal failed for {code}: {exc})")
    return a1, a2, rest or full_address


def build_row(session, display_row, index):
    row = map_row(display_row)
    row["order_id"] = f"TEST-{index+1:03d}"
    row["consignee_zip_code"] = re.sub(r"\D", "", row.get("consignee_zip_code", ""))
    row["delivery_date"] = to_iso_date(row.get("delivery_date"))
    row["shipment_date"] = to_iso_date(row.get("order_date")) or row["delivery_date"]

    a1, a2, a3 = split_address(
        session, display_row.get("Postcode"), row.pop("consignee_address_full", "")
    )
    row["consignee_address1"], row["consignee_address2"], row["consignee_address3"] = a1, a2, a3

    # Ignore any existing tracking number so B2 actually re-checks the data.
    row.pop("tracking_number", None)

    error = prepare_form_order(row)
    if error:
        print(f"    local payment error: {error}")
    return row


def main():
    session = login_from_env()
    for index, display_row in enumerate(ROWS):
        print(f"\n=== Row {index+1}: {display_row['Name']} ===")
        row = build_row(session, display_row, index)
        print(
            f"    service_type={row.get('service_type')} label_type={row.get('label_type')} "
            f"amount={row.get('amount')} item={row.get('item_name1')!r}"
        )
        print(
            f"    addr1={row.get('consignee_address1')!r} addr2={row.get('consignee_address2')!r} "
            f"addr3={row.get('consignee_address3')!r}"
        )
        shipment = create_shipment(row)
        result = b2cloud.check_shipment(session, shipment)
        if result["success"]:
            print("    B2: OK (no errors)")
        else:
            print("    B2 ERRORS:")
            for err in result["errors"]:
                print(f"      - {err}")


if __name__ == "__main__":
    main()
