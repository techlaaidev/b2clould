import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.sheet_mapping import (
    generate_order_id,
    map_input_row,
    map_output_row,
)
from scripts.orders_csv import normalize_row, validate_local


def test_map_input_translates_display_headers():
    display = {
        "Name": "高橋",
        "Postcode": "100-0001",
        "Address": "東京都千代田区千代田1-1",
        "Mobile": "03-1234-5678",
        "Product Number": "COD - iPhone - 50000",
        "Type of transaction": "Daibiki",
        "Thanh toán": "",
        "Số tiền đặt cọc": "",
        "Đơn vị giao hàng": "YAMATO",
        "IG/WA Account": "ignored",
    }
    internal = map_input_row(display)
    assert internal["consignee_name"] == "高橋"
    assert internal["consignee_zip_code"] == "100-0001"
    assert internal["consignee_address"] == "東京都千代田区千代田1-1"
    assert internal["product_number"] == "COD - iPhone - 50000"
    assert internal["type_of_transaction"] == "Daibiki"
    assert internal["carrier"] == "YAMATO"
    assert "IG/WA Account" not in internal  # unmapped column dropped


def test_generate_order_id_is_stable():
    row = {"consignee_name": "A", "consignee_telephone_display": "1", "product_number": "p", "order_date": "d"}
    assert generate_order_id(row) == generate_order_id(dict(row))
    assert generate_order_id(row).startswith("AUTO-")


def test_map_output_translates_status_and_error():
    out = map_output_row({"status": "CREATED", "tracking_number": "12345"})
    assert out["Mã vận đơn"] == "12345"
    assert out["Trạng thái khởi tạo"] == "Đã tạo đơn"  # khớp đúng dropdown trên sheet
    assert out["Trạng thái tạo đơn hàng tự động trên yamato"] == "Thành công"

    bad = map_output_row({"status": "INVALID", "error_message": "consignee_name is required"})
    assert bad["Trạng thái khởi tạo"] == "Không tạo đơn"
    assert bad["Cột bị lỗi"] == "Name"  # internal field -> sheet column
    assert bad["Tên lỗi"] == "Thiếu trường bắt buộc: Name"
    assert bad["Trạng thái tạo đơn hàng tự động trên yamato"] == "Thất bại"


def test_map_output_lists_all_missing_columns():
    bad = map_output_row({
        "status": "INVALID",
        "error_message": "consignee_name is required; consignee_telephone_display is required; item_name1 is required for service_type 5",
    })
    assert bad["Cột bị lỗi"] == "Name, Mobile, Product Number"


def test_precheck_only_accepts_yamato_carrier():
    from scripts.api_server import precheck_carrier_and_tracking

    # YAMATO (mọi kiểu hoa/thường) -> đi tiếp (None = xử lý trên Yamato B2).
    assert precheck_carrier_and_tracking({"carrier": "YAMATO", "tracking_number": ""}) is None
    assert precheck_carrier_and_tracking({"carrier": "yamato", "tracking_number": ""}) is None
    # Cách viết cũ JAMATO không còn được nhận -> lỗi tiếng Việt chỉ rõ cột.
    rejected = precheck_carrier_and_tracking({"carrier": "JAMATO", "tracking_number": ""})
    assert rejected["status"] == "INVALID"
    assert "YAMATO" in rejected["error_message"]
    assert rejected["error_column"] == "Đơn vị giao hàng"
    # JAPANPOST vẫn được bỏ qua (xuất CSV riêng), không phải lỗi.
    skipped = precheck_carrier_and_tracking({"carrier": "JAPANPOST", "tracking_number": ""})
    assert skipped["status"] == "SKIPPED"


def test_duplicate_note_has_full_details_in_vietnamese():
    from scripts.api_server import duplicate_note_vi

    note = duplicate_note_vi(
        {"shipment_date": "20260707", "amount": 90400}, "380352633710"
    )
    assert "Đơn TRÙNG" in note
    assert "07/07/2026" in note          # ngày tạo gốc trên B2
    assert "380352633710" in note        # mã vận đơn của đơn cũ
    assert "90400¥" in note              # số tiền thu hộ của đơn cũ
    assert "xoá đơn cũ" in note          # hướng dẫn cách tạo lại nếu cần


def test_normalize_auto_generates_order_id():
    row = normalize_row({"consignee_name": "A", "product_number": "p"})
    assert row["order_id"].startswith("AUTO-")


def test_banktransfer_without_bank_account_is_invalid():
    row = normalize_row({
        "order_id": "T1", "service_type": "3", "shipment_date": "2026/06/23",
        "consignee_name": "A", "consignee_telephone_display": "03-0000-0000",
        "consignee_zip_code": "1000001", "consignee_address1": "東京都",
        "consignee_address2": "千代田区", "consignee_address3": "千代田1-1",
        "product_number": "TF - item - 38800", "type_of_transaction": "BankTransfer",
        "payment_status": "Đã chuyển khoản", "bank_account": "",
    })
    errors = validate_local(row)
    assert any("Bank Account" in e for e in errors)
