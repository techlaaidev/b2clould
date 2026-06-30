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
    .addSeparator()
    .addItem("Cấu hình KiotViet API", "setupKiotVietApi")
    .addItem("Đồng bộ kho KiotViet", "syncKiotVietCatalog")
    .addItem("Tạo hóa đơn KiotViet", "createKiotVietInvoices")
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


// ===== KiotViet product suggestions =====
// Typing a keyword into "Tên sản phẩm Kiot Việt" pops a filtered dropdown of matching
// KiotViet products. Picking one keeps the KiotViet full name in the cell and stores the
// SP code in a hidden "_kvCode" column for invoice creation. "Product Number" is left as
// free text (no dropdown). The full catalog is cached in a hidden sheet by
// "Đồng bộ kho KiotViet"; searching is local (no API call per keystroke).
const KV_TOKEN_URL = "https://id.kiotviet.vn/connect/token";
const KV_API_BASE = "https://public.kiotapi.com";
const KV_CATALOG_SHEET = "KiotViet_Catalog";
const KV_NAME_HEADER = "Tên sản phẩm Kiot Việt";     // column with KiotViet product autocomplete
const KV_CODE_HEADER = "_kvCode";                     // hidden column storing the picked SP code
const KV_IMEI_HEADER = "IMEI";                        // staff-filled IMEI/serial column
const KV_INVOICE_RESULT_HEADER = "Hóa đơn KiotViet";  // invoice code on success / "LỖI: ..." on failure
const KV_MAX_SUGGEST = 20;


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
    let current = 0;
    let total = 0;
    const rows = [];

    while (true) {
      const data = kvFetchProducts_(token, retailer, pageSize, current);
      total = data.total || 0;
      const batch = data.data || [];
      batch.forEach(p => {
        const full = p.fullName || p.name || "";
        if (full) rows.push([p.code || "", full]);
      });
      current += pageSize;
      if (!batch.length || current >= total) break;
      if (Date.now() - started > 300000) break; // 5-min safety; report partial
      Utilities.sleep(150); // pace requests so KiotViet doesn't drop the connection
    }

    kvWriteCatalog_(rows);
    const note = rows.length >= total ? "" : " (một phần — chạy lại để lấy tiếp)";
    return `Đã đồng bộ ${rows.length}/${total} sản phẩm KiotViet${note}.`;
  });
}


