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

	// Dynamic: the "Branded PDF" button is shown on EVERY query report. The
	// server-side endpoint runs any report generically (Script / Query /
	// Report Builder / Custom Report), so no per-report list is needed.

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

	function download_pdf(report_name, filters, only_fields, letter_head, words_column, words_mode) {
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

		if (letter_head) {
			url += "&letter_head=" + encodeURIComponent(letter_head);
		}

		if (words_column) {
			url += "&words_column=" + encodeURIComponent(words_column);
		}

		if (words_mode) {
			url += "&words_mode=" + encodeURIComponent(words_mode);
		}

		window.open(url);
	}

	function open_column_picker(report, report_name) {
		var columns = get_report_columns(report) || [];

		var dialog = new frappe.ui.Dialog({
			title: __("Select Columns - {0}", [report_name]),
			fields: [
				{
					fieldtype: "Link",
					fieldname: "letter_head",
					label: __("Letter Head (blank = Company default)"),
					options: "Letter Head",
				},
				{
					fieldtype: "Check",
					fieldname: "no_letter_head",
					label: __("No letter head"),
					default: 0,
				},
				{
					fieldtype: "Select",
					fieldname: "words_column",
					label: __("Amount in Words - column"),
					options: [__("Auto (last amount column)"), __("Off")].concat(
						columns.map(function (c) {
							return c.label;
						})
					),
					default: __("Auto (last amount column)"),
				},
				{
					fieldtype: "Select",
					fieldname: "words_mode",
					label: __("Amount in Words - basis"),
					options: [__("Last row value"), __("Total (sum)")],
					default: __("Last row value"),
				},
				{ fieldtype: "HTML", fieldname: "columns" },
			],
			primary_action_label: __("Download PDF"),
			primary_action: function (values) {
				var $wrapper = dialog.fields_dict.columns.$wrapper;
				var picked = $wrapper
					.find("input.col-pick:checked")
					.map(function () {
						return $(this).attr("data-fieldname");
					})
					.get();

				var only_fields = null;
				if (columns.length) {
					if (!picked.length) {
						frappe.msgprint(__("Kam se kam aik column select karein."));
						return;
					}
					if (picked.length < columns.length) {
						only_fields = picked;
					}
				}

				var lh = null;
				if (values.no_letter_head) {
					lh = "__none__";
				} else if (values.letter_head) {
					lh = values.letter_head;
				}

				var wc = values.words_column;
				if (wc === __("Off")) {
					wc = "__off__";
				} else if (wc === __("Auto (last amount column)")) {
					wc = "__auto__";
				}
				var wm = values.words_mode === __("Total (sum)") ? "sum" : "last";

				dialog.hide();
				download_pdf(report_name, get_filter_values(report), only_fields, lh, wc, wm);
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
		if (!report_name) return;
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

	function open_grid_download(report) {
		// Report Builder / List Report data lives only in the browser, so the
		// server can't re-run it. Send the current columns + rows instead.
		var cols = (report.columns || []).map(function (c) {
			var df = c.docfield || {};
			return {
				label: c.content || c.id,
				fieldname: c.id,
				fieldtype: df.fieldtype || "Data",
			};
		});
		var rows = (report.data || []).map(function (r) {
			var o = {};
			cols.forEach(function (c) {
				var v = r[c.fieldname];
				if (v && typeof v === "object" && v.value !== undefined) v = v.value;
				o[c.fieldname] = v;
			});
			return o;
		});
		var filters = {};
		try {
			filters = report.get_filters ? report.get_filters() : {};
		} catch (e) {
			filters = {};
		}
		var url =
			frappe.urllib.get_full_url(
				"/api/method/ar_pdf_export.utils.report_pdf.download_grid_pdf"
			) +
			"?title=" +
			encodeURIComponent(report.report_name || report.doctype || "Report") +
			"&columns=" +
			encodeURIComponent(JSON.stringify(cols)) +
			"&rows=" +
			encodeURIComponent(JSON.stringify(rows)) +
			"&filters=" +
			encodeURIComponent(JSON.stringify(filters || {}));
		window.open(url);
	}

	function add_report_view_button(report) {
		if (!report.page || !report.page.add_inner_button) return;
		if (report.page.inner_toolbar && report.page.inner_toolbar.find(".branded-pdf-btn").length) {
			return;
		}
		var btn = report.page.add_inner_button(__("Branded PDF"), function () {
			open_grid_download(report);
		});
		if (btn && btn.addClass) btn.addClass("branded-pdf-btn");
	}

	function patch_report_view() {
		var klass = frappe.views && frappe.views.ReportView;
		if (!klass || !klass.prototype) return false;
		if (klass.prototype.__branded_pdf_patched) return true;

		var orig_setup = klass.prototype.setup_result_area;
		if (typeof orig_setup === "function") {
			klass.prototype.setup_result_area = function () {
				var r = orig_setup.apply(this, arguments);
				try {
					add_report_view_button(this);
				} catch (e) {}
				return r;
			};
		}
		var orig_after = klass.prototype.after_render;
		if (typeof orig_after === "function") {
			klass.prototype.after_render = function () {
				var r = orig_after.apply(this, arguments);
				try {
					add_report_view_button(this);
				} catch (e) {}
				return r;
			};
		}
		klass.prototype.__branded_pdf_patched = true;
		return true;
	}

	(function init() {
		// The report views are defined in the desk bundle; retry until both
		// classes are available (app_include_js may run before they attach).
		var ok = patch_prototype();
		ok = patch_report_view() && ok;
		if (!ok) {
			setTimeout(init, 300);
		}
	})();
})();
