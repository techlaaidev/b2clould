import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import b2cloud
import b2cloud.utilities
from scripts.order_payment import prepare_form_order


REQUIRED_COLUMNS = [
    "order_id",
    "status",
    "tracking_number",
    "service_type",
    "shipment_date",
    "consignee_name",
    "consignee_telephone_display",
    "consignee_zip_code",
    "consignee_address1",
    "consignee_address2",
    "consignee_address3",
]

OUTPUT_COLUMNS = [
    # Internal management fields.
    "order_id",
    "status",
    "error_message",
    "tracking_number",
    "created_at",
    "updated_at",
    # Yamato shipment fields.
    "service_type",
    "print_type",
    "shipment_date",
    "delivery_date",
    "delivery_time_zone",
    "invoice_code",
    "invoice_code_ext",
    "invoice_freight_no",
    "invoice_name",
    "amount",
    "tax_amount",
    "package_qty",
    "consignee_name",
    "consignee_title",
    "consignee_name_kana",
    "consignee_code",
    "consignee_telephone_display",
    "consignee_telephone_ext",
    "consignee_zip_code",
    "consignee_address1",
    "consignee_address2",
    "consignee_address3",
    "consignee_address4",
    "consignee_department1",
    "consignee_department2",
    "is_using_center_service",
    "consignee_center_code",
    "consignee_center_name",
    "shipper_name",
    "shipper_title",
    "shipper_telephone_display",
    "shipper_zip_code",
    "shipper_address1",
    "shipper_address2",
    "shipper_address3",
    "shipper_address4",
    "shipper_name_kana",
    "item_name1",
    "item_name2",
    "handling_information1",
    "handling_information2",
    "note",
    # Internal payment control fields. These are not sent as-is to Yamato.
    "payment_method",
    "cod_amount",
    "bank_transfer_confirmed",
    # Business form inputs. Derived into the Yamato fields above by
    # order_payment.derive_payment_fields().
    "product_number",
    "type_of_transaction",
    "payment_status",
    "deposit_amount",
]

COMMON_REQUIRED = [
    "order_id",
    "service_type",
    "shipment_date",
    "consignee_name",
    "consignee_telephone_display",
    "consignee_zip_code",
    "consignee_address1",
    "consignee_address2",
    "consignee_address3",
]

NON_DM_REQUIRED = [
    "invoice_code",
    "invoice_freight_no",
    "shipper_name",
    "shipper_telephone_display",
    "shipper_zip_code",
    "shipper_address1",
    "shipper_address2",
    "shipper_address3",
    "item_name1",
]


def read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise RuntimeError("CSV file has no header row.")
        missing = [name for name in REQUIRED_COLUMNS if name not in reader.fieldnames]
        if missing:
            raise RuntimeError("Missing required columns: " + ", ".join(missing))
        return [normalize_row(row) for row in reader]


def normalize_row(row: dict) -> dict:
    normalized = {column: (row.get(column) or "").strip() for column in OUTPUT_COLUMNS}
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


def validate_local(row: dict) -> list[str]:
    errors = []
    payment_error = derive_payment_fields(row)
    if payment_error:
        errors.append(payment_error)

    for column in COMMON_REQUIRED:
        if not row.get(column):
            errors.append(f"{column} is required")

    if row.get("service_type") != "3":
        for column in NON_DM_REQUIRED:
            if not row.get(column):
                errors.append(f"{column} is required for service_type {row.get('service_type')}")

    if row.get("is_using_center_service") == "1":
        if not row.get("consignee_center_code"):
            errors.append("consignee_center_code is required when is_using_center_service=1")
        if not row.get("consignee_center_name"):
            errors.append("consignee_center_name is required when is_using_center_service=1")

    if row.get("payment_method", "").upper() == "COD" and not row.get("cod_amount"):
        errors.append("cod_amount is required for COD orders")
    if row.get("payment_method", "").upper() == "BANK_TRANSFER":
        confirmed = row.get("bank_transfer_confirmed", "").lower()
        if confirmed not in {"yes", "true", "1", "confirmed"}:
            errors.append("bank_transfer_confirmed is required for bank transfer orders")
    return errors


