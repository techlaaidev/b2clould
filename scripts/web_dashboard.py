import json
import os
import secrets
import sys
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import b2cloud
from scripts.orders_csv import OUTPUT_COLUMNS, create_shipment, validate_local


HOST = "127.0.0.1"
PORT = int(os.environ.get("B2_DASHBOARD_PORT", "8080"))
SESSIONS = {}
LAST_SESSION_ID = ""
LABEL_DIR = Path(__file__).resolve().parents[1] / "data" / "labels"


SERVICE_TYPES = {
    "": "All",
    "0": "Takkyubin prepaid",
    "3": "Kuroneko Yu-Mail (DM)",
    "4": "Time",
    "5": "Cash on delivery",
    "7": "Nekopos",
    "8": "Compact",
}


INDEX_HTML = r"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>B2 Cloud Dashboard</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #18202b;
      --muted: #667085;
      --accent: #0f766e;
      --accent-strong: #115e59;
      --danger: #b42318;
      --warn: #b54708;
      --shadow: 0 1px 2px rgba(16, 24, 40, .08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      background: #fff;
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 5;
    }
    .brand { font-weight: 700; font-size: 17px; }
    .layout {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      min-height: calc(100vh - 56px);
    }
    aside {
      border-right: 1px solid var(--line);
      background: #fff;
      padding: 18px;
    }
    main { padding: 18px; min-width: 0; }
    h2 { font-size: 15px; margin: 0 0 12px; }
    label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin: 12px 0 5px;
    }
    input, select {
      width: 100%;
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }
    input[type="file"] {
      height: auto;
      padding: 7px;
    }
    input[type="checkbox"] {
      width: 16px;
      height: 16px;
      padding: 0;
    }
    button {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 12px;
      background: #fff;
      color: var(--text);
      font: inherit;
      cursor: pointer;
      white-space: nowrap;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    button.primary:hover { background: var(--accent-strong); }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .row { display: flex; gap: 8px; align-items: center; }
    .stack { display: grid; gap: 10px; }
    .actions { margin-top: 14px; display: grid; gap: 8px; }
    .toolbar {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }
    .tabs { display: flex; gap: 6px; }
    .tab.active {
      background: #e6f4f1;
      border-color: #99d6ce;
      color: #0b5d56;
      font-weight: 600;
    }
    .status {
      min-height: 22px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }
    .status.error { color: var(--danger); }
    .status.warn { color: var(--warn); }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      box-shadow: var(--shadow);
    }
    .metric span { display: block; color: var(--muted); font-size: 12px; }
    .metric strong { display: block; font-size: 22px; margin-top: 4px; }
    .table-wrap {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: auto;
      box-shadow: var(--shadow);
      max-height: calc(100vh - 210px);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 980px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f9fafb;
      color: #475467;
      font-size: 12px;
      font-weight: 600;
    }
    tbody tr:hover { background: #f7fbfa; }
    .muted { color: var(--muted); }
    .mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
    .hidden { display: none; }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">B2 Cloud Dashboard</div>
    <div class="row">
      <span id="loginState" class="muted">Not connected</span>
      <button id="logoutBtn" class="hidden">Logout</button>
    </div>
  </header>
  <div class="layout">
    <aside>
      <section>
        <h2>Login</h2>
        <label>Customer code - required</label>
        <input id="customerCode" autocomplete="username" placeholder="0522286598 or 0522286598-001">
        <label>Password - required</label>
        <input id="customerPassword" type="password" autocomplete="current-password">
        <label>Code after hyphen - optional</label>
        <input id="customerClsCode" placeholder="Only if Yamato shows a value after '-'">
        <label>Personal user ID - optional</label>
        <input id="loginUserId" placeholder="個人ユーザーID">
        <div class="actions">
          <button id="loginBtn" class="primary">Login</button>
        </div>
      </section>
      <section style="margin-top:22px">
        <h2>Filters</h2>
        <label>Service type</label>
        <select id="serviceType"></select>
        <label>Consignee name</label>
        <input id="consigneeName" placeholder="Name contains...">
        <label>Tracking number</label>
        <input id="trackingNumber" placeholder="Exact number">
        <div class="actions">
          <button id="loadBtn">Load data</button>
          <button id="trackingBtn">Update tracking</button>
          <button id="exportBtn">Export CSV</button>
        </div>
      </section>
      <section style="margin-top:22px">
        <h2>Orders CSV</h2>
        <label>Import CSV from Excel or Google Sheets</label>
        <input id="ordersFile" type="file" accept=".csv,text/csv">
        <div class="row" style="margin-top:10px">
          <input id="issuePdf" type="checkbox" checked>
          <span class="muted">Issue PDF and tracking</span>
        </div>
        <div class="actions">
          <button id="validateOrdersBtn">Validate orders</button>
          <button id="createOrdersBtn" class="primary">Create shipments</button>
          <button id="exportOrdersBtn">Export orders CSV</button>
        </div>
      </section>
      <p id="status" class="status"></p>
    </aside>
    <main>
      <div class="toolbar">
        <div class="tabs">
          <button class="tab active" data-view="history">Issued history</button>
          <button class="tab" data-view="new">Saved before issue</button>
          <button class="tab" data-view="deleted">Deleted history</button>
          <button class="tab" data-view="orders">Orders CSV</button>
        </div>
        <div class="muted" id="lastLoaded">No data loaded</div>
      </div>
      <div class="summary">
        <div class="metric"><span>Total rows</span><strong id="mTotal">0</strong></div>
        <div class="metric"><span>With tracking</span><strong id="mTracking">0</strong></div>
        <div class="metric"><span>Service type</span><strong id="mService">-</strong></div>
        <div class="metric"><span>Current view</span><strong id="mView">History</strong></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr id="headerRow">
              <th>Tracking</th>
              <th>Consignee</th>
              <th>Ship date</th>
              <th>Service</th>
              <th>Status</th>
              <th>Telephone</th>
              <th>Address</th>
              <th>Shipment No.</th>
            </tr>
          </thead>
          <tbody id="rows">
            <tr><td colspan="8" class="muted">Login and load data.</td></tr>
          </tbody>
        </table>
      </div>
    </main>
  </div>
  <script>
    const state = { view: "history", rows: [], orders: [] };
    const orderColumns = %ORDER_COLUMNS%;
    const serviceTypes = %SERVICE_TYPES%;
    const $ = (id) => document.getElementById(id);

    function setStatus(message, kind) {
      $("status").textContent = message || "";
      $("status").className = "status" + (kind ? " " + kind : "");
    }

    function setBusy(busy) {
      for (const id of ["loginBtn", "loadBtn", "trackingBtn", "exportBtn", "validateOrdersBtn", "createOrdersBtn", "exportOrdersBtn"]) {
        $(id).disabled = busy;
      }
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        ...options
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        if (data.error === "Not logged in.") {
          setLoggedOut();
        }
        throw new Error(data.error || response.statusText);
      }
      return data;
    }

    function setLoggedOut() {
      $("loginState").textContent = "Not connected";
      $("logoutBtn").classList.add("hidden");
    }

    function entryToRow(entry) {
      const s = entry.shipment || {};
      const address = [
        s.consignee_address1,
        s.consignee_address2,
        s.consignee_address3,
        s.consignee_address4
      ].filter(Boolean).join(" ");
      return {
        tracking: s.tracking_number || "",
        consignee: s.consignee_name || "",
        shipDate: s.shipment_date || s.shipment_result_date || "",
        service: s.service_type || "",
        status: s.tracking_status_name || s.shipment_status_name || s.shipment_flg || "",
        telephone: s.consignee_telephone_display || s.consignee_telephone || "",
        address,
        shipmentNo: s.shipment_number || ""
      };
    }

    function render(entries) {
      state.rows = entries.map(entryToRow);
      $("headerRow").innerHTML = `
        <th>Tracking</th>
        <th>Consignee</th>
        <th>Ship date</th>
        <th>Service</th>
        <th>Status</th>
        <th>Telephone</th>
        <th>Address</th>
        <th>Shipment No.</th>
      `;
      const tbody = $("rows");
      if (!state.rows.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="muted">No rows found.</td></tr>';
      } else {
        tbody.innerHTML = state.rows.map(row => `
          <tr>
            <td class="mono">${escapeHtml(row.tracking)}</td>
            <td>${escapeHtml(row.consignee)}</td>
            <td>${escapeHtml(row.shipDate)}</td>
            <td>${escapeHtml(serviceTypes[row.service] || row.service)}</td>
            <td>${escapeHtml(row.status)}</td>
            <td>${escapeHtml(row.telephone)}</td>
            <td>${escapeHtml(row.address)}</td>
            <td class="mono">${escapeHtml(row.shipmentNo)}</td>
          </tr>
        `).join("");
      }
      $("mTotal").textContent = state.rows.length;
      $("mTracking").textContent = state.rows.filter(row => row.tracking).length;
      $("mService").textContent = serviceTypes[$("serviceType").value] || $("serviceType").value || "All";
      $("mView").textContent = state.view === "history" ? "History" : state.view === "new" ? "Saved" : "Deleted";
      $("lastLoaded").textContent = "Loaded " + new Date().toLocaleString();
    }

    function renderOrders(rows) {
      state.orders = rows;
      $("headerRow").innerHTML = orderColumns.map(column => `<th>${escapeHtml(column)}</th>`).join("");
      const tbody = $("rows");
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="${orderColumns.length}" class="muted">Import an orders CSV file.</td></tr>`;
      } else {
        tbody.innerHTML = rows.map(row => `
          <tr>
            ${orderColumns.map(column => `<td>${escapeHtml(row[column] || "")}</td>`).join("")}
          </tr>
        `).join("");
      }
      $("mTotal").textContent = rows.length;
      $("mTracking").textContent = rows.filter(row => row.tracking_number).length;
      $("mService").textContent = "Orders";
      $("mView").textContent = "Orders";
      $("lastLoaded").textContent = rows.length ? "Orders loaded " + new Date().toLocaleString() : "No orders loaded";
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[c]));
    }

    async function login() {
      setBusy(true);
      setStatus("Logging in...");
      try {
        const parsedCode = parseCustomerCode($("customerCode").value, $("customerClsCode").value);
        await api("/api/login", {
          method: "POST",
          body: JSON.stringify({
            customer_code: parsedCode.code,
            customer_password: $("customerPassword").value,
            customer_cls_code: parsedCode.clsCode,
            login_user_id: $("loginUserId").value
          })
        });
        $("loginState").textContent = "Connected";
        $("logoutBtn").classList.remove("hidden");
        setStatus("Login successful.");
        await loadData();
      } catch (err) {
        setStatus(err.message, "error");
      } finally {
        setBusy(false);
      }
    }

    function parseCustomerCode(codeValue, clsValue) {
      const raw = String(codeValue || "").trim();
      const cls = String(clsValue || "").trim();
      if (raw.includes("-") && !cls) {
        const parts = raw.split("-");
        return { code: parts[0].trim(), clsCode: parts.slice(1).join("-").trim() };
      }
      return { code: raw, clsCode: cls };
    }

    async function loadData() {
      if (state.view === "orders") {
        renderOrders(state.orders);
        return;
      }
      setBusy(true);
      setStatus("Loading data...");
      try {
        const params = new URLSearchParams({
          view: state.view,
          service_type: $("serviceType").value,
          consignee_name: $("consigneeName").value,
          tracking_number: $("trackingNumber").value
        });
        const data = await api("/api/entries?" + params.toString());
        render(data.entries || []);
        setStatus("Data loaded.");
      } catch (err) {
        setStatus(err.message, "error");
      } finally {
        setBusy(false);
      }
    }

    async function updateTracking() {
      if (state.view !== "history") {
        setStatus("Tracking update is available only for issued history.", "warn");
        return;
      }
      setBusy(true);
      setStatus("Updating tracking...");
      try {
        const data = await api("/api/tracking", {
          method: "POST",
          body: JSON.stringify({
            service_type: $("serviceType").value,
            consignee_name: $("consigneeName").value,
            tracking_number: $("trackingNumber").value
          })
        });
        render(data.entries || []);
        setStatus("Tracking updated.");
      } catch (err) {
        setStatus(err.message, "error");
      } finally {
        setBusy(false);
      }
    }

    function exportCsv() {
      if (state.view === "orders") {
        exportOrdersCsv();
        return;
      }
      const header = ["tracking", "consignee", "shipDate", "service", "status", "telephone", "address", "shipmentNo"];
      const lines = [header.join(",")].concat(state.rows.map(row =>
        header.map(key => '"' + String(row[key] ?? "").replace(/"/g, '""') + '"').join(",")
      ));
      const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "b2cloud-" + state.view + ".csv";
      a.click();
      URL.revokeObjectURL(url);
    }

    function parseCsv(text) {
      const rows = [];
      let row = [];
      let cell = "";
      let quoted = false;
      for (let i = 0; i < text.length; i++) {
        const c = text[i];
        const next = text[i + 1];
        if (quoted) {
          if (c === '"' && next === '"') {
            cell += '"';
            i++;
          } else if (c === '"') {
            quoted = false;
          } else {
            cell += c;
          }
        } else if (c === '"') {
          quoted = true;
        } else if (c === ",") {
          row.push(cell);
          cell = "";
        } else if (c === "\n") {
          row.push(cell);
          rows.push(row);
          row = [];
          cell = "";
        } else if (c !== "\r") {
          cell += c;
        }
      }
      if (cell || row.length) {
        row.push(cell);
        rows.push(row);
      }
      if (!rows.length) return [];
      rows[0][0] = String(rows[0][0] || "").replace(/^\uFEFF/, "");
      const header = rows.shift().map(value => String(value || "").trim());
      return rows
        .filter(values => values.some(value => String(value || "").trim()))
        .map(values => {
          const item = {};
          header.forEach((column, index) => item[column] = String(values[index] || "").trim());
          orderColumns.forEach(column => {
            if (!(column in item)) item[column] = "";
          });
          if (!item.status) item.status = "NEW";
          if (!item.service_type) item.service_type = "3";
          return item;
        });
    }

    async function importOrdersFile() {
      const file = $("ordersFile").files[0];
      if (!file) return;
      const text = await file.text();
      state.view = "orders";
      document.querySelectorAll(".tab").forEach(tab => tab.classList.toggle("active", tab.dataset.view === "orders"));
      renderOrders(parseCsv(text));
      setStatus("Orders CSV imported.");
    }

    async function validateOrders() {
      if (!state.orders.length) {
        setStatus("Import orders CSV first.", "warn");
        return;
      }
      setBusy(true);
      setStatus("Validating orders with B2 Cloud...");
      try {
        const data = await api("/api/orders/validate", {
          method: "POST",
          body: JSON.stringify({ rows: state.orders })
        });
        renderOrders(data.rows || []);
        setStatus("Orders validated.");
      } catch (err) {
        setStatus(err.message, "error");
      } finally {
        setBusy(false);
      }
    }

    async function createOrders() {
      if (!state.orders.length) {
        setStatus("Import orders CSV first.", "warn");
        return;
      }
      const ready = state.orders.filter(row => row.status === "READY" && !row.tracking_number).length;
      if (!ready) {
        setStatus("No READY rows without tracking number.", "warn");
        return;
      }
      if (!confirm(`Create shipments for ${ready} READY row(s)? This calls B2 Cloud.`)) {
        return;
      }
      setBusy(true);
      setStatus("Creating shipments...");
      try {
        const data = await api("/api/orders/create", {
          method: "POST",
          body: JSON.stringify({ rows: state.orders, issue_pdf: $("issuePdf").checked })
        });
        renderOrders(data.rows || []);
        setStatus("Shipment creation finished.");
      } catch (err) {
        setStatus(err.message, "error");
      } finally {
        setBusy(false);
      }
    }

    function exportOrdersCsv() {
      const lines = [orderColumns.join(",")].concat(state.orders.map(row =>
        orderColumns.map(key => '"' + String(row[key] ?? "").replace(/"/g, '""') + '"').join(",")
      ));
      const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "orders_checked.csv";
      a.click();
      URL.revokeObjectURL(url);
    }

    async function logout() {
      await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
      setLoggedOut();
      render([]);
      setStatus("Logged out.");
    }

    async function checkSession() {
      try {
        const data = await api("/api/session");
        if (data.logged_in) {
          $("loginState").textContent = "Connected";
          $("logoutBtn").classList.remove("hidden");
        } else {
          setLoggedOut();
        }
      } catch {
        setLoggedOut();
      }
    }

    function init() {
      $("serviceType").innerHTML = Object.entries(serviceTypes)
        .map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`)
        .join("");
      $("serviceType").value = "3";
      $("loginBtn").addEventListener("click", login);
      $("loadBtn").addEventListener("click", loadData);
      $("trackingBtn").addEventListener("click", updateTracking);
      $("exportBtn").addEventListener("click", exportCsv);
      $("ordersFile").addEventListener("change", importOrdersFile);
      $("validateOrdersBtn").addEventListener("click", validateOrders);
      $("createOrdersBtn").addEventListener("click", createOrders);
      $("exportOrdersBtn").addEventListener("click", exportOrdersCsv);
      $("logoutBtn").addEventListener("click", logout);
      document.querySelectorAll(".tab").forEach(btn => {
        btn.addEventListener("click", () => {
          document.querySelectorAll(".tab").forEach(tab => tab.classList.remove("active"));
          btn.classList.add("active");
          state.view = btn.dataset.view;
          if (state.view === "orders") {
            renderOrders(state.orders);
          } else {
            loadData();
          }
        });
      });
      checkSession();
    }
    init();
  </script>
