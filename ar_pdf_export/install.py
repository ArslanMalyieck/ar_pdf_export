import frappe

# Branded PDF button setup.
#
# Original app design: one "Download PDF" button per report configured in
# REPORT_EXECUTE_PATHS. Frappe v16 has no Client Script "Report" view, so
# the buttons are attached by branded_button.js (app_include_js) which
# chains into each report's own onload - same behaviour, v16-compatible.


def after_install():
	frappe.clear_cache()
