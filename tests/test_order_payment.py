import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timedelta

from scripts.order_payment import (
    CONSIGNEE_ADDRESS3_MAX_WIDTH,
    _text_width,
    compute_cod_amount,
    derive_payment_fields,
    normalize_delivery_date,
    parse_product_number,
    prepare_form_order,
    split_consignee_address,
    truncate_item_name,
)
from scripts.orders_csv import create_shipment, normalize_row, validate_local
from scripts.sheet_mapping import b2_errors_to_vi, map_output_row


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


def test_trailing_price_wins_for_yamato_collect():
    # Giá cuối Product Number = số khách trả (ĐÃ GỒM phí thu hộ) — Yamato dùng
    # thẳng; cột Price (giá thật SP) không ảnh hưởng tiền thu hộ.
    row = {
        "product_number": "COD_iPad 11 128GB WIFI BNIB blue - 61300",
        "price": "59.800",
        "type_of_transaction": "Daibiki",
        "payment_status": "",
    }
    error = derive_payment_fields(row)
    assert error == ""
    assert row["amount"] == "61300"
    assert row["item_name1"] == "iPad 11 128GB WIFI BNIB blue"


def test_price_column_works_without_trailing_price():
    # Product Number không có giá -> dựng lại thu hộ = Price (giá thật) + phí.
    row = {
        "product_number": "iPhone 13 128GB blue",
        "price": "61300y",
        "type_of_transaction": "Daibiki",
        "payment_status": "",
    }
    error = derive_payment_fields(row)
    assert error == ""
    assert row["amount"] == "62800"  # 61300 + 1500 phí
    assert row["cod_amount"] == "62800"
    assert row["item_name1"] == "iPhone 13 128GB blue"


def test_trailing_price_dp_subtracts_deposit_only():
    # Thu hộ = giá cuối Product Number (đã gồm phí) - đặt cọc DP; không cộng gì thêm.
    row = {
        "product_number": "COD_iPhone 13 128GB - 100000",
        "price": "98500",
        "type_of_transaction": "Daibiki",
        "payment_status": "DP",
        "deposit_amount": "30000",
    }
    error = derive_payment_fields(row)
    assert error == ""
    assert row["amount"] == "70000"  # 100000 - 30000
    assert row["cod_amount"] == "70000"


def test_extra_fee_used_when_rebuilding_collect_from_price():
    # Chỉ khi Product Number KHÔNG có giá: thu hộ = Price + Thu khác
    # (2000 thay mặc định 1500; 0 = không phí).
    row = {
        "product_number": "iPhone 13 128GB",
        "price": "100000",
        "extra_fee": "2000",
        "type_of_transaction": "Daibiki",
        "payment_status": "",
    }
    assert derive_payment_fields(row) == ""
    assert row["amount"] == "102000"

    free = {
        "product_number": "iPhone 13 128GB",
        "price": "100000",
        "extra_fee": "0",
        "type_of_transaction": "Daibiki",
        "payment_status": "",
    }
    assert derive_payment_fields(free) == ""
    assert free["amount"] == "100000"


def test_missing_price_everywhere_is_invalid():
    row = {
        "product_number": "iPhone 13 128GB blue",
        "price": "",
        "type_of_transaction": "Daibiki",
        "payment_status": "",
    }
    error = derive_payment_fields(row)
    assert "cột Price" in error


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
    assert "Số tiền đặt cọc" in error


def test_banktransfer_paid_collects_zero():
    amount, error = compute_cod_amount("BankTransfer", "Đã chuyển khoản", "", 139800)
    assert error == ""
    assert amount == 0


def test_banktransfer_unpaid_is_invalid():
    amount, error = compute_cod_amount("BankTransfer", "", "", 139800)
    assert amount == 0
    assert "chưa chuyển khoản" in error


def test_unknown_transaction_type_is_invalid():
    amount, error = compute_cod_amount("", "", "", 61300)
    assert amount == 0
    assert "không hợp lệ" in error
    assert "Type of transaction" in error


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
    # Daibiki ships 宅急便コレクト (代引): thu hộ = giá cuối Product Number
    # (số này đã gồm phí thu hộ khách chịu).
    assert row["payment_method"] == "COD"
    assert row["amount"] == "61300"
    assert row["cod_amount"] == "61300"