</body>
</html>
"""


def json_response(handler, status, payload, headers=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    if headers:
        for key, value in headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")


def feed_entries(feed):
    entries = feed.get("feed", {}).get("entry", [])
    if isinstance(entries, dict):
        return [entries]
    return entries or []


def get_sid(handler):
    cookie = SimpleCookie(handler.headers.get("Cookie"))
    morsel = cookie.get("b2sid")
    return morsel.value if morsel else ""


def get_session(handler):
    sid = get_sid(handler)
    session = SESSIONS.get(sid)
    if not session and len(SESSIONS) == 1:
        return next(iter(SESSIONS.values()))
    if not session and LAST_SESSION_ID:
        session = SESSIONS.get(LAST_SESSION_ID)
    if not session:
        raise RuntimeError("Not logged in.")
    return session


def history_params(query):
    params = {}
    service_type = query.get("service_type", [""])[0].strip()
    consignee_name = query.get("consignee_name", [""])[0].strip()
    tracking_number = query.get("tracking_number", [""])[0].strip()
    if service_type:
        params["service_type"] = service_type
    if consignee_name:
        params["consignee_name"] = consignee_name
    if tracking_number:
        params["tracking_number"] = tracking_number
    return params


def load_entries(session, query):
    view = query.get("view", ["history"])[0]
    params = history_params(query)
    if view == "new":
        feed = b2cloud.get_new(session, params=params or None)
    elif view == "deleted":
        feed = b2cloud.get_history_deleted(session)
    else:
        feed = b2cloud.search_history(session, **params)
    return feed_entries(feed), feed


def normalize_order_row(row):
    normalized = {column: str(row.get(column, "") or "").strip() for column in OUTPUT_COLUMNS}
    if not normalized["status"]:
        normalized["status"] = "NEW"
    if not normalized["service_type"]:
        normalized["service_type"] = "3"
    return normalized


def set_order_error(row, message):
    row["status"] = "INVALID"
    row["error_message"] = message
    return row


def validate_order_rows(session, rows):
    output = []
    for item in rows:
        row = normalize_order_row(item)
        if row.get("tracking_number"):
            row["status"] = "CREATED"
            row["error_message"] = ""
            output.append(row)
            continue

        errors = validate_local(row)
        if errors:
            output.append(set_order_error(row, "; ".join(errors)))
            continue

        shipment = create_shipment(row)
        result = b2cloud.check_shipment(session, shipment)
        if result["success"]:
            row["status"] = "READY"
            row["error_message"] = ""
        else:
            row["status"] = "INVALID"
            row["error_message"] = "; ".join(str(error) for error in result["errors"])
        output.append(row)
    return output


def extract_tracking(feed):
    for entry in feed_entries(feed):
        tracking = entry.get("shipment", {}).get("tracking_number", "")
        if tracking:
            return tracking
    return ""


def find_issued_tracking(session, row):
    order_id = row.get("order_id", "")
    if order_id:
        feed = b2cloud.search_history(session, shipment_number=order_id)
        tracking = extract_tracking(feed)
        if tracking:
            return tracking
    consignee_name = row.get("consignee_name", "")
    if consignee_name:
        feed = b2cloud.search_history(
            session,
            service_type=row.get("service_type") or None,
            consignee_name=consignee_name,
        )
        return extract_tracking(feed)
    return ""


def find_existing_shipment(session, row):
    order_id = row.get("order_id", "")
    if not order_id:
        return None, ""

    history = b2cloud.search_history(session, shipment_number=order_id)
    history_entries = feed_entries(history)
    if history_entries:
        tracking = history_entries[0].get("shipment", {}).get("tracking_number", "")
        return "CREATED", tracking

    saved = b2cloud.get_new(session, params={"shipment_number": order_id})
    saved_entries = feed_entries(saved)
    if saved_entries:
        tracking = saved_entries[0].get("shipment", {}).get("tracking_number", "")
        return "SAVED", tracking

    return None, ""


def create_order_shipments(session, rows, issue_pdf):
    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    output = []
    for item in rows:
        row = normalize_order_row(item)
        if row.get("tracking_number"):
            row["status"] = "CREATED"
            row["error_message"] = ""
            output.append(row)
            continue
        if row.get("status") not in {"READY", "NEW"}:
            output.append(row)
            continue

        errors = validate_local(row)
        if errors:
            output.append(set_order_error(row, "; ".join(errors)))
            continue

        try:
            existing_status, existing_tracking = find_existing_shipment(session, row)
            if existing_status:
                row["status"] = existing_status
                row["tracking_number"] = existing_tracking
                row["error_message"] = f"Skipped duplicate order_id already found in B2 Cloud: {row['order_id']}"
                output.append(row)
                continue

            shipment = create_shipment(row)
            checked = b2cloud.post_new_checkonly(session, [shipment])
            checked_errors = feed_entries(checked)[0].get("error", []) if feed_entries(checked) else []
            if checked_errors:
                row["status"] = "INVALID"
                row["error_message"] = "; ".join(str(error) for error in checked_errors)
                output.append(row)
                continue

            saved = b2cloud.post_new(session, checked)
            row["tracking_number"] = extract_tracking(saved)
            row["status"] = "SAVED"
            row["error_message"] = ""

            if issue_pdf:
                try:
                    pdf_data = b2cloud.print_issue(session, row.get("print_type") or row["service_type"], saved)
                    safe_order_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in row["order_id"])
                    pdf_path = LABEL_DIR / f"{safe_order_id or 'shipment'}.pdf"
                    pdf_path.write_bytes(pdf_data)
                    tracking = find_issued_tracking(session, row)
                    if tracking:
                        row["tracking_number"] = tracking
                    row["status"] = "CREATED"
                    row["error_message"] = f"PDF saved: {pdf_path}"
                except Exception as exc:
                    row["status"] = "SAVED"
                    row["error_message"] = f"Saved to B2 Cloud, but PDF issue failed: {exc}"
        except Exception as exc:
            row["status"] = "ERROR"
            row["error_message"] = str(exc)
        output.append(row)
    return output


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = INDEX_HTML.replace(
                "%SERVICE_TYPES%",
                json.dumps(SERVICE_TYPES, ensure_ascii=False),
            ).replace(
                "%ORDER_COLUMNS%",
                json.dumps(OUTPUT_COLUMNS, ensure_ascii=False),
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/entries":
            try:
                session = get_session(self)
                query = parse_qs(parsed.query)
                entries, _ = load_entries(session, query)
                json_response(self, HTTPStatus.OK, {"entries": entries})
            except Exception as exc:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if parsed.path == "/api/session":
            sid = get_sid(self)
            logged_in = bool(sid and sid in SESSIONS)
            headers = None
            if not logged_in:
                headers = {"Set-Cookie": "b2sid=; Max-Age=0; Path=/"}
            json_response(self, HTTPStatus.OK, {"logged_in": logged_in}, headers)
            return
        json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self):
        global LAST_SESSION_ID
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/login":
                data = read_json(self)
                customer_code = data.get("customer_code", "").strip()
                customer_password = data.get("customer_password", "").strip()
                if not customer_code or not customer_password:
                    raise RuntimeError("Customer code and password are required.")
                session = b2cloud.login(
                    customer_code,
                    customer_password,
                    data.get("customer_cls_code", "").strip(),
                    data.get("login_user_id", "").strip(),
                )
                sid = secrets.token_urlsafe(32)
                SESSIONS[sid] = session
                LAST_SESSION_ID = sid
                json_response(
                    self,
                    HTTPStatus.OK,
                    {"ok": True},
                    {"Set-Cookie": f"b2sid={sid}; HttpOnly; SameSite=Lax; Path=/"},
                )
                return
            if parsed.path == "/api/logout":
                sid = get_sid(self)
                if sid:
                    SESSIONS.pop(sid, None)
                if not SESSIONS:
                    LAST_SESSION_ID = ""
                json_response(
                    self,
                    HTTPStatus.OK,
                    {"ok": True},
                    {"Set-Cookie": "b2sid=; Max-Age=0; Path=/"},
                )
                return
            if parsed.path == "/api/tracking":
                session = get_session(self)
                data = read_json(self)
                query = {
                    key: [value]
                    for key, value in data.items()
                    if isinstance(value, str) and value.strip()
                }
                entries, feed = load_entries(session, query)
                if not entries:
                    json_response(self, HTTPStatus.OK, {"entries": []})
                    return
                updated = b2cloud.put_tracking(session, feed)
                json_response(self, HTTPStatus.OK, {"entries": feed_entries(updated)})
                return
            if parsed.path == "/api/orders/validate":
                session = get_session(self)
                data = read_json(self)
                rows = data.get("rows", [])
                if not isinstance(rows, list):
                    raise RuntimeError("rows must be a list.")
                json_response(self, HTTPStatus.OK, {"rows": validate_order_rows(session, rows)})
                return
            if parsed.path == "/api/orders/create":
                session = get_session(self)
                data = read_json(self)
                rows = data.get("rows", [])
                if not isinstance(rows, list):
                    raise RuntimeError("rows must be a list.")
                created = create_order_shipments(session, rows, bool(data.get("issue_pdf", True)))
                json_response(self, HTTPStatus.OK, {"rows": created})
                return
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except Exception as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})


def main():
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"B2 Cloud Dashboard: http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
