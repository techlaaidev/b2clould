# Hướng dẫn sử dụng Sheet quản lý đơn hàng — B2 Cloud + KiotViet

*Phiên bản: 20/07/2026 — dành cho nhân viên nhập đơn và quản lý.*

Hệ thống gồm 1 Google Sheet + menu **B2 Cloud** (hiện trên thanh menu khi mở sheet). Từ sheet này bạn làm được trọn luồng: **nhập đơn → kiểm tra → tạo vận đơn Yamato → in nhãn → tạo hóa đơn KiotViet → in phiếu giao hàng** mà không phải vào trang Yamato B2 hay KiotViet thao tác tay.

---

## 1. Luồng làm việc chuẩn cho 1 đơn hàng

```
① Nhập thông tin đơn vào 1 dòng  (Order Date tự điền, xem mục 7)
② Gõ IMEI (5 số cuối) → hệ thống tự điền tên sản phẩm KiotViet
③ Bôi đen dòng → "Kiểm tra và đồng bộ đơn"          (bắt lỗi dữ liệu)
④ Bôi đen dòng → "Tạo vận đơn cho đơn hợp lệ"       (đơn YAMATO — có Mã vận đơn + PDF nhãn)
   (đơn JAPANPOST → "Tạo CSV Japan Post" thay cho bước này)
⑤ Bôi đen các dòng đã có vận đơn → "In gộp phiếu đã tạo"  (2 nhãn Yamato / tờ A4)
⑥ Bôi đen dòng → "Tạo hóa đơn KiotViet"             (trừ kho + gắn IMEI + Thu khác + phiếu giao hàng)
⑦ Bôi đen dòng đã có hóa đơn → "In gộp phiếu giao hàng KiotViet"  (2 phiếu / tờ A4)
```

**Quy tắc quan trọng nhất: hệ thống chỉ xử lý các dòng bạn đang BÔI ĐEN.** Bôi đen nhiều dòng (kể cả Ctrl+click các dòng rời nhau) để xử lý hàng loạt.

---

## 2. Ý nghĩa các cột

### 2.1. Cột nhập tay (nhân viên điền)

| Cột | Bắt buộc | Cách điền |
|---|---|---|
| **Name** | ✔ | Tên người nhận hàng |
| **IG/WA Account** | ✔ (để tạo hóa đơn) | Tài khoản Instagram/WhatsApp của khách — dùng làm TÊN KHÁCH trên KiotViet (không trùng nhau) |
| **Postcode** | ✔ | Mã bưu điện Nhật, ví dụ `762-0025` |
| **Address** | ✔ | Địa chỉ đầy đủ đến tận nhà (tiếng Nhật) |
| **Mobile** | ✔ | Số điện thoại người nhận |
| **Email** | — | Email khách (nếu có) |
| **Date** | — | Ngày khách muốn nhận. **Phải là ngày TƯƠNG LAI** và đủ thời gian vận chuyển. Không chắc thì **để trống** — Yamato giao sớm nhất có thể. Chấp nhận nhiều kiểu: `20/07/2026`, `20/7`, `2026/07/20` |
| **Time** | — | Khung giờ nhận, ví dụ `09:00~12:00` |
| **Product Number** | ✔ | Mô tả hàng, **KẾT THÚC bằng số tiền KHÁCH TRẢ khi nhận** (đã gồm phí COD). Ví dụ `COD_iPad 11 128GB - 61300`. Chấp nhận cả phép tính thu cũ đổi mới: `... - 121,800y-Buyback 57,000 = 64,800y` → lấy **64.800** (số sau dấu `=`) |
| **Price** | — | **GIÁ THẬT của máy** = số khách trả − Thu khác. Không cần điền tay — bấm menu **"Điền cột Price từ Product Number"** để tự tính (xem mục 5.2) |
| **Type of transaction** | ✔ | Chỉ 2 giá trị: `Daibiki` (COD) hoặc `BankTransfer` |
| **Bank Account** | ✔ khi BankTransfer | Tài khoản ngân hàng nhận tiền |
| **Thanh toán** | tùy loại đơn | Đơn **BankTransfer**: phải là `Đã chuyển khoản` mới được tạo đơn. Đơn **Daibiki**: để trống, hoặc `DP` nếu khách đặt cọc |
| **Số tiền đặt cọc** | ✔ khi Thanh toán = DP | Số tiền khách đã cọc (chỉ số) |
| **Đơn vị giao hàng** | ✔ | `YAMATO` hoặc `JAPANPOST` (chọn từ dropdown) |
| **IMEI** | ✔ với máy quản lý IMEI | Gõ **5 số cuối** IMEI rồi Enter — hệ thống tự tra và điền phần còn lại (xem mục 4). Dán đủ số IMEI cũng được |
| **Người nhập đơn** | — | Chọn tên nhân viên từ dropdown → thành NGƯỜI BÁN trên hóa đơn KiotViet. Trống = người bán mặc định |
| **Hàng tặng kèm** | — | Chọn bộ quà / phí ship từ dropdown; nhiều mục ngăn cách dấu phẩy (xem mục 5.4) |
| **Thu khác** | — | Phí COD thu của khách cho đơn Daibiki. **Trống = mặc định 1.500¥**; điền `0` = không thu phí |
| **Ngôn ngữ phiếu** | — | Chọn `Nhật` / `Việt` — quyết định phiếu giao hàng KiotViet in bằng mẫu nào. **Trống = Nhật** (xem mục 6) |
| **Ghi chú** | — | Ghi chú nội bộ, không in lên nhãn |

