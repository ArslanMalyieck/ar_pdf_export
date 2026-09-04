// "Branded PDF" button for the selected accounting reports.
// Opens the server-side branded exporter (letterhead + filters included).
// The report's own onload is preserved (chained).
//
// Why a prototype patch: frappe.query_reports["Report"] is only registered
// when the report is opened for the first time (query_report.js
// get_report_settings), so a one-shot init() can never see it. Instead we
// wrap QueryReport.prototype.refresh_report, which runs on every open/refresh
// AFTER the settings object exists - at that point we chain into
// settings.onload, and the button is added at the correct moment (after
// page.clear_custom_actions() inside the report's own refresh flow).

(function () {
	"use strict";

	var BRANDED_REPORTS = [
		"General Ledger",
		"Accounts Receivable",
		"Accounts Payable",
		"Accounts Receivable Summary",
		"Accounts Payable Summary",
		"Sales Register",
	];

	function get_filter_values(report) {
		if (report.get_filter_values) return report.get_filter_values();
		if (report.get_values) return report.get_values();
		return {};
	}

	function get_report_columns(report) {
		// v16 QueryReport keeps the executed report columns on the instance
		// (this.columns) after a successful run.
		var columns = report.columns;
		if (!columns || !columns.length) return [];

		return columns.map(function (col) {
			var label = col.label || col.title || col.fieldname || String(col);
			var fieldname = col.fieldname;
			if (!fieldname) {
				// mirror the server-side fallback in report_pdf.py:
				// label -> lowercase, spaces/slashes -> underscore
				fieldname = String(label)
					.toLowerCase()
					.replace(/[\s/]+/g, "_");
			}
			return { label: label, fieldname: fieldname };
		});
	}

	function escape_html(value) {
		return String(value)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;");
	}

	function download_pdf(report_name, filters, only_fields) {
		var url =
			frappe.urllib.get_full_url(
				"/api/method/ar_pdf_export.utils.report_pdf.download_report_pdf"
			) +
			"?report_name=" +
			encodeURIComponent(report_name) +
			"&filters=" +
			encodeURIComponent(JSON.stringify(filters));

		if (only_fields && only_fields.length) {
			url += "&only_fields=" + encodeURIComponent(JSON.stringify(only_fields));
		}

		window.open(url);
	}

	function open_column_picker(report, report_name) {
		var columns = get_report_columns(report);

		if (!columns.length) {
			frappe.msgprint(
				__("Report pehle run karein (filters set kar ke) phir Branded PDF dobara click karein.")
			);
			return;
		}

		var dialog = new frappe.ui.Dialog({
			title: __("Select Columns - {0}", [report_name]),
			fields: [{ fieldtype: "HTML", fieldname: "columns" }],
			primary_action_label: __("Download PDF"),
			primary_action: function () {
				var $wrapper = dialog.fields_dict.columns.$wrapper;
				var picked = $wrapper
					.find("input.col-pick:checked")
					.map(function () {
						return $(this).attr("data-fieldname");
					})
					.get();

				if (!picked.length) {
					frappe.msgprint(__("Kam se kam aik column select karein."));
					return;
				}

				var only_fields = null;
				if (picked.length < columns.length) {
					only_fields = picked;
				}

				dialog.hide();
				download_pdf(report_name, get_filter_values(report), only_fields);
			},
		});

		var list_html =
			'<div class="row" style="margin-bottom:8px">' +
			'<div class="col-xs-12">' +
			'<button class="btn btn-xs btn-default select-all" type="button">' +
			__("Select All") +
			"</button> " +
			'<button class="btn btn-xs btn-default clear-all" type="button">' +
			__("Clear") +
			"</button>" +
			'<span class="text-muted" style="margin-left:8px;font-size:12px">' +
			columns.length +
			" " +
			__("columns") +
			"</span>" +
			"</div></div>" +
			'<div style="max-height:300px;overflow:auto;border:1px solid #d1d8dd;border-radius:4px;padding:8px 10px">';

		columns.forEach(function (col, index) {
			list_html +=
				'<div class="checkbox">' +
				'<label style="display:block">' +
				'<input type="checkbox" class="col-pick" data-fieldname="' +
				escape_html(col.fieldname) +
				'"' +
				(index < 10 ? ' data-index="' + index + '"' : "") +
				" checked> " +
				escape_html(col.label) +
				"</label></div>";
		});
		list_html += "</div>";

		dialog.fields_dict.columns
			.$wrapper.html(list_html)
			.find(".select-all")
			.on("click", function () {
				dialog.fields_dict.columns.$wrapper.find("input.col-pick").prop("checked", true);
			});
		dialog.fields_dict.columns.$wrapper
			.find(".clear-all")
			.on("click", function () {
				dialog.fields_dict.columns.$wrapper.find("input.col-pick").prop("checked", false);
			});

		dialog.show();
	}

	function add_button(report) {
		var report_name = report.report_name;
		if (BRANDED_REPORTS.indexOf(report_name) === -1) return;
		if (!report.page || !report.page.add_inner_button) return;

		report.page.add_inner_button(__("Branded PDF"), function () {
			open_column_picker(report, report_name);
		});
	}

	function chain_onload(settings) {
		if (settings.__branded_pdf_patched) return;
		settings.__branded_pdf_patched = true;

		var base_onload = settings.onload;
		settings.onload = function (report) {
			if (base_onload) base_onload(report);
			add_button(report);
		};
	}

	function patch_prototype() {
		var klass = frappe.views && frappe.views.QueryReport;
		if (!klass || !klass.prototype) return false;
		if (klass.prototype.__branded_pdf_patched) return true;

		var original_refresh = klass.prototype.refresh_report;
		if (typeof original_refresh !== "function") return false;

		klass.prototype.refresh_report = function (route_options) {
			// Some reports (e.g. General Ledger, Sales Register) never define
			// their own onload - still create one so the button gets added.
			if (this.report_settings) {
				chain_onload(this.report_settings);
			}
			return original_refresh.call(this, route_options);
		};
		klass.prototype.__branded_pdf_patched = true;
		return true;
	}

	(function init() {
		// The QueryReport class is defined in the desk bundle; retry until it
		// is available (app_include_js may run before the class is attached).
		if (!patch_prototype()) {
			setTimeout(init, 300);
		}
	})();
})();