def test_truncate_item_name_width_aware():
    # ASCII counts 0.5/char: 50 chars = 25.0 width, still fits.
    ascii50 = "macbook pro 2015 13inch retina space gray abcdefgh"
    assert len(ascii50) == 50
    assert truncate_item_name(ascii50) == ascii50
    # Over 50 ASCII chars gets cut at 50 (25.0 width).
    assert len(truncate_item_name(ascii50 + "XXXX")) == 50
    # Full-width counts 1.0/char: 26 kana -> trimmed to 25.
    kana = "あ" * 26
    assert truncate_item_name(kana) == "あ" * 25


def test_derive_truncates_long_item_name():
    row = {
        "product_number": "COD_" + "iPhone 15 Pro Max 256GB Natural Titanium xyz - 99000",
        "type_of_transaction": "Daibiki",
        "payment_status": "",
    }
    derive_payment_fields(row)
    # 品名 kept within the 25 full-width limit (ASCII => <=50 chars).
    assert len(row["item_name1"]) <= 50


def test_daibiki_deposit_partial_collects_remainder():
    row = {
        "service_type": "3",
        "print_type": "3",
        "product_number": "COD_iPhone 13 128GB - 100000",
        "type_of_transaction": "Daibiki",
        "payment_status": "DP",
        "deposit_amount": "30000",
    }
    error = prepare_form_order(row)
    assert error == ""
    assert row["service_type"] == "2"  # still 代引
    assert row["amount"] == "71500"    # price - deposit + 1500 phí thu hộ
    assert row["cod_amount"] == "71500"


def test_daibiki_full_deposit_ships_prepaid():
    row = {
        "service_type": "3",
        "print_type": "3",
        "product_number": "COD_iPhone 13 128GB - 100000",
        "type_of_transaction": "Daibiki",
        "payment_status": "DP",
        "deposit_amount": "100000",
    }
    error = prepare_form_order(row)
    assert error == ""
    # Fully deposited -> nothing to collect -> ship 発払い (prepaid), not 代引.
    assert row["service_type"] == "0"
    assert row["payment_method"] == "PREPAID"
    assert row["label_type"] == "Prepaid"
    assert row["amount"] == "0"


def test_split_address_caps_address3_and_overflows_to_building():
    # No postal session -> regex fallback. A long romaji building/room string
    # after the banchi must not blow past the 町・番地 width limit (ES001014).
    full = (
        "香川県坂出市川津町2126番地1 "
        "Nagai New Dormitory Building A Room 101 extra long tail xxxxxxxx"
    )
    a1, a2, a3, a4 = split_consignee_address(None, "762-0025", full)
    assert a1 == "香川県"
    assert _text_width(a3) <= CONSIGNEE_ADDRESS3_MAX_WIDTH
    # Nothing is lost: the overflow lands in the building field (address4).
    assert "101" in (a3 + a4)
    assert a4  # building/room text moved here


def test_split_separates_building_when_postal_lookup_fails():
    # Novy's address (ES001014 repro). No session -> regex fallback, yet the
    # building/room must still land in address4 so 町・番地 stays short.
    full = "石川県加賀市山代温泉山世台2丁目4番 和光ハイム No.302"
    a1, a2, a3, a4 = split_consignee_address(None, "9220242", full)
    assert a1 == "石川県"
    assert a2 == "加賀市"
    assert a3 == "山代温泉山世台2丁目4番"      # town+banchi only
    assert _text_width(a3) <= CONSIGNEE_ADDRESS3_MAX_WIDTH
    assert a4 == "和光ハイム No.302"           # building/room moved here


def test_create_shipment_does_not_send_note_to_yamato():
    # "Ghi chú" is an internal scratch column (deposit note); it must not be
    # forwarded to the Yamato label (would print + trip ES001036 when long).
    row = normalize_row(
        _consignee_base(
            "ORD-NOTE",
            service_type="0",
            product_number="COD - item - 61300",
            type_of_transaction="Daibiki",
            payment_status="",
            note="あ" * 40,
        )
    )
    prepare_form_order(row)
    shipment = create_shipment(row)
    assert shipment["shipment"]["note"] == ""


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
    assert row["service_type"] == "2"  # Daibiki -> 宅急便コレクト (代引/COD)
    assert row["print_type"] == "m5"  # A5マルチ: PDF từng đơn 1 nhãn / tờ A5
    assert row["label_type"] == "COD"
    assert row["amount"] == "62800"  # giá hàng + 1500 phí thu hộ


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
    assert any("chưa chuyển khoản" in error for error in errors)


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
    assert row["service_type"] == "2"  # Daibiki -> 宅急便コレクト (代引/COD)
    assert row["label_type"] == "COD"
    assert row["payment_method"] == "COD"
    assert row["amount"] == "38800"  # giá hàng + 1500 phí thu hộ
    assert row["cod_amount"] == "38800"
    assert row["item_name1"] == "iPhone 11 128GB White"