> **Order Date** được hệ thống **tự điền ngày hôm nay** cho dòng mới — không cần gõ tay (xem mục 7).

### 2.2. Cột hệ thống tự ghi (KHÔNG sửa tay)

| Cột | Ai ghi | Ý nghĩa |
|---|---|---|
| **Tên sản phẩm Kiot Việt** | Tự điền khi gõ IMEI (hoặc gõ từ khóa để tìm) | Tên đầy đủ SP trên KiotViet — phải khớp đúng SP sẽ bán |
| **Order Date** | Hệ thống tự điền | Ngày tạo đơn (hôm nay) |
| **Mã vận đơn** | Hệ thống (đơn Yamato) / tự điền (Japan Post) | Số tracking |
| **Trạng thái khởi tạo** | Hệ thống | `Chờ tạo đơn` / `Không tạo đơn` (kèm lý do) |
| **Cột bị lỗi**, **Tên lỗi** | Hệ thống | Chỉ đúng cột sai + lỗi bằng tiếng Việt — sửa xong chạy lại |
| **Trạng thái tạo đơn hàng tự động trên yamato** | Hệ thống | Kết quả phía Yamato |
| **pdf_url** | Hệ thống | Link PDF nhãn Yamato của riêng đơn đó (1 nhãn/tờ A5) |
| **pdf_url_kiot_viet** | Hệ thống | Link PDF phiếu giao hàng KiotViet của riêng đơn đó |
| **Link url file csv xử lí mã vận đơn** | Hệ thống | Link file CSV YuPack R (đơn Japan Post) |
| **Hóa đơn KiotViet** | Hệ thống | Mã hóa đơn (vd `HD045022`) khi thành công, hoặc `LỖI: ...` |
| **_kvCode** (cột ẩn) | Hệ thống | Mã SP KiotViet — **tuyệt đối không xóa cột này** |

> Ngoài ra sheet có 2 sheet ẩn `KiotViet_Catalog`, `KiotViet_ImeiIndex` (dữ liệu nền) và sheet `In gộp` (lịch sử in — có 2 cột link: **Link PDF** cho nhãn Yamato, **Link PDF KiotViet** cho phiếu giao hàng). Không sửa/xóa các sheet này.

---

## 3. Menu B2 Cloud — từng chức năng

