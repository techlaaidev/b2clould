import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.order_payment import (
    compute_cod_amount,
    derive_payment_fields,
    parse_product_number,
    prepare_form_order,
)
from scripts.orders_csv import normalize_row, validate_local


def _consignee_base(order_id, **extra):
    base = {
        "order_id": order_id,
        "service_type": "3",
        "shipment_date": "2026/06/23",
        "consignee_name": "Test",
        "consignee_telephone_display": "00-0000-0000",
        "consignee_zip_code": "1000001",
        "consignee_address1": "東京都",
        "consignee_address2": "千代田区",
        "consignee_address3": "千代田1-1",
    }
    base.update(extra)
    return base


def test_parse_strips_label_and_reads_trailing_price():
    name, price = parse_product_number("COD_iPad 11 128GB WIFI BNIB blue - 61300")
    assert name == "iPad 11 128GB WIFI BNIB blue"
    assert price == 61300


def test_parse_handles_no_space_dash_and_y_suffix():
    name, price = parse_product_number("COD-iphone 17 pro 256gb blue BNIB-211300y")
    assert name == "iphone 17 pro 256gb blue BNIB"
    assert price == 211300


def test_parse_keeps_inner_code_and_uses_last_number_as_price():
    name, price = parse_product_number(
        "CK - iPhone 15 pro 256gb white Likenew 98% pin 86% 25964- 109800y"
    )
    assert price == 109800
    assert "iPhone 15 pro" in name


def test_parse_row_without_label_prefix():
    name, price = parse_product_number(
        "iPhone 12 pro 128gb graphite rank B Bh 100% 64633 - 46300y"
    )
    assert price == 46300
    assert name.startswith("iPhone 12 pro")


def test_daibiki_no_deposit_collects_full_total():
    amount, error = compute_cod_amount("Daibiki", "", "", 61300)
    assert error == ""
    assert amount == 61300


def test_daibiki_with_dp_deposit_subtracts():
    amount, error = compute_cod_amount("Daibiki", "DP", "20000", 100000)
    assert error == ""
    assert amount == 80000


def test_daibiki_dp_without_deposit_is_invalid():
    amount, error = compute_cod_amount("Daibiki", "DP", "", 100000)
    assert amount == 0
    assert "dat coc" in error


def test_banktransfer_paid_collects_zero():
    amount, error = compute_cod_amount("BankTransfer", "Đã chuyển khoản", "", 139800)
    assert error == ""
    assert amount == 0


def test_banktransfer_unpaid_is_invalid():
    amount, error = compute_cod_amount("BankTransfer", "", "", 139800)
    assert amount == 0
    assert "chua chuyen khoan" in error


def test_unknown_transaction_type_is_invalid():
    amount, error = compute_cod_amount("", "", "", 61300)
    assert amount == 0
    assert "khong hop le" in error


def test_derive_fills_yamato_fields_for_daibiki():
    row = {
        "product_number": "COD_iPad 11 128GB WIFI BNIB blue - 61300",
        "type_of_transaction": "Daibiki",
        "payment_status": "",
        "deposit_amount": "",
    }
    error = derive_payment_fields(row)
    assert error == ""
    assert row["item_name1"] == "iPad 11 128GB WIFI BNIB blue"
    # Daibiki ships 着払い: no product-price collection, so amount stays empty.
    assert row["payment_method"] == "Chakubarai"
    assert row["amount"] == ""
    assert row["cod_amount"] == ""


def test_derive_is_noop_without_type_of_transaction():
    row = {"item_name1": "kept", "product_number": "ignored - 999"}
    assert derive_payment_fields(row) == ""
    assert "payment_method" not in row


def test_prepare_form_order_sets_non_dm_service_type():
    row = {
        "service_type": "3",
        "print_type": "3",
        "product_number": "COD - item - 61300",
        "type_of_transaction": "Daibiki",
        "payment_status": "",
    }
    error = prepare_form_order(row)
    assert error == ""
    assert row["service_type"] == "5"  # Daibiki -> 着払い (receiver pays delivery fee)
    assert row["print_type"] == "m5"
    assert row["label_type"] == "Chakubarai"
    assert row["amount"] == ""


def test_validate_local_surfaces_unpaid_banktransfer():
    row = normalize_row(
        _consignee_base(
            "ORD-1",
            product_number="TF - item - 38800",
            type_of_transaction="BankTransfer",
            payment_status="",
            bank_account="ACC-123",
        )
    )
    errors = validate_local(row)
    assert any("chua chuyen khoan" in error for error in errors)


def test_validate_local_passes_daibiki_without_shipper_or_invoice():
    # App does not require shipper/invoice; B2 fills the sender and check_shipment
    # is the source of truth for anything else it needs.
    row = normalize_row(
        _consignee_base(
            "ORD-2",
            product_number="COD - iPhone 11 128GB White - 37300",
            type_of_transaction="Daibiki",
            payment_status="",
        )
    )
    errors = validate_local(row)
    assert errors == []
    assert row["service_type"] == "5"  # Daibiki -> 着払い (receiver pays delivery fee)
    assert row["label_type"] == "Chakubarai"
    assert row["payment_method"] == "Chakubarai"
    assert row["amount"] == ""
    assert row["cod_amount"] == ""
    assert row["item_name1"] == "iPhone 11 128GB White"


def test_banktransfer_paid_gets_prepaid_label():
    row = {
        "product_number": "TF - Samsung S23 ultra - 92800",
        "type_of_transaction": "BankTransfer",
        "payment_status": "Đã chuyển khoản",
        "bank_account": "ACC-123",
    }
    error = prepare_form_order(row)
    assert error == ""
    assert row["label_type"] == "Prepaid"
    assert row["amount"] == "0"
