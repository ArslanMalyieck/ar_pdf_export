# ar_pdf_export
app_name = "ar_pdf_export"
app_title = "AR PDF Export"
app_publisher = "BOT Solutions"
app_description = "Branded PDF export for GL, Accounts Receivable / Payable, Receivable / Payable Summaries and Sales Register."
app_icon = "octicon octicon-file-pdf"
app_color = "grey"
app_email = "support@botsolutions.local"
app_license = "MIT"
app_version = "1.0.0"

# Runs once when the app is installed on a site.
after_install = "ar_pdf_export.install.after_install"

# Re-runs the same setup safely if you bench migrate
after_migrate = "ar_pdf_export.install.after_install"

# Global desk JS - adds the "Branded PDF" button on every query report
# (dynamic; the server endpoint runs any report). The ?v= query busts the
# browser cache on each deploy so the latest dialog options are loaded.
app_include_js = ["/assets/ar_pdf_export/js/branded_button.js?v=20261002d"]