def test_normalize_delivery_date_accepts_common_display_formats():
    tomorrow = datetime.now().date() + timedelta(days=1)
    expect = tomorrow.strftime("%Y/%m/%d")
    assert normalize_delivery_date(tomorrow.strftime("%d/%m/%Y")) == expect
    assert normalize_delivery_date(tomorrow.strftime("%Y/%m/%d")) == expect
    assert normalize_delivery_date(tomorrow.strftime("%Y-%m-%d")) == expect


def test_normalize_delivery_date_us_format_and_no_year():
    # Ngày > 12 -> tự nhận ra MM/DD/YYYY (Google Sheets locale US hiển thị vậy).
    year = datetime.now().year + 1
    assert normalize_delivery_date(f"12/25/{year}") == f"{year}/12/25"
    # Thiếu năm -> năm nay; ngày đã qua thì tự sang năm sau.
    result = normalize_delivery_date("25/12")
    assert result.endswith("/12/25")
    assert result >= datetime.now().strftime("%Y/%m/%d")


def test_normalize_delivery_date_drops_past_and_garbage():
    assert normalize_delivery_date("01/01/2020") == ""
    assert normalize_delivery_date("mai giao") == ""
    assert normalize_delivery_date("") == ""


def test_delivery_date_sent_for_both_collect_and_prepaid():
    # Cột Date phải thành delivery_date (お届け予定日) trên shipment gửi lên B2,
    # cho cả đơn Daibiki (collect) lẫn BankTransfer (prepaid).
    tomorrow = (datetime.now().date() + timedelta(days=1)).strftime("%d/%m/%Y")
    expect = (datetime.now().date() + timedelta(days=1)).strftime("%Y/%m/%d")
    collect = normalize_row(_consignee_base(
        "ORD-DD1", service_type="0", delivery_date=tomorrow,
        product_number="COD - item - 61300",
        type_of_transaction="Daibiki", payment_status="",
    ))
    prepare_form_order(collect)
    assert create_shipment(collect)["shipment"]["delivery_date"] == expect

    prepaid = normalize_row(_consignee_base(
        "ORD-DD2", service_type="0", delivery_date=tomorrow,
        product_number="TF - item - 38800",
        type_of_transaction="BankTransfer", payment_status="Đã chuyển khoản",
        bank_account="ACC-123",
    ))
    prepare_form_order(prepaid)
    assert create_shipment(prepaid)["shipment"]["delivery_date"] == expect


def test_b2_error_translated_to_vietnamese_with_column():
    # Lỗi Yamato (tiếng Nhật + tên trường nội bộ) phải ra tiếng Việt + tên cột sheet.
    message, columns = b2_errors_to_vi([
        {
            "error_property_name": "consignee_address3",
            "error_code": "ES001014",
            "error_description": "お届け先町・番地が長すぎます。",
        }
    ])
    assert columns == "Address"
    assert "quá dài" in message
    assert "ES001014" in message
    assert "お届け先" not in message  # không lộ tiếng Nhật cho người dùng cuối


def test_map_output_statuses_match_sheet_dropdown():
    # Dropdown "Trạng thái khởi tạo" chỉ có 3 giá trị, đúng chữ hoa/thường.
    assert map_output_row({"status": "CREATED"})["Trạng thái khởi tạo"] == "Đã tạo đơn"
    assert map_output_row({"status": "PENDING"})["Trạng thái khởi tạo"] == "Chờ tạo đơn"
    assert map_output_row({"status": "SAVED"})["Trạng thái khởi tạo"] == "Chờ tạo đơn"
    assert map_output_row({"status": "INVALID"})["Trạng thái khởi tạo"] == "Không tạo đơn"
    # Cột trạng thái tự động: PENDING chưa được tính là thành công.
    assert map_output_row({"status": "PENDING"})["Trạng thái tạo đơn hàng tự động trên yamato"] == "Đang chờ Yamato xác nhận"
    assert map_output_row({"status": "CREATED"})["Trạng thái tạo đơn hàng tự động trên yamato"] == "Thành công"
    assert map_output_row({"status": "INVALID"})["Trạng thái tạo đơn hàng tự động trên yamato"] == "Thất bại"


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
