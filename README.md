# AR PDF Export (ar_pdf_export)

Branded, letterhead-aware **PDF export for standard ERPNext reports** with a
column picker. Works on **Frappe / ERPNext v16** (bench).

Instead of replacing the standard report toolbar, the app adds its own
**"Branded PDF"** button to six accounting reports. The button opens a dialog
where you can choose which columns go into the PDF, then the server renders a
branded A4-landscape PDF containing:

- your company **Letter Head** (logo + header/footer content, images embedded
  as base64 - no network access needed by the PDF renderer),
- the report **title**,
- a **filters bar** (Company / From-To / As-on / Customer / Supplier / Party),
- the report **table** (only the columns you selected, headers always aligned
  with their data),
- a "Generated on <date>" footer.

All other reports are **unaffected** - their standard Print / PDF keeps
working exactly as before.

---

## Included reports (registry)

| Report name | ERPNext execute module |
|---|---|
| General Ledger | `erpnext.accounts.report.general_ledger.general_ledger.execute` |
| Accounts Receivable | `erpnext.accounts.report.accounts_receivable.accounts_receivable.execute` |
| Accounts Payable | `erpnext.accounts.report.accounts_payable.accounts_payable.execute` |
| Accounts Receivable Summary | `erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary.execute` |
| Accounts Payable Summary | `erpnext.accounts.report.accounts_payable_summary.accounts_payable_summary.execute` |
| Sales Register | `erpnext.accounts.report.sales_register.sales_register.execute` |

A report that is **not** in this registry is rejected by the endpoint
("PDF export is not configured for report: ...").

---

## Requirements

| Component | Version / notes |
|---|---|
| ERPNext | **v16.x** (tested on 16.28.0) |
| Frappe | v16.x (comes with ERPNext v16) |
| bench | v5.x (comes with your ERPNext v16 install) |
| Python | 3.11+ (the one used by your bench `env`) |
| PDF engine | whatever `frappe.utils.pdf.get_pdf` uses on your site (wkhtmltopdf / headless chromium / gotenberg) - already configured in ERPNext |
| OS | Ubuntu / Debian WSL, Linux, macOS (any bench host) |

No extra Python packages, no node modules and no custom doctypes are
required. The app is pure Python + one JavaScript asset.

---

## App structure

```
ar_pdf_export/
├── pyproject.toml                          # pip packaging (pip install -e)
└── ar_pdf_export/                          # the app package (bench apps/<app>)
    ├── __init__.py
    ├── hooks.py                            # app metadata + install hooks + app_include_js
    ├── install.py                          # after_install / after_migrate (cache clear)
    ├── modules.txt                         # declares the "AR PDF Export" module
    ├── patches.txt                         # (empty, reserved)
    ├── public/js/
    │   └── branded_button.js               # toolbar button + column picker dialog
    └── utils/
        ├── __init__.py
        ├── report_pdf.py                   # registry + whitelisted endpoint + letterhead embedding
        └── report_pdf.html                 # A4-landscape branded PDF template
```

---

## Installation

Run every command as the user that owns your bench (usually in a terminal
where `bench` works, e.g. inside the WSL/Linux bench host).

### 1. Get the app into your bench

Clone it directly into your bench `apps` folder (or copy the folder there):

```bash
cd ~/frappe-bench
# option A - clone from GitHub
git clone https://github.com/ArslanMalyieck/ar_pdf_export.git apps/ar_pdf_export

# option B - copy a local folder
# cp -r /path/to/ar_pdf_export ~/frappe-bench/apps/ar_pdf_export
```

### 2. Register the app with bench (MANDATORY)

A manually copied app (or a clone) is only importable if bench knows about it.
The bench-wide app list lives in **`sites/apps.txt`** (one app name per line).
Make sure `ar_pdf_export` is present:

```bash
cd ~/frappe-bench
grep -q "^ar_pdf_export$" sites/apps.txt || echo "ar_pdf_export" >> sites/apps.txt
cat sites/apps.txt          # verify - one app name per line, no merged lines!
```

> **Important:** `sites/apps.txt` must have exactly one app per line. If the
> last line of the file has no trailing newline, `echo >>` will merge two app
> names into one line and every bench command will fail with
> `ModuleNotFoundError: No module named '<previousapp><ar_pdf_export>'`.
> If that happens, open the file and split the merged line.

### 3. Install the Python package (recommended)

```bash
cd ~/frappe-bench
./env/bin/pip install -e apps/ar_pdf_export
```

This registers `ar-pdf-export` in the bench virtualenv. If you skip it, the
app may still run in development, but running commands through `env/bin/python`
(console scripts, tests, some bench tasks) can fail with `ModuleNotFoundError`.

### 4. Install the app on your site

```bash
cd ~/frappe-bench
bench --site erpnext.localhost install-app ar_pdf_export
# replace erpnext.localhost with your site name
```

`install-app` runs the migration/sync, creates the **"AR PDF Export"** Module
Def (from `modules.txt`) and executes `after_install`. On the next
`bench migrate` the same setup runs again (safe, it only clears the cache).

### 5. Make sure the JS asset is served

The button script is loaded from `/assets/ar_pdf_export/js/branded_button.js`.

- **Development mode** (`bench start`): the app's `public/` folder is served
  directly. If you get 404 for the asset URL, create the symlink once:

```bash
cd ~/frappe-bench
# remove first if it already exists and points somewhere else
rm -f sites/assets/ar_pdf_export
ln -s ../../apps/ar_pdf_export/ar_pdf_export/public sites/assets/ar_pdf_export
```

- **Production mode** (nginx / supervisor): build the asset bundle so it is
  copied into `sites/assets`:

