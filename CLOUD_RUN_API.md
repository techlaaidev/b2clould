# B2 Cloud FastAPI Service

This service exposes the current dashboard workflow as API endpoints that Google Sheets Apps Script can call.

## Exposed APIs

All `/api/*` endpoints require:

```http
X-API-Key: <B2_API_KEY>
```

Public health check:

```http
GET /health
```

B2 session:

```http
GET  /api/session/status
POST /api/session/login
```

Entries from B2 Cloud:

```http
GET /api/entries?view=history&service_type=3&consignee_name=&tracking_number=
```

`view` can be:

- `history`: issued shipments
- `new`: saved shipments before issue
- `deleted`: deleted history

Tracking update:

```http
POST /api/tracking
Content-Type: application/json

{
  "view": "history",
  "service_type": "3",
  "consignee_name": "",
  "tracking_number": ""
}
```

Validate Google Sheet order rows against Yamato B2 Cloud:

```http
POST /api/orders/validate
Content-Type: application/json

{
  "rows": [
    {
      "order_id": "ORDER-001",
      "service_type": "3",
      "shipment_date": "2026/06/04",
      "consignee_name": "Test",
      "consignee_telephone_display": "090-0000-0000",
      "consignee_zip_code": "8900053",
      "consignee_address1": "鹿児島県",
      "consignee_address2": "鹿児島市",
      "consignee_address3": "中央町"
    }
  ]
}
```

Create shipments and optionally return issued PDF labels as base64:

```http
POST /api/orders/create
Content-Type: application/json

{
  "issue_pdf": true,
  "include_pdf_base64": true,
  "rows": []
}
```

Response rows include status fields such as:

- `status`
- `error_message`
- `tracking_number`
- `updated_at`
- `pdf_base64`
- `pdf_filename`

## Required Environment Variables

```text
B2_API_KEY=<secret used by Google Apps Script>
B2_CUSTOMER_CODE=<Yamato customer code>
B2_CUSTOMER_PASSWORD=<Yamato password>
B2_CUSTOMER_CLS_CODE=<optional>
B2_LOGIN_USER_ID=<optional>
```

## Run Locally

```powershell
$env:B2_API_KEY="dev-api-key"
$env:B2_CUSTOMER_CODE="..."
$env:B2_CUSTOMER_PASSWORD="..."
$env:B2_CUSTOMER_CLS_CODE=""
$env:B2_LOGIN_USER_ID=""
uvicorn scripts.api_server:app --host 127.0.0.1 --port 8080 --reload
```

## Deploy To Cloud Run

Build and deploy from this repo:

```powershell
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud run deploy b2cloud-api `
  --source . `
  --region asia-northeast1 `
  --allow-unauthenticated `
  --set-env-vars B2_API_KEY=your-api-key,B2_CUSTOMER_CODE=your-customer-code,B2_CUSTOMER_PASSWORD=your-password,B2_CUSTOMER_CLS_CODE=,B2_LOGIN_USER_ID=
```

For production, move `B2_CUSTOMER_PASSWORD` and `B2_API_KEY` to Secret Manager instead of passing them directly in the command.

## Google Apps Script Example

A complete Google Sheets workflow is available in:

```text
google-apps-script/Code.gs
```

Copy that file into `Extensions -> Apps Script`. It provides menu actions to:

- Validate rows and synchronize existing B2 shipment status/tracking number.
- Create shipments for valid rows.
- Save returned PDF labels to Google Drive and write `pdf_url` to the sheet.

Store the API key once:

```javascript
function setupApiKey() {
  PropertiesService.getScriptProperties().setProperty("B2_API_KEY", "your-api-key");
}
```

Call the API:

```javascript
function callB2Api(path, payload) {
  const baseUrl = "https://your-cloud-run-url.run.app";
  const apiKey = PropertiesService.getScriptProperties().getProperty("B2_API_KEY");

  const response = UrlFetchApp.fetch(baseUrl + path, {
    method: "post",
    contentType: "application/json",
    headers: {"X-API-Key": apiKey},
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  const text = response.getContentText();
  const data = JSON.parse(text);
  if (response.getResponseCode() >= 400) {
    throw new Error(data.detail || text);
  }
  return data;
}
```

Save a returned PDF to Drive:

```javascript
function savePdfToDrive(base64Pdf, fileName) {
  const bytes = Utilities.base64Decode(base64Pdf);
  const blob = Utilities.newBlob(bytes, "application/pdf", fileName);
  const file = DriveApp.createFile(blob);
  return file.getUrl();
}
```
