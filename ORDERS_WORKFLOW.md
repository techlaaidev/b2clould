# Order Workflow

Use `templates/orders_template.csv` as the starting file for Excel or Google Sheets.

## Columns

Internal columns:

- `order_id`: your internal order id. Required.
- `status`: processing status. Leave `NEW` for new rows.
- `error_message`: system writes validation errors here.
- `tracking_number`: filled after shipment is created.
- `created_at`: optional internal timestamp.
- `updated_at`: optional internal timestamp.

Yamato columns:

- `service_type`: Yamato service type. `3` is DM.
- `print_type`: Yamato print type. For example `3` for DM, `m5` for A5 multi.
- `shipment_date`: format `YYYY/MM/DD`.
- `delivery_date`: optional delivery date.
- `delivery_time_zone`: optional delivery time zone.
- `invoice_code`: required for non-DM services in this template.
- `invoice_code_ext`: invoice extension.
- `invoice_freight_no`: required for non-DM services in this template.
- `invoice_name`: invoice name.
- `amount`: payment amount.
- `tax_amount`: tax amount.
- `package_qty`: package quantity.
- `consignee_name`: recipient name.
- `consignee_title`: recipient title.
- `consignee_name_kana`: recipient kana.
- `consignee_code`: recipient code.
- `consignee_telephone_display`: recipient phone.
- `consignee_telephone_ext`: recipient phone extension.
- `consignee_zip_code`: postal code.
- `consignee_address1`: prefecture.
- `consignee_address2`: city/ward.
- `consignee_address3`: street/block.
- `consignee_address4`: building.
- `consignee_department1`: company or department.
- `consignee_department2`: company or department line 2.
- `is_using_center_service`: `0` or `1`.
- `consignee_center_code`: required when center service is `1`.
- `consignee_center_name`: required when center service is `1`.
- `shipper_name`: required for non-DM services in this template.
- `shipper_title`: shipper title.
- `shipper_telephone_display`: required for non-DM services in this template.
- `shipper_zip_code`: required for non-DM services in this template.
- `shipper_address1`: required for non-DM services in this template.
- `shipper_address2`: required for non-DM services in this template.
- `shipper_address3`: required for non-DM services in this template.
- `shipper_address4`: shipper building.
- `shipper_name_kana`: shipper kana.
- `item_name1`: item name, required for non-DM services.
- `item_name2`: item name line 2.
- `handling_information1`: handling note 1.
- `handling_information2`: handling note 2.
- `note`: memo.

Internal payment control columns. These are not sent directly to Yamato:

- `payment_method`: `COD`, `BANK_TRANSFER`, or blank.
- `cod_amount`: required when `payment_method` is `COD`.
- `bank_transfer_confirmed`: use `yes` when a bank transfer is confirmed.

## Business Form Columns

These four columns let the sheet keep its human layout; the system derives the
Yamato fields above from them (see `scripts/order_payment.py`). When
`type_of_transaction` is set, the order is treated as 宅急便 (non-DM):
`service_type` becomes `0` and `print_type` becomes `m5` automatically.

- `product_number`: `<label> - <name> - <total_price>`. The label prefix
  (COD/CK/TF...) is ignored; `<name>` becomes `item_name1` and `<total_price>`
  (trailing number, optional `y`/`¥`) is the order total.
- `type_of_transaction`: `Daibiki` (COD) or `BankTransfer` (prepaid). This — not
  the product label — drives every money decision.
- `payment_status`:
  - `Daibiki`: blank (no deposit) or `DP` (partial deposit, requires
    `deposit_amount`).
  - `BankTransfer`: `Đã chuyển khoản` (paid) or blank. Blank is rejected (do not
    ship before payment).
- `deposit_amount`: deposit value, required when `payment_status` is `DP`.

COD collect amount: `Daibiki` collects `total_price - deposit_amount`;
`BankTransfer` collects `0`.

### Shipper / invoice config

Shipper and invoice values are constant per shop, so they come from environment
config (see `.env.example`), not one column per order: `B2_INVOICE_CODE`,
`B2_INVOICE_FREIGHT_NO`, `B2_SHIPPER_NAME`, `B2_SHIPPER_TELEPHONE_DISPLAY`,
`B2_SHIPPER_ZIP_CODE`, `B2_SHIPPER_ADDRESS1..4`, `B2_SHIPPER_NAME_KANA`.
Non-DM orders are marked `INVALID` until these are configured.

## Status Values

- `NEW`: newly entered row.
- `INVALID`: row has missing or invalid data.
- `READY`: row passed validation and can be used to create a shipment.
- `CREATED`: tracking number already exists.

## Excel

Open `templates/orders_template.csv` in Excel, fill rows, then save as CSV UTF-8.

Validate locally:

```powershell
cd C:\Users\chipc\Desktop\b2cloud
python scripts\orders_csv.py templates\orders_template.csv -o data\orders_checked.csv
```

Validate against B2 Cloud:

```powershell
$env:B2_CUSTOMER_CODE="your_customer_code"
$env:B2_CUSTOMER_PASSWORD="your_customer_password"
$env:B2_LOGIN_USER_ID="your_login_user_id"
python scripts\orders_csv.py templates\orders_template.csv -o data\orders_checked.csv --check-b2
```

## Google Sheets

Create a Sheet with the same header row as `templates/orders_template.csv`.
Export it as CSV, then run the same command above.

Direct Google Sheets read/write needs Google API credentials. That can be added after the sheet layout is confirmed.
