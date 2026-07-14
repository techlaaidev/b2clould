const B2_API_BASE_URL = "https://b2cloud-9ma8.onrender.com";


function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("B2 Cloud")
    .addItem("Cấu hình API key", "setupApiKey")
    .addSeparator()
    .addItem("Kiểm tra và đồng bộ đơn", "validateAndSyncOrders")
    .addItem("Tạo vận đơn cho đơn hợp lệ", "createReadyShipments")
    .addItem("Sửa dropdown Đơn vị giao hàng", "fixCarrierDropdown")
    .addItem("Điền cột Price từ Product Number", "fillPriceColumnFromProductNumber")
    .addSeparator()
    .addItem("Tạo CSV Japan Post (YuPack R)", "generateJapanPostCsv")
    .addSeparator()
    .addItem("Cấu hình KiotViet API", "setupKiotVietApi")
    .addItem("Đồng bộ kho KiotViet", "syncKiotVietCatalog")
    .addItem("Tạo hóa đơn KiotViet", "createKiotVietInvoices")
    .addItem("Tạo lại hóa đơn KiotViet (test)", "recreateKiotVietInvoicesTest")
    .addItem("Xem IMEI của SP (test)", "kvShowImeis")
    .addToUi();
}


function setupApiKey() {
  const ui = SpreadsheetApp.getUi();
  const result = ui.prompt(
    "B2 API Key",
    "Nhập B2_API_KEY đã cấu hình trên Render:",
    ui.ButtonSet.OK_CANCEL
  );

  if (result.getSelectedButton() !== ui.Button.OK) return;

  const apiKey = result.getResponseText().trim();
  if (!apiKey) throw new Error("API key không được để trống.");

  PropertiesService.getScriptProperties().setProperty("B2_API_KEY", apiKey);
  ui.alert("Đã lưu API key.");
}


function validateAndSyncOrders() {
  runWithAlert_("Đang kiểm tra và đồng bộ đơn hàng...", () => {
    const sheet = SpreadsheetApp.getActiveSheet();
    const read = readRows_(sheet);
    if (!read.rows.length) return "Chưa chọn dòng nào. Hãy bôi đen các dòng cần xử lý rồi chạy lại.";

    // Kiểm tra dữ liệu ngay trên sheet trước — dòng lỗi được báo tại chỗ, không
    // gửi lên server (nhanh hơn nhiều). Dòng đã có mã vận đơn vẫn gửi để đồng bộ.
    const part = partitionRowsLocally_(sheet, read, true);
    if (!part.valid.length) return localOnlySummary_(part);

    const result = callB2Api_("/api/orders/validate", { rows: part.valid });
    const warning = writeRowsByPosition_(sheet, result.rows, part.validSheetRows, part.valid);
    return localSummary_(part) + summarizeRows_(result.rows) + warning + localErrorDetails_(part);
  });
}


function createReadyShipments() {
  runWithAlert_("Đang kiểm tra dữ liệu trên sheet...", () => {
    const sheet = SpreadsheetApp.getActiveSheet();
    const read = readRows_(sheet);
    if (!read.rows.length) return "Chưa chọn dòng nào. Hãy bôi đen các dòng cần xử lý rồi chạy lại.";

    ensureHeader_(sheet, "pdf_url");

    // Bước 1: kiểm tra dữ liệu ngay trên sheet. Dòng lỗi → ghi "Không tạo đơn"
    // + tên cột + lỗi tiếng Việt tại chỗ, KHÔNG gửi lên server. Dòng hợp lệ →
    // đánh dấu "Chờ tạo đơn" rồi mới gửi lên Yamato B2.
    const part = partitionRowsLocally_(sheet, read, false);
    if (!part.valid.length) return localOnlySummary_(part);

    SpreadsheetApp.getActive().toast(
      "Dữ liệu hợp lệ: " + part.valid.length + " đơn. Đang gửi lên Yamato B2...", "B2 Cloud", 15);

    const result = callB2Api_("/api/orders/create", {
      rows: part.valid,
      issue_pdf: true,
      include_pdf_base64: true
    });

    // PDF GỘP: server in cả loạt vào 1 file (2 nhãn / tờ A4) — lưu 1 lần lên
    // Drive rồi dán cùng 1 link vào cột pdf_url của mọi dòng trong loạt.
    const batchUrls = {};
    const batchLinks = [];
    (result.batch_pdfs || []).forEach(batch => {
      if (!batch.pdf_base64) return;
      const url = savePdfToDrive_(batch.pdf_base64, batch.pdf_filename);
      batchUrls[batch.pdf_filename] = url;
      batchLinks.push(url);
    });
    result.rows.forEach(row => {
      if (row.pdf_batch && batchUrls[row.pdf_batch]) row.pdf_url = batchUrls[row.pdf_batch];
      delete row.pdf_batch;
      if (!row.pdf_base64) return; // tương thích server cũ (PDF từng đơn)
      row.pdf_url = savePdfToDrive_(row.pdf_base64, row.pdf_filename || `${row.order_id}.pdf`);
      delete row.pdf_base64;
    });

    const warning = writeRowsByPosition_(sheet, result.rows, part.validSheetRows, part.valid);
    const pdfNote = batchLinks.length
      ? "\n\nPDF in gộp (mở 1 file, in tất cả nhãn):\n" + batchLinks.join("\n")
      : "";
    return localSummary_(part) + summarizeRows_(result.rows) + pdfNote + warning + localErrorDetails_(part);
  });
}


// ===== Kiểm tra dữ liệu ngay trên sheet (trước khi gửi lên server) =====
// Chặn sớm lỗi thiếu/sai dữ liệu để không phải chờ server, và báo đúng tên cột
// cần sửa bằng tiếng Việt. Server vẫn kiểm tra lần cuối (tách địa chỉ, Yamato...).

// Trả về danh sách lỗi [{col, msg}] của một dòng; rỗng = hợp lệ.
function localValidateRow_(row) {
  const errors = [];
  const need = (col, msg) => {
    if (!String(row[col] || "").trim()) errors.push({ col: col, msg: msg });
  };
  need("Name", "Thiếu tên người nhận (cột Name)");
  need("Postcode", "Thiếu mã bưu điện (cột Postcode)");
  need("Address", "Thiếu địa chỉ (cột Address)");
  need("Mobile", "Thiếu số điện thoại (cột Mobile)");
  need("Product Number", "Thiếu sản phẩm (cột Product Number)");

  // Cột Price = SỐ TIỀN THU HỘ cuối cùng (đã trừ sẵn đặt cọc DP) — được ưu
  // tiên; giá ở cuối Product Number chỉ là fallback cho dòng cũ chưa có Price.
  const prod = String(row["Product Number"] || "").trim();
  const priceRaw = String(row["Price"] || "").trim();
  const priceCell = priceRaw ? parsePriceCell_(priceRaw) : null;
  if (priceRaw && priceCell == null) {
    errors.push({ col: "Price", msg: 'Cột Price phải là số (ví dụ 61300), đang là "' + priceRaw + '"' });
  } else if (prod && priceCell == null && parsePriceFromProductNumber_(prod) == null) {
    errors.push({ col: "Price", msg: 'Thiếu giá bán: điền số vào cột Price (hoặc ở cuối cột Product Number, ví dụ "iPhone 13 128GB - 61300")' });
  }

  const ttype = String(row["Type of transaction"] || "").trim();
  const pay = String(row["Thanh toán"] || "").trim();
  if (!ttype) {
    errors.push({ col: "Type of transaction", msg: "Thiếu cột Type of transaction (chọn Daibiki hoặc BankTransfer)" });
  } else if (ttype === "Daibiki") {
    if (pay && pay.toUpperCase() !== "DP") {
      errors.push({ col: "Thanh toán", msg: 'Cột Thanh toán không hợp lệ cho đơn Daibiki: "' + pay + '" (để trống hoặc điền DP)' });
    } else if (pay.toUpperCase() === "DP") {
      const deposit = String(row["Số tiền đặt cọc"] || "").replace(/[.,\s]/g, "");
      if (!deposit) {
        // Có cột Price (đã trừ sẵn đặt cọc) thì không bắt buộc Số tiền đặt cọc nữa.
        if (priceCell == null) {
          errors.push({ col: "Số tiền đặt cọc", msg: "Đơn Daibiki có đặt cọc (DP) nhưng thiếu cột Số tiền đặt cọc" });
        }
      } else if (!/^\d+$/.test(deposit)) {
        errors.push({ col: "Số tiền đặt cọc", msg: "Cột Số tiền đặt cọc phải là số" });
      }
    }
  } else if (ttype === "BankTransfer") {
    if (pay !== "Đã chuyển khoản") {
      errors.push({ col: "Thanh toán", msg: 'Đơn BankTransfer chưa chuyển khoản — cột Thanh toán phải là "Đã chuyển khoản"' });
    }
    if (!String(row["Bank Account"] || row["Back account"] || "").trim()) {
      errors.push({ col: "Bank Account", msg: "Đơn BankTransfer thiếu cột Bank Account" });
    }
  } else {
    errors.push({ col: "Type of transaction", msg: 'Cột Type of transaction không hợp lệ: "' + ttype + '" (chỉ nhận Daibiki hoặc BankTransfer)' });
  }
  return errors;
}


// Giá bán từ cột Price riêng: số nguyên (cho phép dấu . , khoảng trắng và đuôi y/¥).
function parsePriceCell_(text) {
  const digits = String(text || "").trim().replace(/[y¥]\s*$/i, "").replace(/[.,\s]/g, "");
  return digits && /^\d+$/.test(digits) ? Number(digits) : null;
}


// Lấy giá bán ở cuối ô Product Number: số sau dấu '-' cuối cùng, cho phép đuôi y/¥.
function parsePriceFromProductNumber_(text) {
  const match = String(text || "").match(/-\s*([\d.,]+)\s*[y¥]?\s*$/i);
  if (!match) return null;
  const digits = match[1].replace(/[.,\s]/g, "");
  return /^\d+$/.test(digits) ? Number(digits) : null;
}