| Menu | Khi nào dùng |
|---|---|
| **Cấu hình API key** | Chỉ quản lý, cài 1 lần (key server B2) |
| **Kiểm tra và đồng bộ đơn** | Trước khi tạo vận đơn: bắt lỗi dữ liệu tại chỗ + đồng bộ trạng thái các đơn đã gửi lên Yamato |
| **Tạo vận đơn cho đơn hợp lệ** | Tạo vận đơn Yamato cho các dòng bôi đen. Dòng lỗi bị chặn lại và ghi lý do, KHÔNG gửi đi. Thành công → có Mã vận đơn + pdf_url |
| **In gộp phiếu đã tạo (2 nhãn/tờ A4)** | Sau khi tạo vận đơn: bôi đen các dòng cần in (tất cả phải có Mã vận đơn + pdf_url) → 1 file PDF gộp, 2 **nhãn Yamato**/tờ. Link mở được ngay ở hộp thoại + lưu vào sheet "In gộp" |
| **In gộp phiếu giao hàng KiotViet (2 phiếu/tờ A4)** | Sau khi tạo hóa đơn: bôi đen các dòng đã có Hóa đơn KiotViet → 1 file PDF **phiếu giao hàng** (mẫu 納品書 Nhật/Việt), 2 phiếu/tờ A4 |
| **Điền cột Price từ Product Number** | Tự điền cột Price hàng loạt (xem mục 5.2). Ô đã có giá thì giữ nguyên |
| **Tạo CSV Japan Post (YuPack R)** | Đơn JAPANPOST: xuất file CSV để nhập vào phần mềm ゆうプリR. Link ghi vào từng dòng đã xuất |
| **Cấu hình KiotViet API** | Chỉ quản lý, cài 1 lần (Client ID / Secret / tên gian hàng) |
| **Đồng bộ nhanh KiotViet (nhân viên/quà/SP thay đổi)** | **Dùng hằng ngày** khi: có nhân viên mới, sửa bộ quà, hoặc muốn cập nhật SP mới — chỉ mất vài giây (xem mục 8) |
| **Đồng bộ kho KiotViet (TOÀN BỘ — chậm, ít khi cần)** | Chỉ chạy lần đầu cài đặt, hoặc khi nghi dữ liệu nền lệch (vd SP bị xóa hẳn khỏi KiotViet) |
| **Tạo hóa đơn KiotViet** | Tạo hóa đơn (trừ kho, gắn IMEI, gắn Thu khác, dựng phiếu giao hàng PDF) cho các dòng bôi đen |

---

## 4. Tra sản phẩm bằng IMEI (nhanh nhất)

1. Gõ **5 số cuối** của IMEI vào cột **IMEI** rồi Enter (dán đủ số IMEI cũng được).
2. Hệ thống hỏi KiotViet dữ liệu mới nhất rồi tra:
   - Khớp đúng 1 máy → tự ghi **IMEI đầy đủ** vào ô + điền **Tên sản phẩm Kiot Việt** + mã SP ẩn.
   - Nhiều máy trùng đuôi → hiện dropdown ▼ các IMEI đầy đủ để chọn.
   - Không thấy → báo "không tìm thấy" (sai IMEI, máy đã bán, hoặc máy ở chi nhánh khác).
3. Nếu tên SP tra ra **lệch với mô tả ở Product Number**, hệ thống cảnh báo ngay — kiểm tra lại kẻo bán nhầm máy.

Cách phụ: gõ từ khóa (vd `iphone 13 128`) thẳng vào cột **Tên sản phẩm Kiot Việt** → dropdown gợi ý → chọn đúng SP.

---

## 5. Quy tắc riêng cho đơn Daibiki (COD)

### 5.1. Thứ tự bắt buộc
Đơn Daibiki **phải tạo vận đơn Yamato TRƯỚC, tạo hóa đơn KiotViet SAU** — hóa đơn cần Mã vận đơn để in lên phiếu giao hàng. Làm ngược sẽ bị chặn với thông báo rõ ràng.

### 5.2. Tiền nong (hiểu 1 lần cho đúng)

Có 3 con số, đừng nhầm lẫn:

| Con số | Ở đâu | Là gì |
|---|---|---|
| **Số khách trả** | cuối cột **Product Number** | Tiền khách đưa khi nhận hàng — **ĐÃ GỒM phí COD** |
| **Thu khác** | cột **Thu khác** | Phí COD (trống = 1.500¥) |
| **Giá thật của máy** | cột **Price** | = Số khách trả − Thu khác |

- **Yamato thu hộ** = đúng số cuối Product Number (đơn DP thì trừ đặt cọc). Không cộng gì thêm.
- **Menu "Điền cột Price từ Product Number"** tự tính: đơn Daibiki → Price = số cuối Product Number − Thu khác; đơn khác → giữ nguyên số cuối. *Nhớ điền cột Thu khác TRƯỚC khi bấm menu này.*
- **Trên hóa đơn KiotViet**: giá SP = cột Price; **Thu khác** lên thành khoản thu `決済手数料 (THK000001)` → tổng hóa đơn khớp đúng số khách trả.

> Ví dụ: Product Number `... - 128800`, Thu khác trống → Price tự điền `127300`. Hóa đơn KiotViet: máy 127.300 + Thu khác 1.500 = 128.800 (đúng số khách trả).

