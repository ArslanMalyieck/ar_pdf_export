import base64
import json
import mimetypes
import os
import re

import frappe
from frappe.utils import flt, formatdate
from frappe.utils.pdf import get_pdf

# ---------------------------------------------------------------------------
# Report registry - only reports listed here get the branded PDF button and
# endpoint (same design as the original app).
# ---------------------------------------------------------------------------
REPORT_EXECUTE_PATHS = {
    "General Ledger": "erpnext.accounts.report.general_ledger.general_ledger.execute",
    "Accounts Receivable": "erpnext.accounts.report.accounts_receivable.accounts_receivable.execute",
    "Accounts Payable": "erpnext.accounts.report.accounts_payable.accounts_payable.execute",
    "Accounts Receivable Summary": "erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary.execute",
    "Accounts Payable Summary": "erpnext.accounts.report.accounts_payable_summary.accounts_payable_summary.execute",
    "Sales Register": "erpnext.accounts.report.sales_register.sales_register.execute",
}

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def format_cell(value, fieldtype):
    if value in (None, ""):
        return ""
    if fieldtype == "Currency":
        return "{:,.2f}".format(flt(value))
    if fieldtype == "Date":
        return formatdate(value)
    if isinstance(value, list):
        return ", ".join([str(v) for v in value])
    return str(value)


def normalize_columns(columns):
    """Script reports sometimes return columns as plain strings like
    'Label:Fieldtype/Options:Width' instead of dicts. Normalize both
    shapes into a consistent list of dicts."""
    norm = []
    for col in columns or []:
        if isinstance(col, str):
            parts = col.split(":")
            label = parts[0]
            fieldname = label.lower().replace(" ", "_").replace("/", "_")
            fieldtype = parts[1].split("/")[0] if len(parts) > 1 else "Data"
            norm.append({"label": label, "fieldname": fieldname, "fieldtype": fieldtype})
        else:
            norm.append(dict(col))
    return norm


# ---------------------------------------------------------------------------
# Letterhead embedding (logo etc. inlined as base64 so wkhtmltopdf needs
# no network access and missing files don't break the PDF)
# ---------------------------------------------------------------------------
def get_letter_head_html(company):
    letter_head_name = frappe.db.get_value("Company", company, "default_letter_head")
    if not letter_head_name:
        return ""
    try:
        letter_head = frappe.get_doc("Letter Head", letter_head_name)
    except frappe.DoesNotExistError:
        return ""
    content = letter_head.content or ""
    try:
        content = frappe.utils.jinja.render_template(
            content,
            {"doc": frappe._dict({"company": company}), "company": company},
        )
    except Exception:
        pass

    def embed_image(match):
        src = match.group(1)
        if src.startswith("data:") or src.startswith("http"):
            return match.group(0)
        filename = src.split("/")[-1]
        file_path = None
        for base in ("public", "private"):
            candidate = frappe.get_site_path(base, "files", filename)
            if os.path.exists(candidate):
                file_path = candidate
                break
        if not file_path:
            try:
                file_doc = frappe.get_doc("File", {"file_url": src})
                file_path = file_doc.get_full_path()
            except frappe.DoesNotExistError:
                file_path = None
        if not file_path or not os.path.exists(file_path):
            return 'src=""'
        mime = mimetypes.guess_type(file_path)[0] or "image/png"
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f'src="data:{mime};base64,{b64}"'

    return re.sub(r'src\s*=\s*["\']([^"\']+)["\']', embed_image, content)


# ---------------------------------------------------------------------------
# Main whitelisted endpoint
# ---------------------------------------------------------------------------
@frappe.whitelist()
def download_report_pdf(report_name, filters=None, only_fields=None, orientation="Landscape"):
    if isinstance(filters, str):
        filters = json.loads(filters) if filters else {}
    filters = frappe._dict(filters or {})

    execute_path = REPORT_EXECUTE_PATHS.get(report_name)
    if not execute_path:
        frappe.throw(f"PDF export is not configured for report: {report_name}")

    execute_fn = frappe.get_attr(execute_path)
    result = execute_fn(filters)

    # script reports may return extra values after columns + data
    if isinstance(result, (tuple, list)) and len(result) >= 2:
        columns, data = result[0], result[1]
    else:
        columns, data = result, []
    columns = normalize_columns(columns)

    if isinstance(only_fields, str):
        only_fields = json.loads(only_fields) if only_fields else None

    # Rows are ALWAYS formatted against the FULL column list so that every
    # cell stays locked to its own column (dict lookup by fieldname for dict
    # rows, positional index for array rows). only_fields is applied AFTER
    # formatting by slicing the same index positions out of both the column
    # list and every row - header/data alignment can never drift.
    all_fieldnames = [c["fieldname"] for c in columns]

    formatted_rows = []
    for row in data:
        if isinstance(row, dict):
            cells = [
                format_cell(row.get(c["fieldname"]), c.get("fieldtype")) for c in columns
            ]
        else:
            cells = [
                format_cell(row[i] if i < len(row) else "", columns[i].get("fieldtype"))
                for i in range(len(columns))
            ]
        formatted_rows.append(cells)

    if only_fields:
        keep = [i for i, name in enumerate(all_fieldnames) if name in only_fields]
        if keep:
            columns = [columns[i] for i in keep]
            formatted_rows = [[row[i] for i in keep] for row in formatted_rows]

    company = filters.get("company") or frappe.defaults.get_user_default("Company")
    letter_head_html = get_letter_head_html(company)

    html = frappe.render_template(
        "ar_pdf_export/utils/report_pdf.html",
        {
            "title": report_name,
            "columns": columns,
            "rows": formatted_rows,
            "letter_head_html": letter_head_html,
            "filters": filters,
            "today": formatdate(frappe.utils.nowdate()),
        },
    )

    pdf = get_pdf(html, {"orientation": orientation})

    frappe.local.response.filename = f"{report_name.replace(' ', '-')}.pdf"
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "download"