// Chia các dòng đã chọn thành: hợp lệ (gửi lên server) / lỗi dữ liệu (ghi kết
// quả tại chỗ) / bỏ qua (JAPANPOST, đã có mã vận đơn). keepTracked=true: dòng
// đã có mã vận đơn vẫn gửi (menu "Kiểm tra và đồng bộ đơn" cần chúng để đồng bộ).
function partitionRowsLocally_(sheet, read, keepTracked) {
  const headerMap = headerMap_(sheet);
  const out = {
    valid: [], validSheetRows: [],
    localErrors: [], skippedTracking: 0, skippedJapanPost: 0
  };

  read.rows.forEach((row, i) => {
    const sheetRow = read.sheetRows[i];
    const carrier = String(row["Đơn vị giao hàng"] || "").trim().toUpperCase();
    if (carrier === "JAPANPOST") { out.skippedJapanPost++; return; }

    const hasTracking = !!String(row["Mã vận đơn"] || "").trim();
    if (hasTracking && !keepTracked) { out.skippedTracking++; return; }

    const errors = hasTracking ? [] : localValidateRow_(row);
    if (!carrier) {
      errors.unshift({ col: "Đơn vị giao hàng", msg: "Thiếu cột Đơn vị giao hàng (chọn YAMATO hoặc JAPANPOST)" });
    } else if (carrier !== "YAMATO") {
      // Chỉ nhận đúng YAMATO — giá trị cũ "JAMATO" phải sửa lại (menu
      // "Sửa dropdown Đơn vị giao hàng" đổi hàng loạt một lần).
      errors.unshift({ col: "Đơn vị giao hàng", msg: 'Cột Đơn vị giao hàng không hợp lệ: "' + carrier + '" (chỉ nhận YAMATO hoặc JAPANPOST)' });
    }

    if (errors.length) {
      const cols = [];
      errors.forEach(e => { if (cols.indexOf(e.col) === -1) cols.push(e.col); });
      writeLocalResult_(sheet, sheetRow, headerMap, "Không tạo đơn",
        cols.join(", "), errors.map(e => e.msg).join("; "), "Thất bại");
      out.localErrors.push("• " + (row["Name"] || ("Dòng " + sheetRow)) + " — " + errors.map(e => e.msg).join("; "));
      return;
    }

    // Hợp lệ, sắp gửi lên Yamato B2 → trạng thái "Chờ tạo đơn", xoá lỗi cũ.
    if (!hasTracking) writeLocalResult_(sheet, sheetRow, headerMap, "Chờ tạo đơn", "", "", "");
    out.valid.push(row);
    out.validSheetRows.push(sheetRow);
  });
  return out;
}


// Ghi kết quả kiểm tra cục bộ vào đúng dòng: trạng thái + cột bị lỗi + tên lỗi.
function writeLocalResult_(sheet, sheetRow, headerMap, status, errorCols, errorMsg, autoStatus) {
  const setCell = (header, value) => {
    if (headerMap[header]) sheet.getRange(sheetRow, headerMap[header]).setValue(value);
  };
  setCell("Trạng thái khởi tạo", status);
  setCell("Cột bị lỗi", errorCols);
  setCell("Tên lỗi", errorMsg);
  setCell("Trạng thái tạo đơn hàng tự động trên yamato", autoStatus);
}


function localSummary_(part) {
  let out = "";
  if (part.localErrors.length) out += "Không tạo đơn (lỗi dữ liệu, chưa gửi lên Yamato): " + part.localErrors.length + "\n";
  if (part.skippedTracking) out += "Bỏ qua (đã có mã vận đơn): " + part.skippedTracking + "\n";
  if (part.skippedJapanPost) out += "Bỏ qua (đơn JAPANPOST — xuất CSV riêng): " + part.skippedJapanPost + "\n";
  return out;
}


function localErrorDetails_(part) {
  if (!part.localErrors.length) return "";
  return "\n\nLỗi dữ liệu (sửa xong hãy chạy lại các dòng này):\n" + part.localErrors.slice(0, 15).join("\n");
}


function localOnlySummary_(part) {
  const out = localSummary_(part) + localErrorDetails_(part);
  return out.trim() || "Không có dòng nào cần xử lý.";
}


// Đặt lại dropdown cột "Đơn vị giao hàng" về đúng 2 lựa chọn YAMATO / JAPANPOST,
// đồng thời đổi hàng loạt các ô đang ghi "JAMATO" (cách viết cũ) thành "YAMATO".
// Chạy 1 lần từ menu.
function fixCarrierDropdown() {
  runWithAlert_("Đang sửa dropdown Đơn vị giao hàng...", () => {
    const sheet = SpreadsheetApp.getActiveSheet();
    const col = headerMap_(sheet)["Đơn vị giao hàng"];
    if (!col) throw new Error('Không tìm thấy cột "Đơn vị giao hàng" trên sheet này.');

    // Đổi giá trị cũ JAMATO -> YAMATO trước, để dropdown mới không báo ô sai.
    let converted = 0;
    const lastRow = sheet.getLastRow();
    if (lastRow >= 2) {
      const range = sheet.getRange(2, col, lastRow - 1, 1);
      const values = range.getValues();
      values.forEach(cells => {
        if (String(cells[0] || "").trim().toUpperCase() === "JAMATO") {
          cells[0] = "YAMATO";
          converted++;
        }
      });
      if (converted) range.setValues(values);
    }

    const rule = SpreadsheetApp.newDataValidation()
      .requireValueInList(["YAMATO", "JAPANPOST"], true)
      .setAllowInvalid(false)
      .build();
    sheet.getRange(2, col, sheet.getMaxRows() - 1, 1).setDataValidation(rule);

    let out = 'Đã đặt lại dropdown "Đơn vị giao hàng": chỉ còn YAMATO, JAPANPOST.';
    if (converted) out += "\nĐã đổi " + converted + ' ô "JAMATO" cũ thành "YAMATO".';
    return out;
  });
}


// Phí thu hộ shop thu của KHÁCH — cộng thẳng vào tiền thu hộ mọi đơn Daibiki
// (khác với 代引手数料 330-1.100¥ Yamato trừ của shop theo bậc tiền thu hộ).
const DAIBIKI_FEE = 1500;


// Điền cột Price cho MỌI dòng có Product Number. Price = số tiền THU HỘ cuối
// cùng: giá ở cuối ô Product Number, trừ Số tiền đặt cọc nếu DP, đơn Daibiki
// cộng thêm phí thu hộ theo cột "Thu khác" (ô trống -> mặc định DAIBIKI_FEE
// 1.500¥, điền 0 = không thu phí) — cùng nguồn với khoản thu THK000001 trên
// hóa đơn KiotViet nên 2 bên luôn khớp nhau.
// Chưa có cột Price → tự chèn một cột mới ngay cạnh phải Product Number.
// Ô Price đã có giá trị thì GIỮ NGUYÊN (không ghi đè giá đã sửa tay).
function fillPriceColumnFromProductNumber() {
  runWithAlert_("Đang điền cột Price từ Product Number...", () => {
    const sheet = SpreadsheetApp.getActiveSheet();
    let headers = headerRow_(sheet);
    const prodIdx = headers.indexOf("Product Number");
    if (prodIdx === -1) throw new Error('Không tìm thấy cột "Product Number" trên sheet này.');

    if (headers.indexOf("Price") === -1) {
      sheet.insertColumnAfter(prodIdx + 1);
      sheet.getRange(1, prodIdx + 2).setValue("Price");
      headers = headerRow_(sheet); // các cột sau Product Number đã dịch sang phải 1
    }
    const col = {
      prod: headers.indexOf("Product Number"),
      price: headers.indexOf("Price"),
      pay: headers.indexOf("Thanh toán"),
      deposit: headers.indexOf("Số tiền đặt cọc"),
      ttype: headers.indexOf("Type of transaction"),
      extraFee: headers.indexOf(KV_SURCHARGE_HEADER)
    };

    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return "Sheet chưa có dữ liệu.";
    const values = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getDisplayValues();
    const priceRange = sheet.getRange(2, col.price + 1, lastRow - 1, 1);
    const priceValues = priceRange.getValues();

    let filled = 0;
    let kept = 0;
    const skippedNoPrice = [];
    const skippedDeposit = [];
    values.forEach((raw, i) => {
      if (!String(raw[col.prod] || "").trim()) return; // dòng không có SP
      if (String(priceValues[i][0] || "").trim() !== "") { kept++; return; } // đã có giá → giữ nguyên

      let price = parsePriceFromProductNumber_(raw[col.prod]);
      if (price == null) { skippedNoPrice.push(i + 2); return; }

      const pay = col.pay === -1 ? "" : String(raw[col.pay] || "").trim().toUpperCase();
      if (pay === "DP") {
        const deposit = col.deposit === -1 ? null : parsePriceCell_(raw[col.deposit]);
        if (deposit == null || deposit > price) { skippedDeposit.push(i + 2); return; }
        price -= deposit;
      }
      // Đơn Daibiki: cộng phí thu hộ khách chịu (đặt cọc đủ 100% thì thôi).
      // Mức phí theo cột "Thu khác"; ô trống -> DAIBIKI_FEE, điền 0 = miễn phí.
      const ttype = col.ttype === -1 ? "" : String(raw[col.ttype] || "").trim();
      if (ttype === "Daibiki" && price > 0) {
        const fee = col.extraFee === -1 ? null : parsePriceCell_(raw[col.extraFee]);
        price += fee != null ? fee : DAIBIKI_FEE;
      }
      priceValues[i][0] = price;
      filled++;
    });
    priceRange.setValues(priceValues);

    let out = "Đã điền cột Price cho " + filled + " dòng (giá lấy từ Product Number, DP đã trừ đặt cọc, đơn Daibiki đã cộng " + DAIBIKI_FEE + "¥ phí thu hộ).";
    if (kept) out += "\n• Giữ nguyên " + kept + " dòng đã có sẵn giá trong cột Price.";
    if (skippedNoPrice.length) {
      out += "\n⚠ " + skippedNoPrice.length + " dòng không đọc được giá ở cuối Product Number (dòng: " +
        skippedNoPrice.slice(0, 20).join(", ") + ") — điền tay vào cột Price.";
    }
    if (skippedDeposit.length) {
      out += "\n⚠ " + skippedDeposit.length + " dòng DP thiếu/sai Số tiền đặt cọc (dòng: " +
        skippedDeposit.slice(0, 20).join(", ") + ") — sửa đặt cọc rồi chạy lại.";
    }
    return out;
  });
}


