# B2 Cloud Dashboard

Run the local dashboard:

```powershell
cd C:\Users\chipc\Desktop\b2cloud
pip install -r requirements.txt
python scripts\web_dashboard.py
```

Open this URL in your browser:

```text
http://127.0.0.1:8080
```

The dashboard supports:

- Login to Yamato B2 Cloud.
- View issued shipment history.
- View saved shipments before issue.
- View deleted history.
- Filter by service type, consignee name, and tracking number.
- Update tracking information for issued history.
- Export the current table to CSV.

Set another port if 8080 is busy:

```powershell
$env:B2_DASHBOARD_PORT="8090"
python scripts\web_dashboard.py
```
