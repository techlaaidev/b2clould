import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.order_payment import (
    compute_cod_amount,
    derive_payment_fields,
    parse_product_number,
)
from scripts.orders_csv import normalize_row, validate_local


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