function callB2Api_(path, payload) {
  const apiKey = PropertiesService.getScriptProperties().getProperty("B2_API_KEY");
  if (!apiKey) throw new Error("Chưa cấu hình B2_API_KEY.");

  const response = UrlFetchApp.fetch(B2_API_BASE_URL + path, {
    method: "post",
    contentType: "application/json",
    headers: {
      "X-API-Key": apiKey
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  const text = response.getContentText();
  let data;
  try {
    data = JSON.parse(text);
  } catch (error) {
    throw new Error(`Máy chủ B2 trả lỗi (HTTP ${response.getResponseCode()}): ${text}`);
  }

  if (response.getResponseCode() >= 400) {
    throw new Error(
      `Máy chủ B2 trả lỗi (HTTP ${response.getResponseCode()}): ${data.detail || data.error || text}`
    );
  }
  return data;
}


function readRows_(sheet) {
  const values = sheet.getDataRange().getDisplayValues();
  if (values.length < 2) return { rows: [], sheetRows: [] };

  const headers = values[0].map(value => String(value).trim());
  // A row is an order if it has a customer Name or a Product Number.
  const nameCol = headers.indexOf("Name");
  const prodCol = headers.indexOf("Product Number");

  // Only process the rows the user has highlighted (selection).
  const selected = getSelectedRowSet_(sheet);

  const rows = [];
  const sheetRows = [];
  for (let i = 1; i < values.length; i++) {
    const sheetRow = i + 1; // 1-based sheet row number
    if (selected && !selected[sheetRow]) continue; // skip rows not selected

    const raw = values[i];
    const hasData =
      (nameCol >= 0 && String(raw[nameCol] || "").trim()) ||
      (prodCol >= 0 && String(raw[prodCol] || "").trim());
    if (!hasData) continue;

    const item = {};
    headers.forEach((header, index) => {
      // Skip helper columns (prefixed with "_", e.g. "_kvCode") so they are not sent to the B2 API.
      if (header && header.charAt(0) !== "_") item[header] = String(raw[index] || "").trim();
    });
    rows.push(item);
    sheetRows.push(sheetRow);
  }
  return { rows, sheetRows };
}


// Returns a set {sheetRow: true} of all rows covered by the current selection,
// supporting multiple non-contiguous ranges (Ctrl+click). null if no selection.
function getSelectedRowSet_(sheet) {
  const rangeList = sheet.getActiveRangeList();
  if (!rangeList) return null;

  const set = {};
  rangeList.getRanges().forEach(range => {
    const start = range.getRow();
    const end = start + range.getNumRows() - 1;
    for (let r = start; r <= end; r++) set[r] = true;
  });
  return set;
}


// Bản đồ header -> số cột (1-based) của dòng tiêu đề hiện tại.
function headerMap_(sheet) {
  const map = {};
  headerRow_(sheet).forEach((header, index) => {
    if (header) map[header] = index + 1;
  });
  return map;
}


function writeRowsByPosition_(sheet, rows, sheetRows, sentRows) {
  if (!rows || !rows.length) return "";

  const headerMap = headerMap_(sheet);

  // Results come back in the same order they were sent, so write by position.
  // Safety: if the sheet was sorted / rows inserted or deleted while the API
  // was running, the remembered row numbers point at the wrong rows. Before
  // writing, re-check the row's Name cell still matches what was sent; if it
  // moved, skip that row and report it instead of writing onto a stranger.
  const nameCol = headerMap["Name"];
  const mismatches = [];
  rows.forEach((row, i) => {
    const sheetRow = sheetRows[i];
    if (!sheetRow) return;
    if (nameCol && sentRows && sentRows[i]) {
      const sentName = String(sentRows[i]["Name"] || "").trim();
      const nowName = String(sheet.getRange(sheetRow, nameCol).getDisplayValue() || "").trim();
      if (sentName && nowName !== sentName) {
        mismatches.push(`Dòng ${sheetRow}: "${sentName}" đã bị di chuyển (hiện là "${nowName}") — KHÔNG ghi kết quả.`);
        return;
      }
    }
    Object.keys(row).forEach(key => {
      if (key === "pdf_base64" || !headerMap[key]) return;
      sheet.getRange(sheetRow, headerMap[key]).setValue(row[key] ?? "");
    });
  });

  if (!mismatches.length) return "";
  return "\n\n⚠ Sheet bị thay đổi trong lúc xử lý (sort/thêm/xoá dòng?):\n" +
    mismatches.join("\n") + "\nHãy chạy lại các dòng này.";
}


function ensureHeader_(sheet, header) {
  const headers = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1))
    .getDisplayValues()[0]
    .map(value => String(value).trim());

  if (headers.includes(header)) return;
  sheet.getRange(1, headers.length + 1).setValue(header);
}


function savePdfToDrive_(base64Pdf, fileName) {
  const bytes = Utilities.base64Decode(base64Pdf);
  const blob = Utilities.newBlob(bytes, "application/pdf", fileName);
  const folderId = PropertiesService.getScriptProperties().getProperty("B2_PDF_FOLDER_ID");

  if (folderId) {
    return DriveApp.getFolderById(folderId).createFile(blob).getUrl();
  }
  return DriveApp.createFile(blob).getUrl();
}


// ===== Japan Post (YuPack R / ゆうプリR) CSV export =====
// Yamato orders create labels via the B2 API; Japan Post orders can't, so we
// export them to a ゆうプリR CSV instead and write the file URL back to the
// "Link url file csv xử lí mã vận đơn" column.
const JP_SENDER_NAME = "MOBAPPY";
const JP_SENDER_PHONE = "090-2668-8868";
const JP_SENDER_ADDRESS = "愛知県名古屋市中区大須3丁目31-22";
const JP_LINK_HEADER = "Link url file csv xử lí mã vận đơn";


function generateJapanPostCsv() {
  runWithAlert_("Đang tạo CSV Japan Post...", () => {
    return buildJapanPostCsv_(SpreadsheetApp.getActiveSheet());
  });
}


function buildJapanPostCsv_(sheet) {
  const values = sheet.getDataRange().getDisplayValues();
  if (values.length < 2) return "Không có dữ liệu.";

  const headers = values[0].map(value => String(value).trim());
  const col = name => headers.indexOf(name);
  const idx = {
    name: col("Name"),
    ig: col("IG/WA Account"),
    postcode: col("Postcode"),
    address: col("Address"),
    mobile: col("Mobile"),
    product: col("Product Number"),
    date: col("Date"),
    time: col("Time"),
    carrier: col("Đơn vị giao hàng"),
    link: col(JP_LINK_HEADER)
  };

  if (idx.carrier === -1) throw new Error('Thieu cot "Đơn vị giao hàng".');
  if (idx.link === -1) throw new Error(`Thieu cot "${JP_LINK_HEADER}".`);

  const csvHeader = [
    "お届け先郵便番号", "お届け先住所1", "お届け先住所2", "お届け先氏名", "お届け先電話番号",
    "品名", "お届け希望日", "お届け希望時間帯", "ご依頼主氏名", "ご依頼主電話番号", "ご依頼主住所"
  ];
  const lines = [csvHeader.map(csvCell_).join(",")];
  const exportedRows = [];
  const selected = getSelectedRowSet_(sheet); // only highlighted rows

  for (let r = 1; r < values.length; r++) {
    const sheetRow = r + 1;
    if (selected && !selected[sheetRow]) continue;    // skip rows not selected
    const row = values[r];
    const carrier = String(row[idx.carrier] || "").trim().toUpperCase();
    if (carrier !== "JAPANPOST") continue;            // only Japan Post orders
    if (String(row[idx.link] || "").trim()) continue; // already exported
    if (!row[idx.name] || !row[idx.address]) continue; // skip incomplete rows

    let customerName = String(row[idx.name] || "");
    if (idx.ig !== -1 && row[idx.ig]) customerName += ` (${row[idx.ig]})`;

    lines.push([
      row[idx.postcode] || "",
      "", // 住所1 left blank; full address goes to 住所2 (matches old form)
      row[idx.address] || "",
      customerName,
      row[idx.mobile] || "",
      row[idx.product] || "",
      idx.date !== -1 ? (row[idx.date] || "") : "",
      idx.time !== -1 ? (row[idx.time] || "") : "",
      JP_SENDER_NAME,
      JP_SENDER_PHONE,
      JP_SENDER_ADDRESS
    ].map(csvCell_).join(","));
    exportedRows.push(r + 1);
  }

  if (!exportedRows.length) return "Không có đơn Japan Post mới để xuất CSV.";

  const ts = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyyMMdd_HHmm");
  const fileName = `YuPack_${ts}.csv`;
  const url = saveCsvToDrive_(lines.join("\n"), fileName);

  // All exported orders point to this combined CSV file.
  exportedRows.forEach(sheetRow => sheet.getRange(sheetRow, idx.link + 1).setValue(url));

  return `Đã tạo CSV Japan Post: ${exportedRows.length} đơn.\nFile: ${fileName}`;
}


function csvCell_(value) {
  return `"${String(value == null ? "" : value).replace(/"/g, '""')}"`;
}


function saveCsvToDrive_(csv, fileName) {
  const blob = Utilities.newBlob("", "text/csv", fileName).setDataFromString(csv, "UTF-8");
  const folderId = PropertiesService.getScriptProperties().getProperty("B2_PDF_FOLDER_ID");
  const file = folderId
    ? DriveApp.getFolderById(folderId).createFile(blob)
    : DriveApp.createFile(blob);
  return file.getUrl();
}


// Trạng thái nội bộ (backend) → nhãn tiếng Việt cho popup, để không hiện chữ "INVALID".
// "Đã tạo đơn" CHỈ hiện khi đơn đã được xác nhận có trên Yamato B2.
const STATUS_VI_ = {
  CREATED: "Tạo đơn MỚI thành công (đã xác nhận trên Yamato)",
  EXISTED: "Đã có sẵn trên Yamato từ trước (không tạo lại — xem ngày tạo trên B2)",
  PENDING: "Đã gửi lên Yamato, chờ xác nhận — vài phút nữa chạy 'Kiểm tra và đồng bộ đơn'",
  SAVED: "Đơn nháp đã có trên Yamato (chưa phát hành)",
  READY: "Hợp lệ, chờ tạo đơn",
  NEW: "Hợp lệ, chờ tạo đơn",
  INVALID: "Không tạo được (lỗi dữ liệu)",
  ERROR: "Không tạo được (lỗi hệ thống)",
  SKIPPED: "Bỏ qua"
};


function summarizeRows_(rows) {
  const counts = {};
  const errors = [];
  const duplicates = [];
  rows.forEach(row => {
    // Phân biệt đơn VỪA tạo mới với đơn ĐÃ CÓ SẴN trên Yamato từ trước
    // (server gắn created_now="1" khi thật sự vừa phát hành trong lần gọi này).
    let status = row.status || "UNKNOWN";
    if (status === "CREATED" && !row.created_now) status = "EXISTED";
    counts[status] = (counts[status] || 0) + 1;

    // Ưu tiên "Tên lỗi" (đã dịch tiếng Việt) thay vì error_message thô.
    const msg = row["Tên lỗi"] || row.error_message || "";
    const who = row.consignee_name || row.order_id || "";
    if (msg && (status === "INVALID" || status === "ERROR")) {
      errors.push("• " + (who ? who + " — " : "") + msg);
    }
    // Đơn trùng: báo chi tiết (ngày tạo, mã vận đơn, thu hộ) cho từng dòng.
    if (msg && status === "EXISTED") {
      duplicates.push("• " + (who ? who + " — " : "") + msg);
    }
  });
  let out = Object.keys(counts).sort()
    .map(status => `${STATUS_VI_[status] || status}: ${counts[status]}`)
    .join("\n");
  if (duplicates.length) out += "\n\n⚠ Đơn TRÙNG (không tạo lại):\n" + duplicates.slice(0, 15).join("\n");
  if (errors.length) out += "\n\nChi tiết lỗi:\n" + errors.slice(0, 15).join("\n");
  return out;
}


function runWithAlert_(message, operation) {
  const ui = SpreadsheetApp.getUi();
  SpreadsheetApp.getActive().toast(message, "B2 Cloud", 10);
  try {
    ui.alert(operation() || "Hoàn tất.");
  } catch (error) {
    ui.alert(`Lỗi: ${error.message || error}`);
    throw error;
  }
}


// ===== KiotViet product suggestions =====
// Typing a keyword into "Tên sản phẩm Kiot Việt" pops a filtered dropdown of matching
// KiotViet products. Picking one keeps the KiotViet full name in the cell and stores the
// SP code in a hidden "_kvCode" column for invoice creation. "Product Number" is left as
// free text (no dropdown). The full catalog is cached in a hidden sheet by
// "Đồng bộ kho KiotViet"; searching is local (no API call per keystroke).
const KV_TOKEN_URL = "https://id.kiotviet.vn/connect/token";
const KV_API_BASE = "https://public.kiotapi.com";
const KV_CATALOG_SHEET = "KiotViet_Catalog";
const KV_IMEI_INDEX_SHEET = "KiotViet_ImeiIndex";     // bảng ẩn IMEI→(mã SP, tên SP) lập khi đồng bộ
const KV_NAME_HEADER = "Tên sản phẩm Kiot Việt";     // column with KiotViet product autocomplete
const KV_CODE_HEADER = "_kvCode";                     // hidden column storing the picked SP code
const KV_IMEI_HEADER = "IMEI";                        // staff-filled IMEI/serial column
const KV_INVOICE_RESULT_HEADER = "Hóa đơn KiotViet";  // invoice code on success / "LỖI: ..." on failure
const KV_SELLER_HEADER = "Người nhập đơn";            // map với NGƯỜI BÁN (soldById) trên hóa đơn KiotViet
const KV_GIFT_HEADER = "Hàng tặng kèm";               // bộ quà / phụ phí thêm vào hóa đơn KiotViet
const KV_SURCHARGE_HEADER = "Thu khác";               // phí COD thu của khách -> khoản thu khác trên hóa đơn
const KV_COD_SURCHARGE_CODE = "THK000001";            // mã khoản thu 決済手数料・Cash on Delivery Fee trên KiotViet
const KV_NAME_MATCH_MIN = 0.6;                        // tên SP KiotViet phải khớp >=60% từ khoá của Product Number

// Tên bộ tặng kèm / phụ phí -> các mã SP KiotViet sẽ thêm vào hóa đơn.
// Quà tặng lên hóa đơn với giá 0¥; mục "Shipping cost ..." lấy giá bán trên
// KiotViet (fallback: số trong tên). Ô cho phép nhiều mục, ngăn cách dấu phẩy.
const KV_GIFT_SETS = {
  "SET 20W-Lightning": ["SP012564", "SP012965"],
  "20W Adapter": ["SP012564"],
  "SET 20W-CtoC": ["SP012564", "SP013652"],
  "SET 35W-CtoC (2m)": ["SP016719", "SP013963"],
  "SET 5W-Lightning": ["SP014192", "SP012966"],
  "Shipping cost 600": ["SP165674"],
  "Shipping cost 430": ["SP165675"],
  "Shipping cost 200": ["SP165676"]
};
const KV_MAX_SUGGEST = 20;
const KV_BRANCH_ID = 17397;                           // chi nhánh hiện tại; chỉ bán IMEI thuộc chi nhánh này


function setupKiotVietApi() {
  const ui = SpreadsheetApp.getUi();
  const ask = (msg) => {
    const r = ui.prompt("KiotViet API", msg, ui.ButtonSet.OK_CANCEL);
    return r.getSelectedButton() === ui.Button.OK ? r.getResponseText().trim() : null;
  };
  const id = ask("Client ID:");
  if (id === null) return;
  const secret = ask("Client Secret:");
  if (secret === null) return;
  const retailer = ask("Tên gian hàng (Retailer), vd jamobileno1:");
  if (retailer === null) return;

  const props = PropertiesService.getScriptProperties();
  if (id) props.setProperty("KV_CLIENT_ID", id);
  if (secret) props.setProperty("KV_CLIENT_SECRET", secret);
  if (retailer) props.setProperty("KV_RETAILER", retailer);
  ui.alert("Đã lưu cấu hình KiotViet.");
}


function syncKiotVietCatalog() {
  runWithAlert_("Đang đồng bộ kho KiotViet...", () => {
    const token = kvGetToken_();
    const retailer = kvProp_("KV_RETAILER");
    const pageSize = 100;
    const started = Date.now();
    const branchId = kvCurrentBranchId_();
    let current = 0;
    let total = 0;
    const rows = [];      // catalog: [code, fullName]
    const imeiRows = [];  // index:   [imei, code, fullName] — chỉ serial còn hàng ở CN hiện tại

    while (true) {
      const data = kvFetchProducts_(token, retailer, pageSize, current);
      total = data.total || 0;
      const batch = data.data || [];
      batch.forEach(p => {
        const full = p.fullName || p.name || "";
        if (full) rows.push([p.code || "", full]);
        // Chỉ lập chỉ mục IMEI còn hàng (status 1) VÀ thuộc CN hiện tại — khớp luật tạo hóa đơn.
        (p.productSerials || []).forEach(s => {
          if (Number(s.status) !== 1 || Number(s.branchId) !== branchId) return;
          const num = String(s.serialNumber || "").trim();
          if (num) imeiRows.push([num, p.code || "", full]);
        });
      });
      current += pageSize;
      if (!batch.length || current >= total) break;
      if (Date.now() - started > 300000) break; // 5-min safety; report partial
      Utilities.sleep(150); // pace requests so KiotViet doesn't drop the connection
    }

    kvWriteCatalog_(rows);
    kvWriteImeiIndex_(imeiRows);
    const sellerNote = kvApplySellerDropdown_(token, retailer) + kvApplyGiftDropdown_();
    const note = rows.length >= total ? "" : " (một phần — chạy lại để lấy tiếp)";
    return `Đã đồng bộ ${rows.length}/${total} sản phẩm KiotViet${note}.\n` +
      `Chỉ mục IMEI (CN ${branchId}): ${imeiRows.length} IMEI.` +
      (imeiRows.length ? "" : "\n⚠ 0 IMEI — endpoint danh sách không trả serial; báo lại để tôi đổi cách lấy.") +
      sellerNote;
  });
}


function onEdit(e) {
  try {
    if (!e || !e.range) return;
    const sheet = e.range.getSheet();
    if (sheet.getName() === KV_CATALOG_SHEET || sheet.getName() === KV_IMEI_INDEX_SHEET) return;
    if (e.range.getNumRows() !== 1 || e.range.getNumColumns() !== 1) return;
    if (e.range.getRow() === 1) return;

    const headers = headerRow_(sheet);
    const col = e.range.getColumn();

    // Gõ IMEI → tự tra tên SP từ chỉ mục (lập khi đồng bộ).
    const imeiCol = headers.indexOf(KV_IMEI_HEADER) + 1;
    if (imeiCol !== 0 && col === imeiCol) { kvFillNameFromImei_(e, sheet, headers); return; }

    const prodCol = headers.indexOf(KV_NAME_HEADER) + 1;
    if (prodCol === 0 || col !== prodCol) return;

    const catalog = kvLoadCatalog_();
    if (!catalog) return; // not synced → stay out of the way

    const codeCol = kvEnsureCodeColumn_(sheet);
    const row = e.range.getRow();
    const val = (e.value == null ? "" : String(e.value)).trim();

    if (!val) { // cleared → reset row
      sheet.getRange(row, codeCol).clearContent();
      e.range.clearDataValidations();
      return;
    }

    // Picked a suggestion (exact catalog fullName) → keep the KiotViet name + store SP code.
    if (Object.prototype.hasOwnProperty.call(catalog.byName, val)) {
      e.range.clearDataValidations();
      sheet.getRange(row, codeCol).setValue(catalog.byName[val]);
      SpreadsheetApp.getActive().toast("✓ Đã chọn SP " + catalog.byName[val], "KiotViet", 5);
      return;
    }

    // Always search and always show the dropdown, regardless of the row's state.
    const matches = kvSearch_(catalog.names, val, KV_MAX_SUGGEST);
    if (!matches.length) {
      e.range.clearDataValidations();
      SpreadsheetApp.getActive().toast('Không thấy SP khớp "' + val + '"', "KiotViet", 4);
      return;
    }
    e.range.setDataValidation(
      SpreadsheetApp.newDataValidation().requireValueInList(matches, true).setAllowInvalid(true).build()
    );
    SpreadsheetApp.getActive().toast(matches.length + " gợi ý — bấm ▼ để chọn", "KiotViet", 5);
  } catch (err) {
    SpreadsheetApp.getActive().toast("KiotViet: " + (err.message || err), "Lỗi", 5);
  }
}


// Chuẩn hoá tên SP để so khớp: bỏ khoảng trắng thừa 2 đầu + gộp khoảng trắng giữa.
// Dùng để đối chiếu tên trong ô với fullName thật trên KiotViet (chặn sai tên).
function kvNorm_(name) {
  return String(name == null ? "" : name).trim().replace(/\s+/g, " ");
}


function kvSearch_(names, query, max) {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return [];
  const out = [];
  for (let i = 0; i < names.length && out.length < max; i++) {
    const lower = names[i].toLowerCase();
    if (tokens.every(t => lower.indexOf(t) !== -1)) out.push(names[i]);
  }
  return out;
}


function kvLoadCatalog_() {
  const sh = SpreadsheetApp.getActive().getSheetByName(KV_CATALOG_SHEET);
  if (!sh || sh.getLastRow() < 2) return null;
  const vals = sh.getRange(2, 1, sh.getLastRow() - 1, 2).getValues();
  const names = [];
  const byName = {};
  vals.forEach(r => {
    const name = String(r[1] || "");
    if (!name) return;
    names.push(name);
    byName[name] = String(r[0] || "");
  });
  return { names, byName };
}


function kvWriteCatalog_(rows) {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(KV_CATALOG_SHEET);
  if (!sh) sh = ss.insertSheet(KV_CATALOG_SHEET);
  sh.clearContents();
  sh.getRange(1, 1, 1, 2).setValues([["code", "fullName"]]);
  if (rows.length) sh.getRange(2, 1, rows.length, 2).setValues(rows);
  sh.hideSheet();
}


// Gõ IMEI vào cột IMEI → tra bảng chỉ mục (lập khi đồng bộ) → tự điền tên SP + _kvCode.
// - IMEI trống: không đụng gì (giữ tên đang có).
// - IMEI không có trong kho CN hiện tại (sai / đã bán / CN khác): xoá tên + mã (không điền gì).
// Nhân viên chỉ cần gõ 5 SỐ CUỐI của IMEI (hoặc nhiều hơn / đủ IMEI):
// - khớp đúng 1 IMEI → tự ghi IMEI ĐẦY ĐỦ lại vào ô (tạo hóa đơn cần đủ số)
//   và điền tên SP + mã.
// - nhiều IMEI cùng đuôi → hiện dropdown các IMEI đầy đủ để chọn.
function kvFillNameFromImei_(e, sheet, headers) {
  const nameCol = headers.indexOf(KV_NAME_HEADER) + 1;
  if (nameCol === 0) return; // chưa có cột tên SP → bỏ qua
  const codeCol = kvEnsureCodeColumn_(sheet);
  const row = e.range.getRow();
  // PASTE không có e.value (chỉ gõ tay mới có) → đọc lại giá trị từ ô.
  let typed = (e.value == null ? "" : String(e.value)).trim();
  if (!typed) typed = String(e.range.getDisplayValue() || "").trim();
  // Số IMEI dài bị Sheets hiển thị dạng khoa học (3.5E+14) → khôi phục đủ chữ số.
  if (/^\d+(\.\d+)?e\+?\d+$/i.test(typed)) typed = Number(typed).toFixed(0);
  if (!typed) return;

  const index = kvLoadImeiIndex_();
  if (!index) {
    SpreadsheetApp.getActive().toast('Chưa có chỉ mục IMEI. Chạy "Đồng bộ kho KiotViet".', "KiotViet", 5);
    return;
  }

  const nameCell = sheet.getRange(row, nameCol);
  nameCell.clearDataValidations();

  let imei = typed;
  let hit = index.byImei[imei];
  if (!hit && /^\d+$/.test(typed)) {
    if (typed.length < 5) {
      SpreadsheetApp.getActive().toast(
        'Gõ ít nhất 5 số cuối của IMEI (đang gõ ' + typed.length + ' số).', "KiotViet", 5);
      return;
    }
    // Tìm theo đuôi: mọi IMEI trong kho CN hiện tại kết thúc bằng số vừa gõ.
    const matches = Object.keys(index.byImei).filter(k => k.length > typed.length && k.endsWith(typed));
    if (matches.length === 1) {
      imei = matches[0];
      hit = index.byImei[imei];
      e.range.setValue(imei); // ghi IMEI đầy đủ — tạo hóa đơn KiotViet cần đủ số
    } else if (matches.length > 1) {
      e.range.setDataValidation(
        SpreadsheetApp.newDataValidation()
          .requireValueInList(matches.slice(0, KV_MAX_SUGGEST), true)
          .setAllowInvalid(true).build()
      );
      SpreadsheetApp.getActive().toast(
        matches.length + ' IMEI cùng đuôi "' + typed + '" — bấm ▼ chọn IMEI đầy đủ.', "KiotViet", 6);
      return;
    }
  }

  if (!hit) {
    e.range.clearDataValidations();
    nameCell.clearContent();
    sheet.getRange(row, codeCol).clearContent();
    SpreadsheetApp.getActive().toast(
      'Không tìm thấy sản phẩm nào có IMEI đuôi "' + typed + '" trong kho KiotViet (chi nhánh ' + kvCurrentBranchId_() + '). Kiểm tra lại IMEI.',
      "KiotViet — không tìm thấy sản phẩm", 8);
    return;
  }
  e.range.clearDataValidations(); // xoá dropdown gợi ý còn lại từ lần gõ trước
  nameCell.setValue(hit.name);
  sheet.getRange(row, codeCol).setValue(hit.code);

  // Cảnh báo sớm nếu SP theo IMEI không khớp mô tả ở Product Number
  // (bước tạo hóa đơn sẽ CHẶN hẳn nếu vẫn lệch).
  const prodCol = headers.indexOf("Product Number") + 1;
  if (prodCol !== 0) {
    const prodCell = sheet.getRange(row, prodCol).getDisplayValue();
    const ratio = kvNameMatchRatio_(prodCell, hit.name);
    if (ratio < KV_NAME_MATCH_MIN) {
      SpreadsheetApp.getActive().toast(
        '⚠ SP theo IMEI là "' + hit.name + '" nhưng chỉ khớp ' + Math.round(ratio * 100) +
        '% với Product Number — kiểm tra lại IMEI/máy!', "KiotViet — lệch tên SP", 8);
      return;
    }
  }
  SpreadsheetApp.getActive().toast("✓ " + hit.name, "KiotViet", 5);
}


function kvLoadImeiIndex_() {
  const sh = SpreadsheetApp.getActive().getSheetByName(KV_IMEI_INDEX_SHEET);
  if (!sh || sh.getLastRow() < 2) return null;
  const vals = sh.getRange(2, 1, sh.getLastRow() - 1, 3).getValues();
  const byImei = {};
  vals.forEach(r => {
    const imei = String(r[0] || "").trim();
    if (imei) byImei[imei] = { code: String(r[1] || ""), name: String(r[2] || "") };
  });
  return { byImei };
}


function kvWriteImeiIndex_(rows) {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(KV_IMEI_INDEX_SHEET);
  if (!sh) sh = ss.insertSheet(KV_IMEI_INDEX_SHEET);
  sh.clearContents();
  sh.getRange(1, 1, 1, 3).setValues([["imei", "code", "fullName"]]);
  if (rows.length) sh.getRange(2, 1, rows.length, 3).setValues(rows);
  sh.hideSheet();
}


function kvEnsureCodeColumn_(sheet) {
  const headers = headerRow_(sheet);
  const idx = headers.indexOf(KV_CODE_HEADER);
  if (idx !== -1) return idx + 1;
  const col = headers.length + 1;
  sheet.getRange(1, col).setValue(KV_CODE_HEADER);
  sheet.hideColumns(col);
  return col;
}


function headerRow_(sheet) {
  return sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1))
    .getDisplayValues()[0]
    .map(value => String(value).trim());
}


