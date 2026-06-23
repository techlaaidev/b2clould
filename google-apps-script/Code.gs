const B2_API_BASE_URL = "https://b2cloud-9ma8.onrender.com";


function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("B2 Cloud")
    .addItem("Cau hinh API key", "setupApiKey")
    .addSeparator()
    .addItem("Kiem tra va dong bo don", "validateAndSyncOrders")
    .addItem("Tao van don cho don hop le", "createReadyShipments")
    .addToUi();
}


function setupApiKey() {
  const ui = SpreadsheetApp.getUi();
  const result = ui.prompt(
    "B2 API Key",
    "Nhap B2_API_KEY da cau hinh tren Render:",
    ui.ButtonSet.OK_CANCEL
  );

  if (result.getSelectedButton() !== ui.Button.OK) return;

  const apiKey = result.getResponseText().trim();
  if (!apiKey) throw new Error("API key khong duoc de trong.");

  PropertiesService.getScriptProperties().setProperty("B2_API_KEY", apiKey);
  ui.alert("Da luu API key.");
}


function validateAndSyncOrders() {
  runWithAlert_("Dang kiem tra va dong bo don hang...", () => {
    const sheet = SpreadsheetApp.getActiveSheet();
    const read = readRows_(sheet);
    const result = callB2Api_("/api/orders/validate", { rows: read.rows });

    writeRowsByPosition_(sheet, result.rows, read.sheetRows);
    return summarizeRows_(result.rows);
  });
}


function createReadyShipments() {
  runWithAlert_("Dang tao van don...", () => {
    const sheet = SpreadsheetApp.getActiveSheet();
    const read = readRows_(sheet);
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
  if (!apiKey) throw new Error("Chua cau hinh B2_API_KEY.");

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

  const rows = [];
  const sheetRows = [];
  for (let i = 1; i < values.length; i++) {
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
    sheetRows.push(i + 1); // 1-based sheet row number
  }
  return { rows, sheetRows };
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
    ui.alert(operation() || "Hoan tat.");
  } catch (error) {
    ui.alert(`Loi: ${error.message || error}`);
    throw error;
  }
}