def create_shipment(row: dict) -> dict:
    if row["service_type"] == "3":
        return b2cloud.utilities.create_dm_shipment(
            shipment_date=row["shipment_date"],
            consignee_telephone_display=row["consignee_telephone_display"],
            consignee_name=row["consignee_name"],
            consignee_zip_code=row["consignee_zip_code"],
            consignee_address1=row["consignee_address1"],
            consignee_address2=row["consignee_address2"],
            consignee_address3=row["consignee_address3"],
            consignee_address4=row.get("consignee_address4", ""),
            consignee_department1=row.get("consignee_department1", ""),
            consignee_department2=row.get("consignee_department2", ""),
            shipment_number=row["order_id"],
            consignee_title=row.get("consignee_title", ""),
            consignee_name_kana=row.get("consignee_name_kana", ""),
            consignee_code=row.get("consignee_code", ""),
            is_using_center_service=row.get("is_using_center_service", "0"),
            consignee_center_code=row.get("consignee_center_code", ""),
            consignee_center_name=row.get("consignee_center_name", ""),
        )

    shipment = b2cloud.utilities.create_empty_shipment()
    data = shipment["shipment"]
    direct_fields = [
        "service_type",
        "shipment_date",
        "delivery_date",
        "delivery_time_zone",
        "invoice_code",
        "invoice_code_ext",
        "invoice_freight_no",
        "invoice_name",
        "amount",
        "tax_amount",
        "package_qty",
        "consignee_name",
        "consignee_title",
        "consignee_name_kana",
        "consignee_code",
        "consignee_telephone_display",
        "consignee_telephone_ext",
        "consignee_zip_code",
        "consignee_address1",
        "consignee_address2",
        "consignee_address3",
        "consignee_address4",
        "consignee_department1",
        "consignee_department2",
        "is_using_center_service",
        "consignee_center_code",
        "consignee_center_name",
        "shipper_name",
        "shipper_title",
        "shipper_telephone_display",
        "shipper_zip_code",
        "shipper_address1",
        "shipper_address2",
        "shipper_address3",
        "shipper_address4",
        "shipper_name_kana",
        "item_name1",
        "item_name2",
        "handling_information1",
        "handling_information2",
        "note",
    ]
    for field in direct_fields:
        data[field] = row.get(field, "")
    data["shipment_number"] = row["order_id"]
    data["consignee_telephone"] = row.get("consignee_telephone_display", "").replace("-", "")
    data["shipper_telephone"] = row.get("shipper_telephone_display", "").replace("-", "")
    return shipment


def login_from_env():
    code = os.environ.get("B2_CUSTOMER_CODE", "").strip()
    password = os.environ.get("B2_CUSTOMER_PASSWORD", "").strip()
    cls_code = os.environ.get("B2_CUSTOMER_CLS_CODE", "").strip()
    login_user = os.environ.get("B2_LOGIN_USER_ID", "").strip()
    if not code or not password:
        raise RuntimeError("Set B2_CUSTOMER_CODE and B2_CUSTOMER_PASSWORD first.")
    return b2cloud.login(code, password, cls_code, login_user)


def process_rows(rows: list[dict], check_b2: bool) -> list[dict]:
    session = login_from_env() if check_b2 else None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output = []

    for row in rows:
        if row.get("tracking_number"):
            row["status"] = "CREATED"
            row["error_message"] = ""
            row["updated_at"] = now
            output.append(row)
            continue

        errors = validate_local(row)
        if errors:
            row["status"] = "INVALID"
            row["error_message"] = "; ".join(errors)
            row["updated_at"] = now
            output.append(row)
            continue

        if check_b2:
            shipment = create_shipment(row)
            result = b2cloud.check_shipment(session, shipment)
            if result["success"]:
                row["status"] = "READY"
                row["error_message"] = ""
            else:
                row["status"] = "INVALID"
                row["error_message"] = "; ".join(str(error) for error in result["errors"])
        else:
            row["status"] = "READY"
            row["error_message"] = ""

        row["updated_at"] = now
        output.append(row)

    return output


def write_rows(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate B2 Cloud orders from CSV.")
    parser.add_argument("input", help="Input CSV exported from Excel or Google Sheets.")
    parser.add_argument("-o", "--output", default="orders_checked.csv", help="Output CSV path.")
    parser.add_argument("--check-b2", action="store_true", help="Also validate rows against B2 Cloud.")
    args = parser.parse_args()

    rows = read_rows(Path(args.input))
    processed = process_rows(rows, args.check_b2)
    write_rows(Path(args.output), processed)

    counts = {}
    for row in processed:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print("Done:", ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    print("Output:", args.output)


if __name__ == "__main__":
    main()