function kvGetToken_() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get("KV_TOKEN");
  if (cached) return cached;

  const resp = UrlFetchApp.fetch(KV_TOKEN_URL, {
    method: "post",
    payload: {
      scopes: "PublicApi",
      grant_type: "client_credentials",
      client_id: kvProp_("KV_CLIENT_ID"),
      client_secret: kvProp_("KV_CLIENT_SECRET")
    },
    muteHttpExceptions: true
  });
  const text = resp.getContentText();
  if (resp.getResponseCode() >= 400) throw new Error(`KiotViet token HTTP ${resp.getResponseCode()}: ${text.slice(0, 200)}`);
  const token = JSON.parse(text).access_token;
  if (!token) throw new Error(`KiotViet token rỗng: ${text.slice(0, 200)}`);
  cache.put("KV_TOKEN", token, 21600); // 6h
  return token;
}


function kvFetchProducts_(token, retailer, pageSize, currentItem) {
  const url = `${KV_API_BASE}/products?pageSize=${pageSize}&currentItem=${currentItem}&includeInventory=false&includeSerials=true`;
  const options = {
    method: "get",
    headers: { Authorization: "Bearer " + token, Retailer: retailer },
    muteHttpExceptions: true
  };
  // KiotViet drops the connection ("Địa chỉ không khả dụng") when called too fast,
  // a connection-level error that muteHttpExceptions can't catch → retry with backoff.
  let lastErr;
  for (let attempt = 1; attempt <= 4; attempt++) {
    try {
      const resp = UrlFetchApp.fetch(url, options);
      const code = resp.getResponseCode();
      const text = resp.getContentText();
      if (code >= 400) throw new Error(`HTTP ${code}: ${text.slice(0, 150)}`);
      return JSON.parse(text);
    } catch (err) {
      lastErr = err;
      Utilities.sleep(800 * attempt); // 0.8s, 1.6s, 2.4s
    }
  }
  throw new Error(`KiotViet products lỗi (currentItem=${currentItem}) sau 4 lần thử: ${lastErr && (lastErr.message || lastErr)}`);
}


