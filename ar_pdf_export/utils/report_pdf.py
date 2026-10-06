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
def _render_letter_head_html(company, raw_html):
    if not raw_html:
        return ""
    try:
        raw_html = frappe.utils.jinja.render_template(
            raw_html,
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

    return re.sub(r'src\s*=\s*["\']([^"\']+)["\']', embed_image, raw_html)


def get_letter_head_parts(company, letter_head_name=None):
    """Return (header_html, footer_html) for the chosen Letter Head.

    The header is placed at the TOP of the PDF. The footer is placed at the
    END of the document so that, on a multi-page report, it lands on the
    LAST page. Both have their images inlined as base64 so wkhtmltopdf needs
    no network access.
    """
    if not letter_head_name:
        letter_head_name = frappe.db.get_value("Company", company, "default_letter_head")
    if not letter_head_name:
        return "", ""
    try:
        letter_head = frappe.get_doc("Letter Head", letter_head_name)
    except frappe.DoesNotExistError:
        return "", ""
    header_html = _render_letter_head_html(company, letter_head.get("content") or "")
    footer_html = _render_letter_head_html(company, letter_head.get("footer") or "")
    return header_html, footer_html


def get_letter_head_html(company, letter_head_name=None):
    # Backward-compatible wrapper: header only.
    return get_letter_head_parts(company, letter_head_name)[0]


# ---------------------------------------------------------------------------
# Generic report runner (works for ANY report)
# ---------------------------------------------------------------------------
def run_report_for_pdf(report_name, filters):
    """Run ANY report generically so no per-report configuration is needed.

    Uses Frappe's own report runner (frappe.desk.query_report.run), which
    handles Script Reports, Query Reports, Report Builder reports and
    Custom Reports (including their own custom columns/filters). An explicit
    execute path in REPORT_EXECUTE_PATHS is kept only as a fallback for
    backwards compatibility.
    """
    try:
        from frappe.desk.query_report import run as run_report

        res = run_report(report_name, filters=dict(filters or {}), ignore_prepared_report=1)
        return res.get("columns") or [], res.get("result") or []
    except Exception:
        execute_path = REPORT_EXECUTE_PATHS.get(report_name)
        if not execute_path:
            raise
        result = frappe.get_attr(execute_path)(filters)
        if isinstance(result, (tuple, list)) and len(result) >= 2:
            return result[0], result[1]
        return result or [], []


# ---------------------------------------------------------------------------
# Amount in words (English + Arabic)
# ---------------------------------------------------------------------------
def _resolve_amount_column(columns, key):
    for idx, col in enumerate(columns):
        if col.get("fieldname") == key or col.get("label") == key:
            return idx
    return None


def _pick_auto_column(columns, data=None):
    """Best-guess amount column: prefer a Currency/Float column whose name
    looks like a balance/total; else the last Currency/Float column; else the
    last column that actually holds numeric values."""
    priority = (
        "balance", "closing", "outstanding", "grand_total", "net_total",
        "rounded_total", "amount", "total", "debit", "credit",
    )
    amount_cols = [
        i for i, c in enumerate(columns) if c.get("fieldtype") in ("Currency", "Float")
    ]
    if amount_cols:
        for key in priority:
            matches = [
                i for i in amount_cols
                if key
                in (
                    (columns[i].get("fieldname") or "")
                    + " "
                    + (columns[i].get("label") or "")
                ).lower()
            ]
            if matches:
                return matches[-1]  # right-most match (totals are usually on the right)
        return amount_cols[-1]

    # No declared amount column - fall back to the last column with numbers.
    def _numeric(v):
        if isinstance(v, (int, float)):
            return True
        if isinstance(v, str):
            t = v.strip().replace(",", "")
            return bool(t) and (t.replace(".", "", 1).replace("-", "", 1).isdigit())
        return False

    for i in range(len(columns) - 1, -1, -1):
        fn = columns[i].get("fieldname")
        for row in data or []:
            v = row.get(fn) if isinstance(row, dict) else (row[i] if i < len(row) else None)
            if _numeric(v):
                return i
    return None


def compute_words_amount(columns, data, words_column, words_mode):
    """Return the amount to render in words: the last value of the chosen
    column, or its total, depending on words_mode."""
    if not words_column or words_column == "__off__":
        return None
    if words_column == "__auto__":
        idx = _pick_auto_column(columns, data)
        if idx is None:
            return None
    else:
        idx = _resolve_amount_column(columns, words_column)
        if idx is None:
            return None
    fieldname = columns[idx]["fieldname"]
    nums = []
    for row in data:
        if isinstance(row, dict):
            nums.append(flt(row.get(fieldname)))
        else:
            nums.append(flt(row[idx]) if idx < len(row) else 0)
    if not nums:
        # Empty report (no rows) - still show a words line so it appears on
        # EVERY report, defaulting to zero.
        return 0.0
    if str(words_mode or "").lower().startswith(("sum", "total")):
        return round(sum(nums), 2)
    # "last" = last NON-ZERO value (skips trailing zero / grand-total rows)
    for v in reversed(nums):
        if v:
            return round(v, 2)
    return round(nums[-1], 2)


def amount_in_words(amount, company=None):
    """English (via Frappe, uses the company currency's fraction name) and
    Arabic (via num2words) words for the amount."""
    from num2words import num2words

    currency = frappe.db.get_value("Company", company, "default_currency") if company else None
    try:
        en = (
            frappe.utils.money_in_words(amount, main_currency=currency)
            if currency
            else frappe.utils.money_in_words(amount)
        )
    except Exception:
        try:
            en = num2words(amount, to="currency", lang="en")
        except Exception:
            en = str(amount)
    try:
        ar = num2words(amount, to="currency", lang="ar")
    except Exception:
        ar = ""
    return en, ar


# ---------------------------------------------------------------------------
# Shared PDF builder + whitelisted endpoints
# ---------------------------------------------------------------------------
def _build_report_pdf(
    columns,
    data,
    title,
    filters,
    letter_head,
    words_column,
    words_mode,
    orientation,
    only_fields=None,
    filename=None,
):
    columns = normalize_columns(columns)

    # Amount in words is ON by default (the common case for a branded report);
    # the dialog sends "__off__" to disable it. Defaulting here also makes it
    # work even with an older cached client script that never sends the param.
    if not words_column:
        words_column = "__auto__"

    amount_words_en = amount_words_ar = ""
    _amount = compute_words_amount(columns, data, words_column, words_mode)
    if _amount is not None:
        company = filters.get("company") or frappe.defaults.get_user_default("Company")
        amount_words_en, amount_words_ar = amount_in_words(_amount, company)

    if isinstance(only_fields, str):
        only_fields = json.loads(only_fields) if only_fields else None

    # Rows are ALWAYS formatted against the FULL column list so that every
    # cell stays locked to its own column (dict lookup by fieldname for dict
    # rows, positional index for array rows). only_fields is applied AFTER
    # formatting by slicing the same index positions out of both the column
    # list and every row - header/data alignment can never drift.
    all_fieldnames = [c["fieldname"] for c in columns]

    formatted_rows = []
    for row in data or []:
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

    if letter_head == "__none__":
        letter_head_html, letter_head_footer_html = "", ""
    else:
        company = filters.get("company") or frappe.defaults.get_user_default("Company")
        letter_head_html, letter_head_footer_html = get_letter_head_parts(company, letter_head)

    html = frappe.render_template(
        "ar_pdf_export/utils/report_pdf.html",
        {
            "title": title,
            "columns": columns,
            "rows": formatted_rows,
            "letter_head_html": letter_head_html,
            "letter_head_footer_html": letter_head_footer_html,
            "amount_words_en": amount_words_en,
            "amount_words_ar": amount_words_ar,
            "filters": filters,
            "today": formatdate(frappe.utils.nowdate()),
        },
    )

    pdf = get_pdf(html, {"orientation": orientation})
    frappe.local.response.filename = f"{(filename or title or 'Report').replace(' ', '-')}.pdf"
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "download"


@frappe.whitelist()
def download_report_pdf(
    report_name,
    filters=None,
    only_fields=None,
    orientation="Landscape",
    letter_head=None,
    words_column=None,
    words_mode=None,
):
    if isinstance(filters, str):
        filters = json.loads(filters) if filters else {}
    filters = frappe._dict(filters or {})

    columns, data = run_report_for_pdf(report_name, filters)
    _build_report_pdf(
        columns, data, report_name, filters, letter_head, words_column, words_mode,
        orientation, only_fields,
    )


@frappe.whitelist()
def download_grid_pdf(
    title=None,
    columns=None,
    rows=None,
    filters=None,
    orientation="Landscape",
    letter_head=None,
    words_column=None,
    words_mode=None,
):
    """For Report Builder / List Report (frappe.views.ReportView), where the
    data lives only in the browser - the client posts its own columns + rows.
    Renders the same branded PDF (letterhead + amount in words)."""
    if isinstance(columns, str):
        columns = json.loads(columns) if columns else []
    if isinstance(rows, str):
        rows = json.loads(rows) if rows else []
    if isinstance(filters, str):
        filters = json.loads(filters) if filters else {}
    filters = frappe._dict(filters or {})
    _build_report_pdf(
        columns or [], rows or [], title or "Report", filters, letter_head,
        words_column, words_mode, orientation,
    )
