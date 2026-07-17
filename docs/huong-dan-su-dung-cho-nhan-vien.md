# Hướng dẫn sử dụng Sheet quản lý đơn hàng — B2 Cloud + KiotViet

*Phiên bản: 17/07/2026 — dành cho nhân viên nhập đơn và quản lý.*

Hệ thống gồm 1 Google Sheet + menu **B2 Cloud** (hiện trên thanh menu khi mở sheet). Từ sheet này bạn làm được trọn luồng: **nhập đơn → kiểm tra → tạo vận đơn Yamato → in nhãn → tạo hóa đơn KiotViet** mà không phải vào trang Yamato B2 hay KiotViet thao tác tay.

---

## 1. Luồng làm việc chuẩn cho 1 đơn hàng

```
① Nhập thông tin đơn vào 1 dòng
② Gõ IMEI (5 số cuối) → hệ thống tự điền tên sản phẩm KiotViet
③ Bôi đen dòng → menu "Kiểm tra và đồng bộ đơn"     (bắt lỗi dữ liệu)
④ Bôi đen dòng → menu "Tạo vận đơn cho đơn hợp lệ"  (đơn YAMATO — có Mã vận đơn + PDF)
   (đơn JAPANPOST → menu "Tạo CSV Japan Post" thay cho bước này)
⑤ Bôi đen các dòng đã có vận đơn → "In gộp phiếu đã tạo" (2 nhãn / tờ A4)
⑥ Bôi đen dòng → "Tạo hóa đơn KiotViet"             (trừ kho + gắn vận đơn trên KiotViet)
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
| **Date** | — | Ngày khách muốn nhận. **Phải là ngày TƯƠNG LAI** và đủ thời gian vận chuyển (vùng xa lùi thêm 1–2 ngày). Không chắc thì **để trống** — Yamato giao sớm nhất có thể |
| **Time** | — | Khung giờ nhận, ví dụ `09:00~12:00` |
| **Product Number** | ✔ | Mô tả hàng: `COD_iPad 11 128GB WIFI BNIB blue - 61300`. Số sau dấu `-` cuối là giá bán (dùng khi cột Price trống) |
| **Price** | ✔* | **GIÁ GỐC** sản phẩm (chỉ số, ví dụ `61300`). Không trừ cọc, không cộng phí. (*bắt buộc nếu cuối Product Number không có giá) |
| **Type of transaction** | ✔ | Chỉ 2 giá trị: `Daibiki` (COD) hoặc `BankTransfer` |
| **Bank Account** | ✔ khi BankTransfer | Tài khoản ngân hàng nhận tiền |
| **Thanh toán** | tùy loại đơn | Đơn **BankTransfer**: phải là `Đã chuyển khoản` mới được tạo đơn. Đơn **Daibiki**: để trống, hoặc `DP` nếu khách đặt cọc |
| **Số tiền đặt cọc** | ✔ khi Thanh toán = DP | Số tiền khách đã cọc (chỉ số) |
| **Đơn vị giao hàng** | ✔ | `YAMATO` hoặc `JAPANPOST` (chọn từ dropdown) |
| **IMEI** | ✔ với máy quản lý IMEI | Gõ **5 số cuối** của IMEI rồi Enter — hệ thống tự tra và điền phần còn lại (xem mục 4) |
| **Người nhập đơn** | — | Chọn tên nhân viên từ dropdown → thành NGƯỜI BÁN trên hóa đơn KiotViet. Trống = người bán mặc định |
| **Hàng tặng kèm** | — | Chọn bộ quà / phí ship từ dropdown; nhiều mục ngăn cách dấu phẩy (xem mục 5.3) |
| **Thu khác** | — | Phí COD thu của khách cho đơn Daibiki. **Trống = mặc định 1.500¥** |
| **Order Date** | — | Ngày khách đặt hàng |
| **Ghi chú** | — | Ghi chú nội bộ, không in lên nhãn |

### 2.2. Cột hệ thống tự ghi (KHÔNG sửa tay)

| Cột | Ai ghi | Ý nghĩa |
|---|---|---|
| **Tên sản phẩm Kiot Việt** | Tự điền khi gõ IMEI (hoặc gõ từ khóa để tìm) | Tên đầy đủ SP trên KiotViet — phải khớp đúng SP sẽ bán |
| **Mã vận đơn** | Hệ thống (đơn Yamato) / tự điền (Japan Post) | Số tracking |
| **Trạng thái khởi tạo** | Hệ thống | `Chờ tạo đơn` / `Không tạo đơn` (kèm lý do) |
| **Cột bị lỗi**, **Tên lỗi** | Hệ thống | Chỉ đúng cột sai + lỗi bằng tiếng Việt — sửa xong chạy lại |
| **Trạng thái tạo đơn hàng tự động trên yamato** | Hệ thống | Kết quả phía Yamato |
| **pdf_url** | Hệ thống | Link PDF nhãn của riêng đơn đó (1 nhãn/tờ A5) |
| **Link url file csv xử lí mã vận đơn** | Hệ thống | Link file CSV YuPack R (đơn Japan Post) |
| **Hóa đơn KiotViet** | Hệ thống | Mã hóa đơn (vd `HD045022`) khi thành công, hoặc `LỖI: ...` |
| **Giao hàng** | Nhân viên | Trạng thái giao: `Đã gửi đơn`... (quy ước nội bộ, hệ thống không đụng) |
| **_kvCode** (cột ẩn) | Hệ thống | Mã SP KiotViet — **tuyệt đối không xóa cột này** |

> Ngoài ra sheet có 2 sheet ẩn `KiotViet_Catalog`, `KiotViet_ImeiIndex` (dữ liệu nền) và sheet `In gộp` (lịch sử in) — không sửa/xóa.

---

## 3. Menu B2 Cloud — từng chức năng

| Menu | Khi nào dùng |
|---|---|
| **Cấu hình API key** | Chỉ quản lý, cài 1 lần (key server B2) |
| **Kiểm tra và đồng bộ đơn** | Trước khi tạo vận đơn: bắt lỗi dữ liệu tại chỗ + đồng bộ trạng thái các đơn đã gửi lên Yamato |
| **Tạo vận đơn cho đơn hợp lệ** | Tạo vận đơn Yamato cho các dòng bôi đen. Dòng lỗi bị chặn lại và ghi lý do, KHÔNG gửi đi. Thành công → có Mã vận đơn + pdf_url |
| **In gộp phiếu đã tạo (2 nhãn/tờ A4)** | Sau khi tạo vận đơn: bôi đen các dòng cần in (tất cả phải có Mã vận đơn + pdf_url) → 1 file PDF gộp, 2 nhãn/tờ. Link lưu vào sheet "In gộp" |
| **Điền cột Price từ Product Number** | Điền giá hàng loạt cho dòng cũ chưa có Price (lấy số cuối Product Number). Ô đã có giá thì giữ nguyên |
| **Tạo CSV Japan Post (YuPack R)** | Đơn JAPANPOST: xuất file CSV để nhập vào phần mềm ゆうプリR. Link ghi vào từng dòng đã xuất |
| **Cấu hình KiotViet API** | Chỉ quản lý, cài 1 lần (Client ID / Secret / tên gian hàng) |
| **Đồng bộ nhanh KiotViet (nhân viên/quà/SP thay đổi)** | **Dùng hằng ngày** khi: có nhân viên mới, sửa bộ quà, hoặc muốn cập nhật SP mới — chỉ mất vài giây (xem mục 6) |
| **Đồng bộ kho KiotViet (TOÀN BỘ — chậm, ít khi cần)** | Chỉ chạy lần đầu cài đặt, hoặc khi nghi dữ liệu nền lệch (vd SP bị xóa hẳn khỏi KiotViet) |
| **Tạo hóa đơn KiotViet** | Bước cuối: tạo hóa đơn (trừ kho, gắn IMEI, gắn vận đơn) cho các dòng bôi đen |

---

## 4. Tra sản phẩm bằng IMEI (nhanh nhất)

1. Gõ **5 số cuối** của IMEI vào cột **IMEI** rồi Enter.
2. Hệ thống hỏi KiotViet dữ liệu mới nhất rồi tra:
   - Khớp đúng 1 máy → tự ghi **IMEI đầy đủ** vào ô + điền **Tên sản phẩm Kiot Việt** + mã SP ẩn.
   - Nhiều máy trùng đuôi → hiện dropdown ▼ các IMEI đầy đủ để chọn.
   - Không thấy → báo "không tìm thấy" (sai IMEI, máy đã bán, hoặc máy ở chi nhánh khác).
3. Nếu tên SP tra ra **lệch với mô tả ở Product Number**, hệ thống cảnh báo ngay — kiểm tra lại kẻo bán nhầm máy.

Cách phụ: gõ từ khóa (vd `iphone 13 128`) thẳng vào cột **Tên sản phẩm Kiot Việt** → dropdown gợi ý → chọn đúng SP.

---

## 5. Quy tắc riêng cho đơn Daibiki (COD)

### 5.1. Thứ tự bắt buộc
Đơn Daibiki **phải tạo vận đơn Yamato TRƯỚC, tạo hóa đơn KiotViet SAU** — hóa đơn cần Mã vận đơn để gắn vào phần giao hàng. Làm ngược sẽ bị chặn với thông báo rõ ràng.

### 5.2. Tiền nong trên hóa đơn KiotViet (tự động, không phải tính tay)
- Giá hàng = cột **Price** (hoặc giá trên KiotViet nếu có).
- **Thu khác** = phí COD thu của khách (trống = 1.500¥) → lên hóa đơn thành khoản thu 決済手数料.
- **Phí vận đơn Yamato (代引手数料)** theo bậc giá hàng: ≤9.999¥ → 330 / ≤29.999¥ → 440 / ≤99.999¥ → 660 / trên nữa → 1.100¥ — tự ghi vào "Phí áp dụng" của vận đơn.
- Vận đơn trên hóa đơn tự gắn đối tác **ヤマト Nagoya**, trạng thái "Chờ xử lý", kèm Mã vận đơn + tên/SĐT/địa chỉ người nhận.

### 5.3. Bộ quà / phụ phí (cột "Hàng tặng kèm")
Các mục hợp lệ (chọn từ dropdown, nhiều mục cách nhau dấu phẩy):
`SET 20W-Lightning`, `20W Adapter`, `SET 20W-CtoC`, `SET 35W-CtoC (2m)`, `SET 5W-Lightning`, `Shipping cost 600`, `Shipping cost 430`, `Shipping cost 200`.
Quà lên hóa đơn giá 0¥; mục "Shipping cost" lên đúng giá. *Muốn thêm bộ mới → báo quản lý (phải sửa trong code).*

---

## 6. Khi có nhân viên mới / hàng mới về

Chạy menu **"Đồng bộ nhanh KiotViet"** — mất vài giây:
- Nhân viên mới trên KiotViet → có ngay trong dropdown "Người nhập đơn".
- Cập nhật dropdown "Hàng tặng kèm".
- SP mới nhập / đổi tên / IMEI mới → tự vá vào dữ liệu tra cứu (chỉ hỏi phần **thay đổi** từ lần đồng bộ trước, không quét lại cả kho).

Không cần chạy "Đồng bộ kho TOÀN BỘ" trừ lần cài đặt đầu tiên.

---

## 7. Lỗi thường gặp & cách xử lý

| Thông báo | Nguyên nhân | Cách sửa |
|---|---|---|
| `Cột Date: dữ liệu bị Yamato từ chối (ES007001)` | Ngày nhận là quá khứ/hôm nay, quá gần (không kịp vận chuyển) hoặc quá xa | Sửa Date thành ngày tương lai hợp lệ, hoặc xóa trống |
| Lỗi địa chỉ `ES001014` | Địa chỉ quá dài so với khổ nhãn Yamato | Rút gọn phần 町・番地, chuyển tên tòa nhà/phòng ra phần sau |
| `Đơn BankTransfer chưa chuyển khoản` | Cột Thanh toán chưa phải `Đã chuyển khoản` | Xác nhận tiền về rồi sửa cột Thanh toán |
| `Đơn Daibiki có đặt cọc (DP) nhưng thiếu Số tiền đặt cọc` | Ghi DP mà quên số cọc | Điền số vào cột Số tiền đặt cọc |
| `Đã có sẵn trên Yamato từ trước (không tạo lại)` | Đơn trùng — đã tạo lần trước | Không phải lỗi; xem chi tiết ngày tạo trong popup |
| `SP quản lý IMEI — cần điền IMEI` | Máy có IMEI mà ô IMEI trống | Gõ 5 số cuối IMEI để hệ thống tra |
| `IMEI ... đã bán / không còn trong kho` | Máy đã bán hoặc IMEI sai | Kiểm tra lại máy thực tế đang cầm |
| `IMEI ... còn hàng nhưng ở chi nhánh khác` | Máy thuộc chi nhánh khác | Chỉ bán được máy thuộc chi nhánh hiện tại (Akihabara) |
| `Sai tên sản phẩm: ô ghi ... nhưng SP mã ... là ...` | Tên trong ô bị sửa tay / chọn nhầm | Chọn lại SP từ gợi ý (đừng gõ đè tên) |
| `SP KiotViet ... chỉ khớp x% với Product Number` | SP chọn không giống mô tả hàng → nghi bán nhầm máy | Đối chiếu lại IMEI với mô tả ở Product Number |
| `Đơn Daibiki chưa có Mã vận đơn Yamato` | Tạo hóa đơn trước khi tạo vận đơn | Chạy "Tạo vận đơn cho đơn hợp lệ" trước |
| `Đã bỏ qua N dòng vì đã có hóa đơn` | Chống đẩy trùng hóa đơn | Muốn tạo lại thật: xóa ô "Hóa đơn KiotViet" của dòng đó rồi chạy lại |
| Popup `⚠ Sheet bị thay đổi trong lúc xử lý` | Có người sort/thêm/xóa dòng khi hệ thống đang chạy | Không sort/xóa dòng khi đang xử lý; chạy lại các dòng được liệt kê |

**Nguyên tắc chung:** dòng lỗi luôn được ghi rõ **Cột bị lỗi** + **Tên lỗi** ngay trên dòng đó. Sửa đúng cột được chỉ, bôi đen dòng, chạy lại menu tương ứng.

---

## 8. Cài đặt lần đầu (chỉ quản lý)

1. **Cấu hình API key** → nhập `B2_API_KEY` (key server B2 trên Render).
2. **Cấu hình KiotViet API** → nhập Client ID, Client Secret, tên gian hàng (`jamobileno1`). Lấy tại KiotViet → Thiết lập → Thiết lập kết nối API.
3. **Đồng bộ kho KiotViet (TOÀN BỘ)** → chạy 1 lần để có dữ liệu nền (danh mục SP + chỉ mục IMEI + các dropdown).
4. Từ đó về sau chỉ dùng **Đồng bộ nhanh**.

Yêu cầu phía KiotViet (đã cấu hình sẵn, ghi lại để biết): gian hàng phải bật **"Sử dụng tính năng giao hàng"**; đối tác giao hàng ヤマト Nagoya phải tồn tại trong danh sách đối tác; khoản thu khác mã `THK000001` (決済手数料) phải có trong "Các khoản thu khác".

---

## 9. Những điều KHÔNG được làm

- **Không sort / thêm / xóa dòng** trong lúc hệ thống đang chạy (đang hiện toast "Đang xử lý...").
- **Không xóa cột ẩn `_kvCode`**, các sheet ẩn `KiotViet_Catalog`, `KiotViet_ImeiIndex`.
- **Không sửa tay** các cột hệ thống ghi (Trạng thái, Tên lỗi, pdf_url, Hóa đơn KiotViet, Mã vận đơn của đơn Yamato).
- **Không gõ đè tên** vào cột "Tên sản phẩm Kiot Việt" — luôn chọn từ gợi ý hoặc để IMEI tự điền.
- Không đổi tên các cột tiêu đề — hệ thống nhận diện cột theo đúng tên header.