function kvProp_(key) {
  const value = PropertiesService.getScriptProperties().getProperty(key);
  if (!value) throw new Error(`Chưa cấu hình ${key}. Chạy menu "Cấu hình KiotViet API".`);
  return value;
}


// ===== KiotViet invoice creation =====
// For each selected row that has a KiotViet product (picked from the "Tên sản phẩm Kiot Việt"
// dropdown → "_kvCode" filled), create one invoice on KiotViet. The IMEI cell, if filled, is
// sent as the serial number so KiotViet validates it: a non-existent IMEI, an already-sold
// IMEI, or an IMEI that belongs to a different product all make KiotViet reject the invoice.
// On rejection we DO NOT create the invoice and write the KiotViet error back to the row.
// Customer = "IG/WA Account" (tra có sẵn → dùng lại, chưa có → tạo mới); trống → khách lẻ.
// Price = product basePrice from KiotViet; branch = chi nhánh hiện tại (17397).
// Menu thường: bỏ qua dòng đã có hóa đơn (không đẩy trùng).
function createKiotVietInvoices() { kvRunCreateInvoices_(false); }

// Menu test: ĐẨY LẠI cả dòng đã có hóa đơn (ghi đè mã HĐ mới). Dùng khi test.
function recreateKiotVietInvoicesTest() { kvRunCreateInvoices_(true); }