```bash
cd ~/frappe-bench
bench build --app ar_pdf_export     # or: bench build
```

### 6. Restart and verify

```bash
cd ~/frappe-bench
# stop any running bench first, then start it again
pkill -f "frappe serve"; pkill -f "frappe schedule"; pkill -f "frappe worker"; pkill -f socketio
bench start        # development
# OR in production:
# bench restart --web   (supervisor: sudo supervisorctl restart all)
```

Then check with a browser (or curl):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/          # expect 200
curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/assets/ar_pdf_export/js/branded_button.js         # expect 200
```

> **Browser tip:** after installing/updating the app, hard-refresh once
> (**Ctrl+Shift+R**) so the new JS is loaded.

---

## Setup on the ERPNext side

The letterhead comes from the **Company** document:

1. Go to **Letter Head** and create/edit one (e.g. "BOT Solutions Letterhead")
   with your logo/header content.
2. Open your **Company** and set **Default Letter Head** to it.

The PDF template pulls the letterhead of the company passed in the report
filters (fallback: the user's default company). Images inside the letterhead
are embedded as base64, so broken/missing files become an empty logo instead
of breaking the PDF.

---

## Usage

1. Open one of the six reports, e.g. **Accounts Receivable Summary**.
2. Set the filters and click **Run** (the report must be executed at least
   once - the column list is read from the executed report).
3. Click **"Branded PDF"** in the toolbar.
4. In the dialog, tick/untick the columns you want (Select All / Clear
   available). At least one column must stay selected.
5. Click **Download PDF** - the branded PDF opens/downloads.

### Column selection details

- All columns ticked (default) → full PDF, exactly like before.
- Some columns unticked → the server receives `only_fields` and renders only
  the selected columns.
- Headers and data always stay aligned: rows are formatted against the full
  column list first, and `only_fields` removes the **same index positions**
  from the header list and every row (dict rows are looked up by fieldname).
  There is no positional drift, no matter which columns you pick.

---

## API

The endpoint is whitelisted and requires an authenticated session (normal
desk login). It is a GET endpoint, which is why the button uses `window.open`.

```
GET /api/method/ar_pdf_export.utils.report_pdf.download_report_pdf
    ?report_name=<Report Name>
    &filters=<JSON object>          # optional, e.g. {"company": "BOT Solutions", "from_date": "2026-01-01", ...}
    &only_fields=<JSON array>       # optional, e.g. ["party", "invoiced", "outstanding"]
    &orientation=Landscape          # optional, default Landscape
```

Returns the PDF as a file download.

```bash
# example with curl (use a logged-in cookie jar)
curl -b cookies.txt \
  "http://localhost:8000/api/method/ar_pdf_export.utils.report_pdf.download_report_pdf?report_name=Accounts%20Receivable%20Summary&filters=%7B%22company%22%3A%22BOT%20Solutions%22%7D" \
  -o report.pdf
```

---

## Adding another report

Two places must be edited (both are MANDATORY, otherwise the report gets no
button or the endpoint rejects it):

1. **`ar_pdf_export/utils/report_pdf.py`** - add a registry entry:

```python
REPORT_EXECUTE_PATHS = {
    ...
    "Trial Balance": "erpnext.accounts.report.trial_balance.trial_balance.execute",
}
```

2. **`ar_pdf_export/public/js/branded_button.js`** - add the name to
   `BRANDED_REPORTS` (appears twice: inside the function and in the list
   used at runtime):

```js
var BRANDED_REPORTS = [
    ...
    "Trial Balance",
];
```

3. Restart bench (JS asset) and hard-refresh the browser.

The button is attached through a wrapper around
`frappe.views.QueryReport.prototype.refresh_report`, which is why report
settings are already registered when the button is added, and why reports
without their own `onload` (e.g. General Ledger, Sales Register) still get
the button. Existing `onload` handlers are always chained and preserved.

---

## Notes & internals

- **Frappe v16 has no Client Script "Report" view** - that is why the button
  is not a Client Script but a global JS file registered via
  `app_include_js` in `hooks.py`.
- `report_pdf.py` normalizes both dict and `"Label:Fieldtype:Width"` string
  columns and tolerates script reports that return extra values after
  `(columns, data)`.
- Currency cells are formatted with thousands separators, date cells with the
  site date format.
- Only the six registry reports can be exported - everything else is blocked
  with a clear error.
- Standard report Print / PDF behaviour is never touched.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Button does not appear after install | Hard refresh (**Ctrl+Shift+R**); confirm the asset URL returns 200 (step 5-6); check the browser console for errors from `branded_button.js`. |
| `ModuleNotFoundError: No module named 'xxxar_pdf_export'` | `sites/apps.txt` has two app names merged on one line - fix the file (step 2). |
| `PDF export is not configured for report: X` | X is not in `REPORT_EXECUTE_PATHS` - add it (section "Adding another report"). |
| Every logged-in desk page returns 500 `SessionBootFailed` | The app is missing its metadata hooks - this repo's `hooks.py` already contains `app_title` etc.; if you trimmed `hooks.py`, restore them. |
| `TypeError` / `ValueError` while exporting | Make sure the report has data and you run the report in the UI first so columns exist. |
| PDF has no letterhead | Company's **Default Letter Head** is not set, or the Letter Head content is empty. |
| Asset 404 in production | Run `bench build --app ar_pdf_export` (step 5). |
| Server refuses connections after a WSL/VM reboot | Start the stack again: `sudo service mariadb start`, `sudo service redis-server start`, then `bench start` (or `bench restart` in production). |

---

## License

MIT - see `pyproject.toml`.

Author: ArslanMalyieck / BOT Solutions.
