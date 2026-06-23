"""Probe B2 cloud for registered master data (sender / billing).

Logs in with B2 credentials from the environment and GETs a list of candidate
master endpoints, reporting which ones return data. Read-only; nothing is saved.

    B2_CUSTOMER_CODE=... B2_CUSTOMER_PASSWORD=... python scripts/probe_b2_master.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.orders_csv import login_from_env

BASE = "https://newb2web.kuronekoyamato.co.jp"

# Candidate endpoints that may hold the registered sender (依頼主) / billing (請求先).
CANDIDATES = [
    "/b2/p/_shipper",
    "/b2/p/shipper",
    "/b2/p/_sender",
    "/b2/p/_consignor",
    "/b2/p/_consignee",
    "/b2/p/_item",
    "/b2/p/_user",
    "/b2/p/_customer",
    "/b2/p/_billing",
    "/b2/p/_invoice",
    "/b2/p/_master",
    "/b2/p/master",
    "/b2/d/_settings/shipper",
    "/b2/d/_settings/sender",
    "/b2/d/_settings/user",
    "/b2/d/_settings/account",
    "/b2/d/_settings/customer",
]

# Words that signal the response actually carries sender/billing data.
SIGNALS = ["shipper", "依頼主", "請求", "invoice_code", "sender", "zip_code", "telephone"]


def main():
    session = login_from_env()
    print("Logged in. Probing candidates...\n")
    for path in CANDIDATES:
        url = BASE + path
        try:
            res = session.get(url, timeout=20)
            text = res.text or ""
            hit = [w for w in SIGNALS if w.lower() in text.lower()]
            flag = "  <-- LOOK" if hit and res.status_code == 200 and len(text) > 50 else ""
            print(f"[{res.status_code}] {path}  len={len(text)} signals={hit}{flag}")
            if flag:
                print("    " + text[:500].replace("\n", " "))
        except Exception as exc:
            print(f"[ERR] {path}: {exc}")


if __name__ == "__main__":
    main()
