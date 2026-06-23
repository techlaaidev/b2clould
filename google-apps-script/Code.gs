const B2_API_BASE_URL = "https://b2cloud-9ma8.onrender.com";


function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("B2 Cloud")
    .addItem("Cấu hình API key", "setupApiKey")
    .addSeparator()
    .addItem("Kiểm tra và đồng bộ đơn", "validateAndSyncOrders")
    .addItem("Tạo vận đơn cho đơn hợp lệ", "createReadyShipments")
    .addSeparator()
    .addItem("Tạo CSV Japan Post (YuPack R)", "generateJapanPostCsv")
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
    const result = callB2Api_("/api/orders/validate", { rows: read.rows });

    writeRowsByPosition_(sheet, result.rows, read.sheetRows);
    return summarizeRows_(result.rows);
  });
}


function createReadyShipments() {
  runWithAlert_("Đang tạo vận đơn...", () => {
    const sheet = SpreadsheetApp.getActiveSheet();
    const read = readRows_(sheet);
    if (!read.rows.length) return "Chưa chọn dòng nào. Hãy bôi đen các dòng cần xử lý rồi chạy lại.";
    const result = callB2Api_("/api/orders/create", {
      rows: read.rows,
      issue_pdf: true,
      include_pdf_base64: true
    });

    result.rows.forEach(row => {
      if (!row.pdf_base64) return;
      row.pdf_url = savePdfToDrive_(row.pdf_base64, row.pdf_filename || `${row.order_id}.pdf`);
      delete row.pdf_base64;
    });

    ensureHeader_(sheet, "pdf_url");
    writeRowsByPosition_(sheet, result.rows, read.sheetRows);
    return summarizeRows_(result.rows);
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
    throw new Error(`API HTTP ${response.getResponseCode()}: ${text}`);
  }

  if (response.getResponseCode() >= 400) {
    throw new Error(
      `API HTTP ${response.getResponseCode()}: ${data.detail || data.error || text}`
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
      if (header) item[header] = String(raw[index] || "").trim();
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


function writeRowsByPosition_(sheet, rows, sheetRows) {
  if (!rows || !rows.length) return;

  const headers = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1))
    .getDisplayValues()[0]
    .map(value => String(value).trim());
  const headerMap = {};
  headers.forEach((header, index) => {
    if (header) headerMap[header] = index + 1;
  });

  // Results come back in the same order they were sent, so write by position.
  rows.forEach((row, i) => {
    const sheetRow = sheetRows[i];
    if (!sheetRow) return;
    Object.keys(row).forEach(key => {
      if (key === "pdf_base64" || !headerMap[key]) return;
      sheet.getRange(sheetRow, headerMap[key]).setValue(row[key] ?? "");
    });
  });
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

  for (let r = 1; r < values.length; r++) {
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


function summarizeRows_(rows) {
  const counts = {};
  rows.forEach(row => {
    const status = row.status || "UNKNOWN";
    counts[status] = (counts[status] || 0) + 1;
  });
  return Object.keys(counts)
    .sort()
    .map(status => `${status}: ${counts[status]}`)
    .join("\n");
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