function kvRunCreateInvoices_(force) {
  runWithAlert_(force ? "Đang tạo LẠI hóa đơn KiotViet (test)..." : "Đang tạo hóa đơn KiotViet...", () => {
    const sheet = SpreadsheetApp.getActiveSheet();
    const headers = headerRow_(sheet);
    const nameCol = headers.indexOf(KV_NAME_HEADER);
    const codeCol = headers.indexOf(KV_CODE_HEADER);
    const imeiCol = headers.indexOf(KV_IMEI_HEADER);
    const prodNumCol = headers.indexOf("Product Number");
    const sellerCol = headers.indexOf(KV_SELLER_HEADER);
    const giftCol = headers.indexOf(KV_GIFT_HEADER);
    const surchargeCol = headers.indexOf(KV_SURCHARGE_HEADER);
    const ttypeCol = headers.indexOf("Type of transaction");
    const giftProductCache = {}; // mã SP tặng kèm -> product (tránh gọi API lặp trong 1 lần chạy)
    let codSurcharge = null;     // khoản thu THK000001 trên KiotViet (tải 1 lần khi cần)
    // Cột khách hàng: tên khách = "IG/WA Account" (unique); SĐT/email/địa chỉ để tạo khách đầy đủ.
    const igCol = headers.indexOf("IG/WA Account");
    const mobileCol = headers.indexOf("Mobile");
    const emailCol = headers.indexOf("Email");
    const addrCol = headers.indexOf("Address");
    if (nameCol === -1) {
      throw new Error(`Thiếu cột "${KV_NAME_HEADER}". Hãy tạo cột này cạnh "Product Number".`);
    }
    if (codeCol === -1) {
      throw new Error(`Chưa có mã SP. Hãy chọn sản phẩm từ gợi ý ở cột "${KV_NAME_HEADER}" trước.`);
    }

    const resultCol = ensureHeaderReturnCol_(sheet, KV_INVOICE_RESULT_HEADER);
    const values = sheet.getDataRange().getDisplayValues();
    const selected = getSelectedRowSet_(sheet);

    const token = kvGetToken_();
    const retailer = kvProp_("KV_RETAILER");
    const soldByDefault = kvGetDefaultUserId_(token, retailer);
    let kvUsers = null; // danh sách người bán — chỉ tải khi có dòng điền "Người nhập đơn"

    let ok = 0;
    let okFee = 0; // hóa đơn có gửi Thu khác kèm theo
    let fail = 0;
    let skipped = 0;
    const errors = [];
    const custCache = {}; // tên khách (lowercase) → customerId, tránh tạo trùng trong 1 lần chạy

    for (let i = 1; i < values.length; i++) {
      const sheetRow = i + 1;
      if (selected && !selected[sheetRow]) continue;

      const raw = values[i];
      const name = String(raw[nameCol] || "").trim();
      const code = String(raw[codeCol] || "").trim();
      const imei = imeiCol === -1 ? "" : String(raw[imeiCol] || "").trim();
      if (!name && !code) continue; // empty row

      // Đã có mã hóa đơn (không phải LỖI) → bỏ qua để không đẩy trùng.
      // Trừ khi force (menu "Tạo lại ... test") thì vẫn đẩy lại, ghi đè mã mới.
      const existing = String(raw[resultCol - 1] || "").trim();
      if (!force && existing && existing.indexOf("LỖI") !== 0) { skipped++; continue; }

      try {
        if (!code) throw new Error(`Chưa chọn SP KiotViet (thiếu mã). Chọn lại từ gợi ý ở cột "${KV_NAME_HEADER}".`);
        const resolved = kvResolveForInvoice_(token, retailer, code, imei);
        // Chặn sai tên: tên trong ô phải khớp fullName thật của SP mã "code" trên KiotViet.
        // Dù IMEI đúng, tên lệch (chọn nhầm/sửa tay) vẫn KHÔNG tạo hóa đơn.
        const kvName = String(resolved.product.fullName || resolved.product.name || "").trim();
        if (kvNorm_(name) !== kvNorm_(kvName)) {
          throw new Error(`Sai tên sản phẩm: ô ghi "${name || "(trống)"}" nhưng SP mã "${code}" trên KiotViet là "${kvName}". Chọn lại SP từ gợi ý ở cột "${KV_NAME_HEADER}".`);
        }
        // Chặn bán nhầm máy: tên SP KiotViet phải khớp đủ từ khoá với mô tả
        // hàng ở cột Product Number (>= KV_NAME_MATCH_MIN).
        if (prodNumCol !== -1) {
          const ratio = kvNameMatchRatio_(raw[prodNumCol], kvName);
          if (ratio < KV_NAME_MATCH_MIN) {
            throw new Error('SP KiotViet "' + kvName + '" chỉ khớp ' + Math.round(ratio * 100) +
              '% với cột Product Number "' + String(raw[prodNumCol] || "").trim() +
              '" (cần ≥ ' + Math.round(KV_NAME_MATCH_MIN * 100) + '%). Kiểm tra lại IMEI / sản phẩm.');
          }
        }

        // Đơn Daibiki: cộng khoản thu khác 決済手数料 (COD fee) vào hóa đơn.
        // Số tiền lấy từ cột "Thu khác"; ô trống -> mặc định DAIBIKI_FEE.
        let surcharges = [];
        const isDaibikiKv = ttypeCol !== -1 &&
          String(raw[ttypeCol] || "").trim().toLowerCase() === "daibiki";
        if (isDaibikiKv) {
          const cellFee = surchargeCol === -1 ? null : parsePriceCell_(raw[surchargeCol]);
          const fee = cellFee != null ? cellFee : DAIBIKI_FEE;
          if (fee > 0) {
            if (!codSurcharge) codSurcharge = kvFindCodSurcharge_(token, retailer);
            // Gửi đủ các biến thể tên trường KiotViet có thể yêu cầu (id/code/giá).
            surcharges = [{
              id: codSurcharge.id,
              surchargeId: codSurcharge.id,
              code: codSurcharge.surchargeCode || codSurcharge.code || KV_COD_SURCHARGE_CODE,
              surchargeName: codSurcharge.surchargeName || "Cash on Delivery Fee",
              surValue: fee,
              surValueRatio: 0,
              price: fee
            }];
          }
        }

        // Gắn khách hàng theo cột IG/WA Account (tra có sẵn → dùng lại, chưa có → tạo mới).
        const custName = igCol === -1 ? "" : String(raw[igCol] || "").trim();
        let customerId = null;
        if (custName) {
          const key = custName.toLowerCase();
          if (Object.prototype.hasOwnProperty.call(custCache, key)) {
            customerId = custCache[key];
          } else {
            customerId = kvResolveCustomerId_(token, retailer, custName, {
              contactNumber: mobileCol === -1 ? "" : String(raw[mobileCol] || "").trim(),
              email: emailCol === -1 ? "" : String(raw[emailCol] || "").trim(),
              address: addrCol === -1 ? "" : String(raw[addrCol] || "").trim(),
              branchId: resolved.branchId
            });
            custCache[key] = customerId;
          }
        }

        // Người bán trên hóa đơn: cột "Người nhập đơn" (khớp tên trên KiotViet);
        // để trống → người bán mặc định (user đầu tiên / KV_SOLD_BY_ID).
        let soldById = soldByDefault;
        const sellerName = sellerCol === -1 ? "" : String(raw[sellerCol] || "").trim();
        if (sellerName) {
          if (!kvUsers) kvUsers = kvFetchUsers_(token, retailer);
          soldById = kvResolveSellerId_(kvUsers, sellerName);
        }

        // SP giá 0 trên KiotViet → lấy GIÁ HÀNG gốc ở cuối cột Product Number.
        // KHÔNG dùng cột Price: Price = tiền thu hộ (đơn Daibiki đã cộng
        // 1.500¥ phí, DP đã trừ cọc) nên không phải giá bán của sản phẩm.
        const paidPrice = prodNumCol === -1 ? null : parsePriceFromProductNumber_(raw[prodNumCol]);

        // Hàng tặng kèm / phụ phí: thêm các SP của bộ đã chọn vào hóa đơn.
        const giftText = giftCol === -1 ? "" : String(raw[giftCol] || "").trim();
        const giftDetails = giftText
          ? kvResolveGiftDetails_(token, retailer, giftText, giftProductCache)
          : [];

        const invoice = kvCreateInvoice_(
          token, retailer, resolved.branchId, soldById, resolved.product, resolved.serialNumbers, customerId, paidPrice, giftDetails, surcharges,
          isDaibikiKv
        );
        const invCode = invoice.code || invoice.id || "OK";
        sheet.getRange(sheetRow, resultCol).setValue(invCode);
        ok++;
        // Tự kiểm chứng: đọc lại hóa đơn vừa tạo xem KiotViet có GHI NHẬN
        // khoản Thu khác không (API có thể âm thầm bỏ qua trường này).
        if (surcharges.length) {
          okFee++;
          if (invoice.id && !kvInvoiceHasSurcharge_(token, retailer, invoice.id)) {
            errors.push("⚠ Dòng " + sheetRow + ": hóa đơn " + invCode +
              " tạo OK nhưng KiotViet KHÔNG ghi nhận khoản Thu khác gửi kèm (API bỏ qua) — báo lại để đổi cách cộng phí.");
          }
        }
      } catch (err) {
        sheet.getRange(sheetRow, resultCol).setValue("LỖI: " + (err.message || err));
        errors.push(`Dòng ${sheetRow}: ${err.message || err}`);
        fail++;
      }
    }

    if (!ok && !fail) {
      if (skipped) {
        return `Đã bỏ qua ${skipped} dòng vì đã có hóa đơn (không đẩy trùng).\n` +
          `Muốn đẩy lại (test): dùng menu "Tạo lại hóa đơn KiotViet (test)", ` +
          `hoặc xoá ô "${KV_INVOICE_RESULT_HEADER}" của dòng đó rồi tạo lại.`;
      }
      return "Không có hàng nào để tạo hóa đơn. Hãy bôi đen các dòng có sản phẩm KiotViet.";
    }
    let summary = `Tạo hóa đơn KiotViet:\n✓ Thành công: ${ok} (${okFee} hóa đơn có gửi Thu khác)\n✗ Lỗi: ${fail}`;
    if (skipped) summary += `\n• Bỏ qua (đã có HĐ): ${skipped}`;
    if (errors.length) summary += "\n\n" + errors.slice(0, 10).join("\n");
    return summary;
  });
}


function kvGetDefaultUserId_(token, retailer) {
  // Manual override (set KV_SOLD_BY_ID in Script Properties) wins over auto-detect.
  const override = PropertiesService.getScriptProperties().getProperty("KV_SOLD_BY_ID");
  if (override) return Number(override);

  const cache = CacheService.getScriptCache();
  const cached = cache.get("KV_SOLD_BY_ID");
  if (cached) return Number(cached);

  const list = kvFetchUsers_(token, retailer);
  if (!list.length) throw new Error("Không lấy được người bán (user) KiotViet.");
  const id = list[0].id;
  cache.put("KV_SOLD_BY_ID", String(id), 21600); // 6h
  return id;
}


// 代引手数料 Yamato trừ của SHOP theo bậc giá trị đơn hàng (KHÔNG tính Thu
// khác) — ghi thành giảm trừ trên hóa đơn KiotViet để doanh thu khớp tiền
// thực nhận. Chỉ áp cho đơn ship Daibiki.
function yamatoCodFee_(value) {
  if (!value || value <= 0) return 0;
  if (value <= 9999) return 330;
  if (value <= 29999) return 440;
  if (value <= 99999) return 660;
  return 1100; // 100,000 - 300,000円
}