function onEdit(e) {
  try {
    if (!e || !e.range) return;
    const sheet = e.range.getSheet();
    if (sheet.getName() === KV_CATALOG_SHEET) return;
    if (e.range.getNumRows() !== 1 || e.range.getNumColumns() !== 1) return;
    if (e.range.getRow() === 1) return;

    const headers = headerRow_(sheet);
    const prodCol = headers.indexOf(KV_NAME_HEADER) + 1;
    if (prodCol === 0 || e.range.getColumn() !== prodCol) return;

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
  const url = `${KV_API_BASE}/products?pageSize=${pageSize}&currentItem=${currentItem}&includeInventory=false`;
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
// Price = product basePrice from KiotViet; customer = walk-in (none); branch = default branch.
function createKiotVietInvoices() {
  runWithAlert_("Đang tạo hóa đơn KiotViet...", () => {
    const sheet = SpreadsheetApp.getActiveSheet();
    const headers = headerRow_(sheet);
    const nameCol = headers.indexOf(KV_NAME_HEADER);
    const codeCol = headers.indexOf(KV_CODE_HEADER);
    const imeiCol = headers.indexOf(KV_IMEI_HEADER);
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
    const branchId = kvGetDefaultBranchId_(token, retailer);

    let ok = 0;
    let fail = 0;
    let skipped = 0;
    const errors = [];

    for (let i = 1; i < values.length; i++) {
      const sheetRow = i + 1;
      if (selected && !selected[sheetRow]) continue;

      const raw = values[i];
      const name = String(raw[nameCol] || "").trim();
      const code = String(raw[codeCol] || "").trim();
      const imei = imeiCol === -1 ? "" : String(raw[imeiCol] || "").trim();
      if (!name && !code) continue; // empty row

      // Already has a successful invoice code (not an error) → don't duplicate.
      const existing = String(raw[resultCol - 1] || "").trim();
      if (existing && existing.indexOf("LỖI") !== 0) { skipped++; continue; }

      try {
        if (!code) throw new Error(`Chưa chọn SP KiotViet (thiếu mã). Chọn lại từ gợi ý ở cột "${KV_NAME_HEADER}".`);
        const product = kvGetProductByCode_(token, retailer, code);
        if (!product || !product.id) throw new Error(`Không tìm thấy SP mã "${code}" trên KiotViet.`);

        const invoice = kvCreateInvoice_(token, retailer, branchId, product, imei);
        const invCode = invoice.code || invoice.id || "OK";
        sheet.getRange(sheetRow, resultCol).setValue(invCode);
        ok++;
      } catch (err) {
        sheet.getRange(sheetRow, resultCol).setValue("LỖI: " + (err.message || err));
        errors.push(`Dòng ${sheetRow}: ${err.message || err}`);
        fail++;
      }
    }

    if (!ok && !fail) {
      return "Không có hàng nào để tạo hóa đơn. Hãy bôi đen các dòng có sản phẩm KiotViet.";
    }
    let summary = `Tạo hóa đơn KiotViet:\n✓ Thành công: ${ok}\n✗ Lỗi: ${fail}`;
    if (skipped) summary += `\n• Bỏ qua (đã có HĐ): ${skipped}`;
    if (errors.length) summary += "\n\n" + errors.slice(0, 10).join("\n");
    return summary;
  });
}


function kvGetDefaultBranchId_(token, retailer) {
  // Manual override (set KV_BRANCH_ID in Script Properties) wins over auto-detect.
  const override = PropertiesService.getScriptProperties().getProperty("KV_BRANCH_ID");
  if (override) return Number(override);

  const cache = CacheService.getScriptCache();
  const cached = cache.get("KV_BRANCH_ID");
  if (cached) return Number(cached);

  const resp = UrlFetchApp.fetch(KV_API_BASE + "/branches", {
    method: "get",
    headers: { Authorization: "Bearer " + token, Retailer: retailer },
    muteHttpExceptions: true
  });
  const text = resp.getContentText();
  if (resp.getResponseCode() >= 400) {
    throw new Error(`KiotViet branches HTTP ${resp.getResponseCode()}: ${text.slice(0, 150)}`);
  }
  const list = (JSON.parse(text).data) || [];
  if (!list.length) throw new Error("Không lấy được chi nhánh KiotViet.");
  const id = list[0].id;
  cache.put("KV_BRANCH_ID", String(id), 21600); // 6h
  return id;
}


function kvGetProductByCode_(token, retailer, code) {
  const url = KV_API_BASE + "/products/code/" + encodeURIComponent(code);
  const resp = UrlFetchApp.fetch(url, {
    method: "get",
    headers: { Authorization: "Bearer " + token, Retailer: retailer },
    muteHttpExceptions: true
  });
  const httpCode = resp.getResponseCode();
  const text = resp.getContentText();
  if (httpCode === 404) return null;
  if (httpCode >= 400) throw new Error(`KiotViet product HTTP ${httpCode}: ${text.slice(0, 150)}`);
  return JSON.parse(text);
}


function kvCreateInvoice_(token, retailer, branchId, product, imei) {
  const detail = {
    productId: product.id,
    productCode: product.code,
    productName: product.fullName || product.name || "",
    quantity: 1,
    price: product.basePrice != null ? product.basePrice : 0
  };
  // Sending the IMEI as the serial makes KiotViet validate it against this exact product.
  if (imei) detail.serialNumbers = imei;

  const payload = {
    branchId: branchId,
    isApplyVoucher: false,
    invoiceDetails: [detail]
  };

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

    const serials = kvExtractSerials_(product);
    let out = "SP: " + picked + "\nMã: " + code + "\n";
    if (!serials.length) {
      out += "\nKhông có IMEI/serial nào KiotViet trả về cho SP này.\n";
      out += "(SP có thể không quản lý IMEI, hoặc API gói của bạn không trả serial.)\n\n";
      out += "Các field KiotViet trả về: " + Object.keys(product).join(", ");
    } else {
      out += "Số IMEI: " + serials.length + "\n\n" + serials.slice(0, 60).map(s => "• " + s).join("\n");
      if (serials.length > 60) out += "\n…(còn " + (serials.length - 60) + " IMEI nữa)";
    }
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


// KiotViet serial field name varies by account; try the common shapes and show status.
function kvExtractSerials_(product) {
  const arr = product.serials || product.productSerials || product.serialNumbers || [];
  const out = [];
  (arr || []).forEach(s => {
    if (typeof s === "string") { out.push(s); return; }
    const num = s.serialNumber || s.serial || s.imei || s.code || "";
    if (!num) return;
    const status = (s.status != null) ? s.status : (s.statusValue != null ? s.statusValue : "");
    out.push(status === "" ? num : (num + " (status " + status + ")"));
  });
  return out;
}