### 5.3. Phiếu giao hàng KiotViet (cột pdf_url_kiot_viet)
Sau khi **Tạo hóa đơn KiotViet**, hệ thống tự dựng **phiếu giao hàng PDF** cho đơn Daibiki (mẫu 納品書), link ghi vào cột **pdf_url_kiot_viet**. Phiếu gồm: mã hóa đơn, mã vạch + số vận đơn Yamato, khách/SĐT/địa chỉ, sản phẩm + IMEI, hàng tặng kèm, số **THU HỘ (COD)**, đối tác ヤマト Nagoya. Muốn in gộp nhiều phiếu → menu **"In gộp phiếu giao hàng KiotViet"** (2 phiếu/tờ A4).

*Phí vận đơn Yamato (代引手数料 theo bậc: ≤9.999¥→330 / ≤29.999¥→440 / ≤99.999¥→660 / trên nữa→1.100¥) được ghi sẵn trong phiếu.*

### 5.4. Bộ quà / phụ phí (cột "Hàng tặng kèm")
Các mục hợp lệ (chọn từ dropdown, nhiều mục cách nhau dấu phẩy):
`SET 20W-Lightning`, `20W Adapter`, `SET 20W-CtoC`, `SET 35W-CtoC (2m)`, `SET 5W-Lightning`, `Shipping cost 600`, `Shipping cost 430`, `Shipping cost 200`.
Quà lên hóa đơn giá 0¥ (vẫn trừ kho); mục "Shipping cost" lên đúng giá. *Muốn thêm bộ mới → báo quản lý (phải sửa trong code).*

---

## 6. Phiếu giao hàng: mẫu tiếng Nhật / tiếng Việt

Hệ thống có 2 mẫu phiếu giao hàng KiotViet, chọn theo cột **Ngôn ngữ phiếu** của TỪNG dòng:

- `Nhật` (hoặc để trống) → mẫu **納品書** tiếng Nhật.
- `Việt` → mẫu **PHIẾU GIAO HÀNG** tiếng Việt.

Một lần "In gộp phiếu giao hàng KiotViet" có thể trộn lẫn — vài phiếu Nhật, vài phiếu Việt trong cùng 1 file PDF. Dropdown Nhật/Việt xuất hiện sau khi chạy "Đồng bộ nhanh KiotViet".

---

## 7. Order Date tự điền

Dòng mới **chỉ cần có 1 trong: Name / Product Number / IG/WA Account / Address** là hệ thống tự điền **Order Date = ngày hôm nay**. Không cần gõ tay, không cần bấm nút.

- Gõ/dán tay → điền ngay.
- Mở sheet ra hoặc bấm bất kỳ menu chính (Kiểm tra đồng bộ / Tạo vận đơn / Tạo hóa đơn) → hệ thống quét và điền cho các dòng còn thiếu (kể cả đơn đổ về từ form web).
- Ô Order Date đã có ngày thì **giữ nguyên** (không ghi đè).

---

## 8. Khi có nhân viên mới / hàng mới về

Chạy menu **"Đồng bộ nhanh KiotViet"** — mất vài giây:
- Nhân viên mới trên KiotViet → có ngay trong dropdown "Người nhập đơn".
- Cập nhật dropdown "Hàng tặng kèm" và "Ngôn ngữ phiếu".
- SP mới nhập / đổi tên / IMEI mới → tự vá vào dữ liệu tra cứu (chỉ hỏi phần **thay đổi** từ lần đồng bộ trước, không quét lại cả kho).

Không cần chạy "Đồng bộ kho TOÀN BỘ" trừ lần cài đặt đầu tiên.

---

## 9. Lỗi thường gặp & cách xử lý