// Đọc lại hóa đơn vừa tạo để kiểm chứng KiotViet có ghi nhận khoản Thu khác không.
function kvInvoiceHasSurcharge_(token, retailer, invoiceId) {
  try {
    const resp = UrlFetchApp.fetch(KV_API_BASE + "/invoices/" + encodeURIComponent(invoiceId), {
      method: "get",
      headers: { Authorization: "Bearer " + token, Retailer: retailer },
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() >= 400) return true; // không đọc được -> đừng báo nhầm
    const data = JSON.parse(resp.getContentText());
    const inv = data && (data.data || data);
    return !!(inv && inv.invoiceOrderSurcharges && inv.invoiceOrderSurcharges.length);
  } catch (ignore) {
    return true; // lỗi mạng/parse -> bỏ qua kiểm chứng, không báo nhầm
  }
}


// Tra khoản thu khác (Các khoản thu khác) trên KiotViet theo mã KV_COD_SURCHARGE_CODE.
function kvFindCodSurcharge_(token, retailer) {
  const resp = UrlFetchApp.fetch(KV_API_BASE + "/surchages?pageSize=100", {
    method: "get",
    headers: { Authorization: "Bearer " + token, Retailer: retailer },
    muteHttpExceptions: true
  });
  const text = resp.getContentText();
  if (resp.getResponseCode() >= 400) {
    throw new Error(`KiotViet surchages HTTP ${resp.getResponseCode()}: ${text.slice(0, 150)}`);
  }
  const list = (JSON.parse(text).data) || [];
  const hit = list.filter(s =>
    String(s.surchargeCode || s.code || "").trim().toUpperCase() === KV_COD_SURCHARGE_CODE)[0];
  if (!hit) {
    throw new Error('Không tìm thấy khoản thu ' + KV_COD_SURCHARGE_CODE +
      ' trong "Các khoản thu khác" trên KiotViet. Kiểm tra lại cấu hình KiotViet.');
  }
  return hit;
}


// Từ khoá mô tả hàng ở ô Product Number: bỏ nhãn thanh toán đầu (COD/CK/TF...)
// và giá ở cuối, tách thành các token chữ+số để so với tên SP KiotViet.
function productNameTokens_(prodCell) {
  let text = String(prodCell || "").trim();
  text = text.replace(/-\s*[\d.,]+\s*[y¥]?\s*$/i, "");      // bỏ giá cuối
  text = text.replace(/^(cod|ck|tf|dp|db)[\s_:.\-]+/i, ""); // bỏ nhãn thanh toán đầu
  return text.toLowerCase().match(/[a-z0-9%]+/g) || [];
}


// Tỷ lệ từ khoá của Product Number xuất hiện trong tên SP KiotViet (0..1).
// So trên chuỗi đã bỏ hết ký tự ngăn cách nên "promax" vẫn khớp "Pro Max".
function kvNameMatchRatio_(prodCell, kvName) {
  const tokens = productNameTokens_(prodCell);
  if (!tokens.length) return 1; // không có gì để so → không chặn
  const hay = String(kvName || "").toLowerCase().replace(/[^a-z0-9%]+/g, "");
  const matched = tokens.filter(t => hay.indexOf(t) !== -1).length;
  return matched / tokens.length;
}


// Ô "Hàng tặng kèm" -> các dòng hóa đơn KiotViet bổ sung. Cho phép nhiều mục
// ngăn cách bởi dấu phẩy / + / ; . Quà tặng lên hóa đơn giá 0¥; mục
// "Shipping cost ..." lấy giá bán trên KiotViet (fallback: số trong tên).
function kvResolveGiftDetails_(token, retailer, cellText, productCache) {
  const details = [];
  const parts = String(cellText || "").split(/[,+;\n]/).map(s => s.trim()).filter(Boolean);
  parts.forEach(part => {
    const key = Object.keys(KV_GIFT_SETS)
      .filter(k => kvNorm_(k).toLowerCase() === kvNorm_(part).toLowerCase())[0];
    if (!key) {
      throw new Error('Không hiểu mục tặng kèm "' + part + '". Hợp lệ: ' + Object.keys(KV_GIFT_SETS).join(", "));
    }
    KV_GIFT_SETS[key].forEach(code => {
      let product = productCache[code];
      if (!product) {
        product = kvGetProductWithSerials_(token, retailer, code);
        if (!product || !product.id) throw new Error('Không tìm thấy SP tặng kèm mã "' + code + '" trên KiotViet.');
        productCache[code] = product;
      }
      const isShipping = /^shipping cost/i.test(key);
      const base = product.basePrice != null ? Number(product.basePrice) : 0;
      const priceInName = Number((key.match(/\d+/) || [0])[0]);
      details.push({
        productId: product.id,
        productCode: product.code,
        productName: product.fullName || product.name || "",
        quantity: 1,
        price: isShipping ? (base > 0 ? base : priceInName) : 0
      });
    });
  });
  return details;
}


// Gắn dropdown các bộ tặng kèm / phụ phí cho cột "Hàng tặng kèm" (nếu có).
// setAllowInvalid(true) để vẫn gõ tay được nhiều mục: "SET 20W-CtoC, Shipping cost 600".
function kvApplyGiftDropdown_() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const col = headerMap_(sheet)[KV_GIFT_HEADER];
  if (!col) return "";
  const rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(Object.keys(KV_GIFT_SETS), true)
    .setAllowInvalid(true).build();
  sheet.getRange(2, col, sheet.getMaxRows() - 1, 1).setDataValidation(rule);
  return '\nDropdown "' + KV_GIFT_HEADER + '": ' + Object.keys(KV_GIFT_SETS).length + " mục tặng kèm/phụ phí.";
}


// Gắn dropdown danh sách người bán KiotViet cho cột "Người nhập đơn" (nếu sheet
// có cột này) — chạy kèm menu "Đồng bộ kho KiotViet" nên danh sách luôn mới.
function kvApplySellerDropdown_(token, retailer) {
  const sheet = SpreadsheetApp.getActiveSheet();
  const col = headerMap_(sheet)[KV_SELLER_HEADER];
  if (!col) return "";
  const names = kvFetchUsers_(token, retailer)
    .map(u => String(u.givenName || u.userName || "").trim())
    .filter(Boolean);
  if (!names.length) return "";
  const rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(names, true).setAllowInvalid(true).build();
  sheet.getRange(2, col, sheet.getMaxRows() - 1, 1).setDataValidation(rule);
  return '\nDropdown "' + KV_SELLER_HEADER + '": ' + names.length + " người bán (" + names.join(", ") + ").";
}


// Danh sách người bán (user) trên KiotViet — dùng cho cột "Người nhập đơn".
function kvFetchUsers_(token, retailer) {
  const resp = UrlFetchApp.fetch(KV_API_BASE + "/users?pageSize=100", {
    method: "get",
    headers: { Authorization: "Bearer " + token, Retailer: retailer },
    muteHttpExceptions: true
  });
  const text = resp.getContentText();
  if (resp.getResponseCode() >= 400) {
    throw new Error(`KiotViet users HTTP ${resp.getResponseCode()}: ${text.slice(0, 150)}`);
  }
  return (JSON.parse(text).data) || [];
}


// Tên ở cột "Người nhập đơn" -> id người bán trên KiotViet. Khớp theo tên
// hiển thị (givenName) hoặc tên đăng nhập (userName), không phân biệt hoa/thường.
function kvResolveSellerId_(users, name) {
  const target = kvNorm_(name).toLowerCase();
  const hit = users.filter(u =>
    kvNorm_(u.givenName).toLowerCase() === target ||
    kvNorm_(u.userName).toLowerCase() === target)[0];
  if (!hit) {
    const known = users.map(u => u.givenName || u.userName).filter(Boolean).join(", ");
    throw new Error('Không tìm thấy người bán "' + name + '" trên KiotViet. Tên hợp lệ: ' + known);
  }
  return hit.id;
}


// Chi nhánh dùng để xuất mọi hóa đơn. Mặc định KV_BRANCH_ID (17397);
// có thể override bằng Script Property "KV_BRANCH_ID".
function kvCurrentBranchId_() {
  const override = PropertiesService.getScriptProperties().getProperty("KV_BRANCH_ID");
  return override ? Number(override) : KV_BRANCH_ID;
}


// Resolves a row to everything the invoice needs and validates the IMEI against KiotViet.
// Hóa đơn LUÔN xuất ở chi nhánh hiện tại (kvCurrentBranchId_), nên chỉ chấp nhận IMEI
// vừa còn hàng (status 1) VỪA thuộc đúng chi nhánh đó.
//   - product (id, code, name, basePrice)
//   - branchId: luôn = chi nhánh hiện tại
//   - serialNumbers: the IMEI to attach (empty for non-serial products)
// Throws a clear Vietnamese error (→ written to the sheet, invoice NOT created) when:
//   - SP quản lý IMEI nhưng ô IMEI trống
//   - IMEI không thuộc SP này (sai IMEI / nhập nhầm)
//   - IMEI đã bán / không còn trong kho
//   - IMEI còn hàng nhưng ở chi nhánh khác
//   - SP hết hàng ở chi nhánh hiện tại
function kvResolveForInvoice_(token, retailer, code, imei) {
  const branchId = kvCurrentBranchId_();
  let product = kvGetProductWithSerials_(token, retailer, code);
  if (!product || !product.id) throw new Error(`Không tìm thấy SP mã "${code}" trên KiotViet.`);

  let serialsRaw = product.productSerials || [];
  if (!serialsRaw.length && product.isLotSerialControl) {
    const byId = kvGetProductByIdWithSerials_(token, retailer, product.id);
    if (byId) { product = byId; serialsRaw = byId.productSerials || []; }
  }

  const imeiTrim = String(imei || "").trim();

  if (product.isLotSerialControl) {
    if (!imeiTrim) throw new Error(`SP quản lý IMEI — cần điền IMEI vào cột "${KV_IMEI_HEADER}".`);
    const matches = serialsRaw.filter(s => String(s.serialNumber).trim() === imeiTrim);
    if (!matches.length) throw new Error(`Không tìm thấy sản phẩm khớp IMEI "${imeiTrim}" trên KiotViet (sai IMEI hoặc nhập nhầm).`);
    // Chỉ IMEI còn hàng (status 1) VÀ ở đúng chi nhánh hiện tại mới bán được ở đây.
    const sellable = matches.filter(s => Number(s.status) === 1 && Number(s.branchId) === branchId)[0];
    if (!sellable) {
      const inStockElsewhere = matches.some(s => Number(s.status) === 1);
      throw new Error(inStockElsewhere
        ? `IMEI "${imeiTrim}" còn hàng nhưng ở chi nhánh khác (không thuộc chi nhánh ${branchId}).`
        : `IMEI "${imeiTrim}" đã bán / không còn trong kho.`);
    }
    return { product: product, branchId: branchId, serialNumbers: imeiTrim };
  }

  // Non-serial product → cần còn hàng ở đúng chi nhánh hiện tại; ignore any IMEI typed.
  const inv = (product.inventories || [])
    .filter(i => Number(i.branchId) === branchId && Number(i.onHand) > 0)[0];
  if (!inv) throw new Error(`SP "${code}" hết hàng ở chi nhánh ${branchId}.`);
  return { product: product, branchId: branchId, serialNumbers: "" };
}


