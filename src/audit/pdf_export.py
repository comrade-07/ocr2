"""Printable report presentation; ReportLab loads only when PDF export is requested."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

import pandas as pd

from src.audit.models import AuditReport, FACILITY_COLUMNS
from src.audit.report import report_description, reports_by_kpi, safe_link, summary_table

if TYPE_CHECKING:
    from reportlab.lib.styles import StyleSheet1
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import Flowable, LongTable, Paragraph, SimpleDocTemplate


def _styles() -> StyleSheet1:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="AuditCell",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="AuditHeader", parent=styles["AuditCell"], textColor=colors.white
        )
    )
    return styles


def _display_text(value: object) -> str:
    if pd.isna(value):
        return "Not available"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _whole_days(value: float) -> int | None:
    if pd.isna(value):
        return None
    return int(value)


def _mapped_label(value: str) -> str:
    if value == "":
        return "Unmapped"
    return value


def _footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
    canvas.setFont("Helvetica", 8)
    canvas.drawString(30, 18, "ESG · Allocation audit")
    canvas.drawRightString(810, 18, f"Page {document.page}")


class _PdfReportWriter:
    """Own the styles and flowable list for one export, avoiding global rendering state."""

    def __init__(self, report: AuditReport) -> None:
        self.report = report
        self.styles = _styles()
        self.story: list[Flowable] = []

    def _paragraph(self, value: object, style_name: str = "AuditCell") -> Paragraph:
        from reportlab.platypus import Paragraph

        text = escape(_display_text(value))
        return Paragraph(text, self.styles[style_name])

    def _source_reference(self, url: str) -> Paragraph:
        from reportlab.platypus import Paragraph

        if not safe_link(url):
            return self._paragraph("SharePoint link unavailable")
        escaped_url = escape(url, {'"': "&quot;"})
        markup = f'<link href="{escaped_url}" color="#205C93">Open evidence file</link>'
        return Paragraph(markup, self.styles["AuditCell"])

    def _table(
        self, headers: list[str], rows: list[list[object]], widths: list[int]
    ) -> LongTable:
        """Wrap text safely, preserve link paragraphs, and repeat headings across pages."""
        from reportlab.lib import colors
        from reportlab.platypus import LongTable, Paragraph, TableStyle

        header_cells = []
        for header in headers:
            header_cells.append(self._paragraph(header, "AuditHeader"))
        table_rows = [header_cells]
        for row in rows:
            cells = []
            for value in row:
                if isinstance(value, Paragraph):
                    cells.append(value)
                else:
                    cells.append(self._paragraph(value))
            table_rows.append(cells)
        table = LongTable(table_rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#205C93")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#D5DEE8")),
                ]
            )
        )
        return table

    def _add_introduction(self) -> None:
        from reportlab.platypus import Spacer

        self.story.append(self._paragraph("Audit and Report", "Title"))
        self.story.append(self._paragraph(report_description(self.report)))
        self.story.append(self._paragraph("Generated UTC: " + self.report.generated_at))
        self.story.append(Spacer(1, 12))
        self.story.append(
            self._paragraph(
                "Allocated kWh = billed kWh / invoice days × days in month. Invoice days count effective dates inclusively. Month-start periods exclude the end; month-end periods exclude the start. Other shared dates belong to the next invoice. Previous invoice pattern is rechecked when the next invoice arrives. Totals use full precision; displayed values use two decimals."
            )
        )
        self.story.append(
            self._paragraph(
                f"Checks needing review: {len(self.report.cases)}. Billed quantities repeat across months and must not be summed."
            )
        )
        self.story.append(Spacer(1, 12))
        for warning in self.report.warnings:
            self.story.append(self._paragraph("Input warning: " + warning))

    def _add_summary(self) -> None:
        summary = summary_table(self.report).drop(columns="KPI Component")
        rows = []
        for record in summary.itertuples(index=False, name=None):
            rows.append(list(record))
        self.story.append(self._paragraph("Facility summary", "Heading2"))
        self.story.append(
            self._table(
                list(summary.columns), rows, [95, 110, 120, 65, 45, 80, 75, 180]
            )
        )

    def _detail_rows(self, details: pd.DataFrame) -> list[list[object]]:
        rows = []
        for index, allocation in enumerate(details.itertuples(), start=1):
            period_labels = []
            for start, end in (
                (allocation.printed_start, allocation.printed_end),
                (allocation.start, allocation.end),
            ):
                if pd.isna(start) or pd.isna(end):
                    period_labels.append("Invalid dates")
                else:
                    period_labels.append(f"{start:%Y-%m-%d} to {end:%Y-%m-%d}")
            rows.append(
                [
                    index,
                    allocation.account,
                    allocation.month,
                    *period_labels,
                    allocation.date_adjustment,
                    allocation.date_resolution,
                    _whole_days(allocation.days),
                    allocation.billed_kwh,
                    _whole_days(allocation.month_days),
                    allocation.allocated_kwh,
                    self._source_reference(allocation.source_link),
                ]
            )
        return rows

    def _add_original_units(self, details: pd.DataFrame) -> None:
        converted_periods = details.drop_duplicates("period_id")
        if converted_periods.empty:
            return
        rows = []
        for period in converted_periods.itertuples():
            rows.append(
                [
                    period.period_id,
                    self._source_reference(period.source_link),
                    period.billed_original,
                    period.original_unit,
                    period.factor,
                    period.source,
                    period.supplier,
                ]
            )
        self.story.append(self._paragraph("Original billed quantities and invoice references", "Heading3"))
        headers = [
            "Invoice period reference",
            "Source",
            "Original billed quantity",
            "Original unit",
            "kWh conversion factor",
            "Data source",
            "Supplier",
        ]
        self.story.append(self._table(headers, rows, [140, 110, 115, 65, 85, 105, 150]))

    def _add_unit_details(self) -> None:
        """Walk units in hierarchy order and render each unit's detail table and total."""
        from reportlab.platypus import PageBreak, Spacer

        grouped_details = self.report.details.groupby(
            FACILITY_COLUMNS, sort=True, dropna=False
        )
        for hierarchy, details in grouped_details:
            division, legal_entity, unit_name = hierarchy
            self.story.append(PageBreak())
            self.story.append(
                self._paragraph("Division: " + _mapped_label(division), "Heading2")
            )
            self.story.append(
                self._paragraph(
                    "Legal entity: " + _mapped_label(legal_entity), "Heading3"
                )
            )
            self.story.append(
                self._paragraph("Unit name: " + _mapped_label(unit_name) + " | " + str(self.report.filters.kpi_component), "Heading3")
            )
            headers = [
                "Index",
                "Account",
                "Reporting month",
                "Invoice period",
                "Allocation period",
                "Date adjustment",
                "Reason",
                "Invoice days",
                "Billed kWh",
                "Days in month",
                "Allocated kWh",
                "Source",
            ]
            self.story.append(
                self._table(
                    headers,
                    self._detail_rows(details),
                    [35, 65, 48, 83, 83, 75, 93, 40, 65, 43, 65, 85],
                )
            )
            total_quantity = details.allocated_kwh.sum(min_count=1)
            if pd.notna(total_quantity):
                total_label = f"Unit total allocated kWh: {total_quantity:,.2f}"
            else:
                total_label = "Unit total unavailable"
            self.story.append(Spacer(1, 10))
            self.story.append(self._paragraph(total_label))
            self._add_original_units(details)

    def _add_case(self, case: pd.Series) -> None:
        from reportlab.platypus import Spacer

        self.story.append(self._paragraph(f"{case.case_id} · {case.issue}", "Heading3"))
        self.story.append(self._paragraph("Division: " + _mapped_label(case.division)))
        self.story.append(
            self._paragraph("Legal entity: " + _mapped_label(case.legal_entity))
        )
        self.story.append(
            self._paragraph("Unit name: " + _mapped_label(case.unit_name))
        )
        self.story.append(
            self._paragraph(f"Account: {case.account} | Reporting month: {case.month}")
        )
        self.story.append(self._paragraph(case.explanation))
        self.story.append(self._paragraph("Next step: " + case.next_step))
        if len(case.source_links) == 0:
            self.story.append(self._source_reference(""))
        else:
            for source_link in case.source_links:
                self.story.append(self._source_reference(source_link))
        self.story.append(
            self._paragraph("Invoice period references: " + ", ".join(case.period_ids))
        )
        self.story.append(Spacer(1, 10))

    def _add_cases(self) -> None:
        from reportlab.platypus import PageBreak

        self.story.append(PageBreak())
        self.story.append(self._paragraph("Checks and exceptions", "Heading2"))
        self.story.append(
            self._paragraph(
                "Coverage checks apply to accounts present in the inputs. Confirm account activity before treating missing coverage as an error."
            )
        )
        if self.report.cases.empty:
            self.story.append(
                self._paragraph(
                    "No exceptions detected for this selection. This does not certify that every invoice has been supplied."
                )
            )
            return
        for case_index, case in self.report.cases.iterrows():
            self._add_case(case)

    def _add_sources(self) -> None:
        from reportlab.platypus import PageBreak, Spacer

        self.story.append(PageBreak())
        self.story.append(self._paragraph("Report inputs", "Heading2"))
        for source in self.report.sources:
            self.story.append(self._paragraph(source["File"], "Heading3"))
            self.story.append(
                self._paragraph("Modified UTC: " + source["Modified (UTC)"])
            )
            self.story.append(self._paragraph("SHA256: " + source["SHA256"]))
            self.story.append(Spacer(1, 8))

    def render(self, include: str) -> bytes:
        """Assemble requested sections, then let ReportLab paginate and serialize them."""
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate

        self._add_introduction()
        original_report = self.report
        for component, scoped in reports_by_kpi(original_report):
            self.report = scoped
            self.story.append(self._paragraph(component, "Heading1"))
            self._add_summary()
            if include in {"Full report", "Summary and details"}:
                self._add_unit_details()
            if include == "Full report":
                self._add_cases()
        self.report = original_report
        self._add_sources()
        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            title=f"Scope 2 Audit Report — {self.report.filters.year}",
            pagesize=landscape(A4),
            rightMargin=30,
            leftMargin=30,
            topMargin=35,
            bottomMargin=35,
        )
        document.build(self.story, onFirstPage=_footer, onLaterPages=_footer)
        return output.getvalue()


def pdf_bytes(report: AuditReport, include: str = "Full report") -> bytes:
    writer = _PdfReportWriter(report)
    return writer.render(include)
