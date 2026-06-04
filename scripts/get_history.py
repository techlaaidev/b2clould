import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import b2cloud


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"Missing environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> None:
    customer_code = require_env("B2_CUSTOMER_CODE")
    customer_password = require_env("B2_CUSTOMER_PASSWORD")
    customer_cls_code = os.environ.get("B2_CUSTOMER_CLS_CODE", "").strip()
    login_user_id = os.environ.get("B2_LOGIN_USER_ID", "").strip()
    service_type = os.environ.get("B2_SERVICE_TYPE", "3").strip()

    session = b2cloud.login(
        customer_code,
        customer_password,
        customer_cls_code,
        login_user_id,
    )
    history = b2cloud.search_history(session, service_type=service_type)
    entries = history.get("feed", {}).get("entry", [])

    if not entries:
        print("No history entries found.")
        return

    for entry in entries:
        shipment = entry.get("shipment", {})
        print(
            shipment.get("tracking_number", ""),
            shipment.get("consignee_name", ""),
            shipment.get("shipment_date", ""),
            sep="\t",
        )


if __name__ == "__main__":
    main()