// fallbackPrice: giá lấy từ cột Product Number (số tiền khách đã trả) — chỉ dùng
// khi SP trên KiotViet để giá 0/không có giá, để hóa đơn không bị 0 đồng.
// giftDetails: các dòng hóa đơn bổ sung từ cột "Hàng tặng kèm" (có thể rỗng).
// surcharges: các khoản thu khác (COD fee THK000001 cho đơn Daibiki, có thể rỗng).
// isDaibiki: đơn ship Daibiki -> trừ 代引手数料 Yamato (bậc theo giá hàng) vào hóa đơn.
function kvCreateInvoice_(token, retailer, branchId, soldById, product, serialNumbers, customerId, fallbackPrice, giftDetails, surcharges, isDaibiki) {
  const basePrice = product.basePrice != null ? Number(product.basePrice) : 0;
  const price = basePrice > 0 ? basePrice : (fallbackPrice != null ? fallbackPrice : 0);
  const detail = {
    productId: product.id,
    productCode: product.code,
    productName: product.fullName || product.name || "",
    quantity: 1,
    price: price
  };
  if (serialNumbers) detail.serialNumbers = serialNumbers;

  const payload = {
    branchId: branchId,
    soldById: soldById, // KiotViet requires a real seller user id
    isApplyVoucher: false,
    invoiceDetails: [detail].concat(giftDetails || [])
  };
  if (customerId) payload.customerId = customerId; // gắn khách; bỏ trống → khách lẻ
  if (surcharges && surcharges.length) payload.invoiceOrderSurcharges = surcharges;
  // Đơn Daibiki: trừ 代引手数料 Yamato (330/440/660/1.100¥ theo bậc GIÁ HÀNG,
  // không tính Thu khác) dưới dạng giảm giá hóa đơn -> tổng hóa đơn = tiền
  // thực nhận về tài khoản.
  if (isDaibiki) {
    const codFee = yamatoCodFee_(price);
    if (codFee > 0) payload.discount = codFee;
  }

  const resp = UrlFetchApp.fetch(KV_API_BASE + "/invoices", {
    method: "post",
    contentType: "application/json",
    headers: { Authorization: "Bearer " + token, Retailer: retailer },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  const text = resp.getContentText();
  let data = null;
  try { data = JSON.parse(text); } catch (ignore) { /* non-JSON error body */ }

  if (resp.getResponseCode() >= 400) {
    const reason =
      (data && data.responseStatus && data.responseStatus.message) ||
      (data && (data.message || data.detail)) ||
      text.slice(0, 250);
    throw new Error(reason);
  }
  return data || {};
}


// Trả customerId cho tên khách (cột IG/WA Account). Có sẵn trên KiotViet → dùng lại;
// chưa có → tạo mới (kèm SĐT/email/địa chỉ nếu có). Tên trống → null (hóa đơn khách lẻ).
// IG/WA account là username duy nhất nên khớp theo tên là đủ, không lo trùng.
function kvResolveCustomerId_(token, retailer, name, extra) {
  const clean = String(name || "").trim();
  if (!clean) return null;
  const existing = kvFindCustomerByName_(token, retailer, clean);
  if (existing && existing.id) return existing.id;
  const created = kvCreateCustomer_(token, retailer, clean, extra);
  if (!created || !created.id) throw new Error(`Tạo khách "${clean}" trên KiotViet thất bại.`);
  return created.id;
}


function kvFindCustomerByName_(token, retailer, name) {
  const url = KV_API_BASE + "/customers?name=" + encodeURIComponent(name) + "&pageSize=100";
  const resp = UrlFetchApp.fetch(url, {
    method: "get",
    headers: { Authorization: "Bearer " + token, Retailer: retailer },
    muteHttpExceptions: true
  });
  const text = resp.getContentText();
  if (resp.getResponseCode() >= 400) {
    throw new Error(`KiotViet customers HTTP ${resp.getResponseCode()}: ${text.slice(0, 150)}`);
  }
  const list = (JSON.parse(text).data) || [];
  // Filter theo tên KiotViet trả về (name có thể là khớp "chứa"); so khớp chính xác, không phân biệt hoa/thường.
  const target = kvNorm_(name).toLowerCase();
  return list.filter(c => kvNorm_(c.name).toLowerCase() === target)[0] || null;
}


function kvCreateCustomer_(token, retailer, name, extra) {
  const payload = { name: name };
  if (extra) {
    if (extra.contactNumber) payload.contactNumber = extra.contactNumber;
    if (extra.email) payload.email = extra.email;
    if (extra.address) payload.address = extra.address;
    if (extra.branchId) payload.branchId = extra.branchId;
  }
  const resp = UrlFetchApp.fetch(KV_API_BASE + "/customers", {
    method: "post",
    contentType: "application/json",
    headers: { Authorization: "Bearer " + token, Retailer: retailer },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
  const text = resp.getContentText();
  let data = null;
  try { data = JSON.parse(text); } catch (ignore) { /* non-JSON error body */ }
  if (resp.getResponseCode() >= 400) {
    const reason =
      (data && data.responseStatus && data.responseStatus.message) ||
      (data && (data.message || data.detail)) ||
      text.slice(0, 250);
    throw new Error(`Tạo khách "${name}": ${reason}`);
  }
  return (data && (data.data || data)) || {};
}


function ensureHeaderReturnCol_(sheet, header) {
  const headers = headerRow_(sheet);
  const idx = headers.indexOf(header);
  if (idx !== -1) return idx + 1;
  const col = headers.length + 1;
  sheet.getRange(1, col).setValue(header);
  return col;
}


// ===== Diagnostic: list IMEIs/serials KiotViet returns for a product =====
// Prompts for a product keyword, finds its SP code in the synced catalog, then asks
// KiotViet for that product WITH serials and shows the IMEI list. If nothing comes back
// it dumps the raw field names so we can see the real schema for this account.
function kvShowImeis() {
  const ui = SpreadsheetApp.getUi();
  const r = ui.prompt("Xem IMEI KiotViet", "Nhập tên/từ khoá sản phẩm:", ui.ButtonSet.OK_CANCEL);
  if (r.getSelectedButton() !== ui.Button.OK) return;
  const kw = r.getResponseText().trim();
  if (!kw) return;

  runWithAlert_("Đang lấy IMEI từ KiotViet...", () => {
    const catalog = kvLoadCatalog_();
    if (!catalog) throw new Error('Chưa đồng bộ kho. Chạy "Đồng bộ kho KiotViet" trước.');

    let code;
    let picked;
    if (Object.prototype.hasOwnProperty.call(catalog.byName, kw)) {
      picked = kw;
      code = catalog.byName[kw];
    } else {
      const matches = kvSearch_(catalog.names, kw, 1);
      if (!matches.length) throw new Error('Không thấy SP khớp "' + kw + '".');
      picked = matches[0];
      code = catalog.byName[matches[0]];
    }

    const token = kvGetToken_();
    const retailer = kvProp_("KV_RETAILER");
    const product = kvGetProductWithSerials_(token, retailer, code);
    if (!product) throw new Error('Không tìm thấy SP mã "' + code + '".');

    // `detail` = the object that actually carries the serial list (by-id sometimes has it
    // when the by-code response doesn't), so all raw dumps below read from `detail`.
    let detail = product;
    let allSerials = kvExtractSerials_(product);
    let triedById = false;
    if (!allSerials.length && product.isLotSerialControl && product.id) {
      triedById = true;
      const byId = kvGetProductByIdWithSerials_(token, retailer, product.id);
      if (byId) { detail = byId; allSerials = kvExtractSerials_(byId); }
    }

    // Chỉ quan tâm serial thuộc chi nhánh hiện tại (17397).
    const branchId = kvCurrentBranchId_();
    const serials = allSerials.filter(s => Number(s.branchId) === branchId);

    const onHandBranch = (detail.inventories || [])
      .filter(i => Number(i.branchId) === branchId)
      .reduce((sum, i) => sum + Number(i.onHand || 0), 0);

    let out = "SP: " + picked + "\nMã: " + code + "\n";
    out += "Quản lý IMEI (isLotSerialControl): " + product.isLotSerialControl + "\n";
    out += "Giá bán (basePrice): " +
      (product.basePrice != null ? product.basePrice : "(không có trường basePrice)") + "\n";
    out += "Chi nhánh hiện tại: " + branchId + "\n";
    out += "Tồn kho ở CN " + branchId + " (onHand): " + onHandBranch + "\n";

    if (!serials.length) {
      out += "\nKhông có IMEI/serial nào của chi nhánh " + branchId + ".\n";
      if (product.isLotSerialControl === false) {
        out += "→ SP này KHÔNG bật quản lý IMEI trong KiotViet, nên không có IMEI để đối chiếu.\n";
      } else if (allSerials.length) {
        out += "→ SP có " + allSerials.length + " serial nhưng đều thuộc chi nhánh khác.\n";
      } else {
        out += "→ SP có bật quản lý IMEI nhưng list rỗng" + (triedById ? " (đã thử cả endpoint theo id)" : "") + ".\n";
      }
    } else {
      const hist = {};
      serials.forEach(s => { const k = String(s.status); hist[k] = (hist[k] || 0) + 1; });
      const histStr = Object.keys(hist).sort().map(k => "status " + k + ": " + hist[k]).join(" | ");
      const inStock = serials.filter(s => Number(s.status) === 1);
      out += "\nSerial ở CN " + branchId + ": " + serials.length + " (gồm cả đã bán)\n";
      out += "Phân bố theo status: " + histStr + "\n";
      out += "→ status 1 = còn hàng (" + inStock.length + " cái), status 0 = đã bán.\n\n";
      out += "IMEI còn bán được ở CN " + branchId + ":\n";
      out += inStock.length
        ? inStock.slice(0, 60).map(s => "• " + s.serial).join("\n")
        : "(không có)";
    }

    // Dò trường giá: liệt kê mọi trường top-level có giá trị SỐ (để tìm trường tiền
    // ngoài basePrice), + dump riêng priceBooks (bảng giá) nếu KiotViet trả về.
    out += "\n\n--- Dò trường giá ---\n";
    const numericFields = Object.keys(product)
      .filter(k => typeof product[k] === "number")
      .map(k => k + " = " + product[k]);
    out += "Các trường dạng số: " + (numericFields.join(" | ") || "(không có)") + "\n";

    const priceBooks = product.priceBooks || product.priceBook || detail.priceBooks;
    if (priceBooks && priceBooks.length) {
      out += "priceBooks (bảng giá):\n";
      out += priceBooks.slice(0, 20).map(p =>
        "• " + (p.priceBookName || p.priceBookId || "?") + " = " + p.price).join("\n");
    } else {
      out += "priceBooks: (không có trong response)\n";
    }
    out += "\n\nTất cả tên trường KiotViet trả về:\n" + Object.keys(product).join(", ");
    return out;
  });
}


function kvGetProductWithSerials_(token, retailer, code) {
  const url = KV_API_BASE + "/products/code/" + encodeURIComponent(code) +
    "?includeSerials=true&includeInventory=true";
  const resp = UrlFetchApp.fetch(url, {
    method: "get",
    headers: { Authorization: "Bearer " + token, Retailer: retailer },
    muteHttpExceptions: true
  });
  const httpCode = resp.getResponseCode();
  const text = resp.getContentText();
  if (httpCode === 404) return null;
  if (httpCode >= 400) throw new Error(`KiotViet product HTTP ${httpCode}: ${text.slice(0, 200)}`);
  return JSON.parse(text);
}


function kvGetProductByIdWithSerials_(token, retailer, id) {
  const url = KV_API_BASE + "/products/" + encodeURIComponent(id) +
    "?includeSerials=true&includeInventory=true";
  const resp = UrlFetchApp.fetch(url, {
    method: "get",
    headers: { Authorization: "Bearer " + token, Retailer: retailer },
    muteHttpExceptions: true
  });
  const httpCode = resp.getResponseCode();
  const text = resp.getContentText();
  if (httpCode === 404) return null;
  if (httpCode >= 400) throw new Error(`KiotViet product(id) HTTP ${httpCode}: ${text.slice(0, 200)}`);
  return JSON.parse(text);
}


// Returns [{serial, status, branchId}]. KiotViet keeps every serial ever attached to the
// product (incl. already-sold ones) across all branches, so callers must filter by status
// and branchId to get the IMEIs sellable at the current branch.
function kvExtractSerials_(product) {
  const arr = product.productSerials || product.serials || product.serialNumbers || [];
  const out = [];
  (arr || []).forEach(s => {
    if (typeof s === "string") { out.push({ serial: s, status: "", branchId: "" }); return; }
    const num = s.serialNumber || s.serial || s.imei || s.code || "";
    if (!num) return;
    const status = (s.status != null) ? s.status : (s.statusValue != null ? s.statusValue : "");
    out.push({ serial: num, status: status, branchId: s.branchId });
  });
  return out;
}