| Thông báo | Nguyên nhân | Cách sửa |
|---|---|---|
| `Cột Date: dữ liệu bị Yamato từ chối` / Estimated delivery date trống | Ngày nhận là quá khứ/hôm nay hoặc quá gần | Sửa Date thành ngày tương lai hợp lệ, hoặc xóa trống |
| Lỗi địa chỉ `ES001014` | Địa chỉ quá dài so với khổ nhãn Yamato | Rút gọn phần 町・番地, chuyển tên tòa nhà/phòng ra phần sau |
| `Đơn BankTransfer chưa chuyển khoản` | Cột Thanh toán chưa phải `Đã chuyển khoản` | Xác nhận tiền về rồi sửa cột Thanh toán |
| `Đơn Daibiki có đặt cọc (DP) nhưng thiếu Số tiền đặt cọc` | Ghi DP mà quên số cọc | Điền số vào cột Số tiền đặt cọc |
| `Thiếu giá bán: điền số vào cột Price...` | Product Number không có số cuối và cột Price trống | Điền Price, hoặc thêm số tiền vào cuối Product Number |
| `SP quản lý IMEI — cần điền IMEI` | Máy có IMEI mà ô IMEI trống | Gõ 5 số cuối IMEI để hệ thống tra |
| `IMEI ... đã bán / không còn trong kho` | Máy đã bán hoặc IMEI sai | Kiểm tra lại máy thực tế đang cầm |
| `IMEI ... còn hàng nhưng ở chi nhánh khác` | Máy thuộc chi nhánh khác | Chỉ bán được máy thuộc chi nhánh hiện tại (Akihabara) |
| `Sai tên sản phẩm: ô ghi ... nhưng SP mã ... là ...` | Tên trong ô bị sửa tay / chọn nhầm | Chọn lại SP từ gợi ý (đừng gõ đè tên) |
| `SP KiotViet ... chỉ khớp x% với Product Number` | SP chọn không giống mô tả hàng → nghi bán nhầm máy | Đối chiếu lại IMEI với mô tả ở Product Number |
| `Đơn Daibiki chưa có Mã vận đơn Yamato` | Tạo hóa đơn trước khi tạo vận đơn | Chạy "Tạo vận đơn cho đơn hợp lệ" trước |
| `Đã bỏ qua N dòng vì đã có hóa đơn` | Chống đẩy trùng hóa đơn | Muốn tạo lại thật: xóa ô "Hóa đơn KiotViet" của dòng đó rồi chạy lại |
| Popup `⚠ Sheet bị thay đổi trong lúc xử lý` | Có người sort/thêm/xóa dòng khi hệ thống đang chạy | Không sort/xóa dòng khi đang xử lý; chạy lại các dòng được liệt kê |

**Nguyên tắc chung:** dòng lỗi luôn được ghi rõ **Cột bị lỗi** + **Tên lỗi** ngay trên dòng đó. Sửa đúng cột được chỉ, bôi đen dòng, chạy lại menu tương ứng.

> ⚠ **Lưu ý:** hệ thống **không còn tự chặn đơn trùng** ở phía Yamato. Chạy lại "Tạo vận đơn" trên một dòng đã có vận đơn có thể tạo đơn Yamato thứ hai — kiểm tra kỹ trước khi chạy lại.

---

## 10. Cài đặt lần đầu (chỉ quản lý)

1. **Cấu hình API key** → nhập `B2_API_KEY` (key server B2 trên Render).
2. **Cấu hình KiotViet API** → nhập Client ID, Client Secret, tên gian hàng (`jamobileno1`). Lấy tại KiotViet → Thiết lập → Thiết lập kết nối API.
3. **Đồng bộ kho KiotViet (TOÀN BỘ)** → chạy 1 lần để có dữ liệu nền (danh mục SP + chỉ mục IMEI + các dropdown).
4. **Mẫu in phiếu giao hàng** (trong Apps Script editor → (+) → HTML):
   - File tên `MauInKiotViet` ← dán HTML mẫu 納品書 tiếng Nhật.
   - File tên `MauInKiotVietVN` ← dán HTML mẫu PHIẾU GIAO HÀNG tiếng Việt.
   - *Lấy HTML: KiotViet → Thiết lập → Quản lý mẫu in → mở mẫu → nút `</>` (Source) → copy toàn bộ.*
5. Từ đó về sau chỉ dùng **Đồng bộ nhanh**.

Yêu cầu phía KiotViet (ghi lại để biết): gian hàng bật **"Sử dụng tính năng giao hàng"**; đối tác giao hàng **ヤマト Nagoya** phải tồn tại trong danh sách đối tác; khoản thu khác mã **`THK000001`** (決済手数料) phải có trong "Các khoản thu khác".

---

## 11. Những điều KHÔNG được làm

- **Không sort / thêm / xóa dòng** trong lúc hệ thống đang chạy (đang hiện toast "Đang xử lý...").
- **Không xóa cột ẩn `_kvCode`**, các sheet ẩn `KiotViet_Catalog`, `KiotViet_ImeiIndex`, sheet `In gộp`.
- **Không sửa tay** các cột hệ thống ghi (Trạng thái, Tên lỗi, pdf_url, pdf_url_kiot_viet, Hóa đơn KiotViet, Mã vận đơn của đơn Yamato).
- **Không gõ đè tên** vào cột "Tên sản phẩm Kiot Việt" — luôn chọn từ gợi ý hoặc để IMEI tự điền.
- Không đổi tên các cột tiêu đề — hệ thống nhận diện cột theo đúng tên header.
