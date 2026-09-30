from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "pdf" / "snl_esg_ocr_file_path_guide.pdf"


def code_block(text: str, styles):
    return Preformatted(
        text.strip("\n"),
        ParagraphStyle(
            "CodeBlock",
            parent=styles["Code"],
            fontName="Courier",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1f2933"),
            backColor=colors.HexColor("#f5f7fa"),
            borderColor=colors.HexColor("#d8dee9"),
            borderWidth=0.6,
            borderPadding=8,
            spaceBefore=4,
            spaceAfter=8,
        ),
    )


def bullets(items, styles):
    return ListFlowable(
        [ListItem(Paragraph(item, styles["Body"]), leftIndent=10) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=18,
        bulletFontSize=7,
        spaceBefore=2,
        spaceAfter=7,
    )


def numbered(items, styles):
    return ListFlowable(
        [ListItem(Paragraph(item, styles["Body"]), leftIndent=13) for item in items],
        bulletType="1",
        leftIndent=20,
        spaceBefore=2,
        spaceAfter=7,
    )


def table(data, widths, styles):
    rows = []
    for row in data:
        rows.append([Paragraph(str(cell), styles["TableCell"]) for cell in row])
    result = Table(rows, colWidths=widths, hAlign="LEFT", repeatRows=1)
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243b53")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd2d9")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fbfcfe")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return result


def add_heading(story, text, styles):
    story.append(Paragraph(text, styles["H2"]))
    story.append(Spacer(1, 0.06 * inch))


def add_subheading(story, text, styles):
    story.append(Paragraph(text, styles["H3"]))
    story.append(Spacer(1, 0.03 * inch))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#52606d"))
    canvas.drawString(0.65 * inch, 0.42 * inch, "SNL ESG OCR - File Path Guide")
    canvas.drawRightString(7.85 * inch, 0.42 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "TitleCustom",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=27,
            textColor=colors.HexColor("#102a43"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "Subtitle",
            parent=styles["BodyText"],
            alignment=TA_CENTER,
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#52606d"),
            spaceAfter=18,
        )
    )
    styles.add(
        ParagraphStyle(
            "Body",
            parent=styles["BodyText"],
            fontSize=9.4,
            leading=13.2,
            textColor=colors.HexColor("#1f2933"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "H2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            textColor=colors.HexColor("#102a43"),
            spaceBefore=8,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            "H3",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor("#334e68"),
            spaceBefore=6,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            "TableCell",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#1f2933"),
        )
    )

    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.65 * inch,
        title="SNL ESG OCR File Path Guide",
        author="Codex",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])

    story = []
    story.append(Paragraph("SNL ESG OCR File Path Guide", styles["TitleCustom"]))
    story.append(
        Paragraph(
            "Detailed guide for changing input folders and output folders for the invoice OCR pipeline.",
            styles["Subtitle"],
        )
    )

    add_heading(story, "1. Quick Answer", styles)
    story.append(
        Paragraph(
            "Most file paths are controlled by one local configuration file: "
            "<b>config/settings.yaml</b>. Edit that file when you want permanent path changes. "
            "Use the command-line <b>--input</b> option only when you want to temporarily override "
            "the input folder for one run.",
            styles["Body"],
        )
    )
    story.append(
        table(
            [
                ["Need", "Where to change it"],
                ["Permanent input folder", "config/settings.yaml, under paths.raw_json_scope1/scope2/water/waste"],
                ["Permanent output folders", "config/settings.yaml, under paths.bronze_output, silver_excel_output, review_checkpoint_output, etc."],
                ["One-time input folder", "Run main.py with --input \"C:/path/to/json_folder\""],
                ["Review app data locations", "The review app reads the configured bronze, silver, checkpoint, and upload folders"],
            ],
            [1.7 * inch, 5.1 * inch],
            styles,
        )
    )

    add_heading(story, "2. The File To Edit", styles)
    story.append(Paragraph("Open this file in the project:", styles["Body"]))
    story.append(code_block(r"C:\Users\My PC\Desktop\snl-esg-ocr\config\settings.yaml", styles))
    story.append(
        Paragraph(
            "This file is intentionally local to your computer. The repository also contains "
            "<b>config/settings.example.yaml</b>, which is only the shared template. Use the example "
            "file as a reference, but edit <b>config/settings.yaml</b> for actual runs.",
            styles["Body"],
        )
    )

    add_subheading(story, "Current local settings", styles)
    story.append(
        code_block(
            """
app:
  name: invoice_platform
  environment: dev

paths:
  raw_json_scope1: "data/source/scope1"
  raw_json_scope2: "C:/Users/My PC/Desktop/raw_json"
  raw_json_water: "data/source/water"
  raw_json_waste: "data/source/waste"

  bronze_output: "data/bronze"
  silver_excel_output: "data/silver"
  review_checkpoint_output: "data/output/checkpoints"
  manual_data_entry_uploads: "data/manual_uploads"
  category_checkpoint_dirs: true
  gold_output: "data/gold"
            """,
            styles,
        )
    )

    add_heading(story, "3. Input Paths", styles)
    story.append(
        Paragraph(
            "Input paths tell the pipeline where the raw Azure Document Intelligence JSON files are stored. "
            "Each category has its own input setting. The selected category decides which input path is used.",
            styles["Body"],
        )
    )
    story.append(
        table(
            [
                ["Category", "Setting", "Used by command"],
                ["Scope 1", "raw_json_scope1", "main.py --category scope1"],
                ["Scope 2", "raw_json_scope2", "main.py --category scope2"],
                ["Water", "raw_json_water", "main.py --category water"],
                ["Waste", "raw_json_waste", "main.py --category waste"],
            ],
            [1.1 * inch, 2.2 * inch, 3.5 * inch],
            styles,
        )
    )
    story.append(
        Paragraph(
            "The input folder must contain .json files. The project does not copy these raw files into "
            "the bronze folder; it reads them from the configured source folder and records each source "
            "file path in the output.",
            styles["Body"],
        )
    )

    add_subheading(story, "Local folder example", styles)
    story.append(
        code_block(
            """
paths:
  raw_json_scope2: "data/source"
            """,
            styles,
        )
    )
    story.append(
        Paragraph(
            "With this setting, put Scope 2 JSON files here:",
            styles["Body"],
        )
    )
    story.append(code_block(r"C:\Users\My PC\Desktop\snl-esg-ocr\data\source", styles))

    add_subheading(story, "SharePoint or synced folder example", styles)
    story.append(
        code_block(
            """
paths:
  raw_json_scope2: "C:/Users/My PC/SharePoint/raw_json"
            """,
            styles,
        )
    )
    story.append(
        Paragraph(
            "Use forward slashes in YAML paths on Windows. They are easier to read and avoid escape-character problems.",
            styles["Body"],
        )
    )

    add_heading(story, "4. Output Paths", styles)
    story.append(
        Paragraph(
            "Output paths tell the pipeline where to create generated CSV files, Excel files, review checkpoint CSV files, "
            "manual upload files, and future gold-layer outputs.",
            styles["Body"],
        )
    )
    story.append(
        table(
            [
                ["Setting", "Purpose", "Current value"],
                ["bronze_output", "Bronze CSV output folder", "data/bronze"],
                ["silver_excel_output", "Final numbered Silver Excel workbook folder", "data/silver"],
                ["review_checkpoint_output", "Review checkpoint CSV folder", "data/output/checkpoints"],
                ["manual_data_entry_uploads", "Unsupported invoice files uploaded through the app", "data/manual_uploads"],
                ["gold_output", "Gold output folder reserved for later layers", "data/gold"],
            ],
            [1.75 * inch, 3.25 * inch, 1.8 * inch],
            styles,
        )
    )

    add_subheading(story, "Move all outputs to a Desktop folder", styles)
    story.append(
        code_block(
            """
paths:
  bronze_output: "C:/Users/My PC/Desktop/esg_outputs/bronze"
  silver_excel_output: "C:/Users/My PC/Desktop/esg_outputs/silver"
  review_checkpoint_output: "C:/Users/My PC/Desktop/esg_outputs/checkpoints"
  manual_data_entry_uploads: "C:/Users/My PC/Desktop/esg_outputs/manual_uploads"
  gold_output: "C:/Users/My PC/Desktop/esg_outputs/gold"
            """,
            styles,
        )
    )

    add_subheading(story, "Keep outputs inside the project", styles)
    story.append(
        code_block(
            """
paths:
  bronze_output: "data/bronze"
  silver_excel_output: "data/silver"
  review_checkpoint_output: "data/output/checkpoints"
  manual_data_entry_uploads: "data/manual_uploads"
  gold_output: "data/gold"
            """,
            styles,
        )
    )

    story.append(PageBreak())

    add_heading(story, "5. What Files Are Produced", styles)
    story.append(
        Paragraph(
            "The exact filenames depend on the category. For Scope 2, the default generated files are:",
            styles["Body"],
        )
    )
    story.append(
        code_block(
            """
data/bronze/scope2_bronze.csv

data/silver/01_scope2_silver_reviewed.xlsx
data/silver/02_scope2_silver_normalized.xlsx
data/silver/03_scope2_silver_curated.xlsx
data/silver/04_scope2_silver_aggregated.xlsx
data/silver/05_scope2_silver_proration_calculation.xlsx
data/silver/06_scope2_silver_proration_split.xlsx
data/silver/07_scope2_silver_prorated.xlsx
            """,
            styles,
        )
    )
    story.append(
        Paragraph(
            "For other categories, replace scope2 in the filename with scope1, water, or waste. "
            "For example, Water bronze output is water_bronze.csv.",
            styles["Body"],
        )
    )

    add_subheading(story, "Review checkpoint outputs", styles)
    story.append(
        Paragraph(
            "Because category_checkpoint_dirs is currently true, checkpoints are grouped by category. "
            "For Scope 2, they are written under data/output/checkpoints/scope2.",
            styles["Body"],
        )
    )
    story.append(
        code_block(
            """
data/output/checkpoints/scope2/step_0_manual_data_entry_queue.csv
data/output/checkpoints/scope2/step_0_manual_data_entry_decisions_checkpoint.csv
data/output/checkpoints/scope2/step_1_field_quality_checkpoint.csv
data/output/checkpoints/scope2/step_2_review_summary_checkpoint.csv
data/output/checkpoints/scope2/step_3_review_issues_checkpoint.csv
data/output/checkpoints/scope2/step_4_manual_review_decisions_checkpoint.csv
data/output/checkpoints/scope2/step_5_approved_silver_checkpoint.csv
            """,
            styles,
        )
    )
    story.append(
        Paragraph(
            "If category_checkpoint_dirs is changed to false, all category checkpoint files are written directly "
            "inside review_checkpoint_output. Keeping it true is usually safer because it prevents categories "
            "from overwriting each other's checkpoint files.",
            styles["Body"],
        )
    )

    add_heading(story, "6. How To Run", styles)
    add_subheading(story, "Run with paths from settings.yaml", styles)
    story.append(
        code_block(
            r"""
cd "C:\Users\My PC\Desktop\snl-esg-ocr"
.\.venv\Scripts\python.exe main.py --category scope2
            """,
            styles,
        )
    )
    story.append(
        Paragraph(
            "Valid category values are scope1, scope2, water, and waste.",
            styles["Body"],
        )
    )
    story.append(
        code_block(
            r"""
.\.venv\Scripts\python.exe main.py --category scope1
.\.venv\Scripts\python.exe main.py --category scope2
.\.venv\Scripts\python.exe main.py --category water
.\.venv\Scripts\python.exe main.py --category waste
            """,
            styles,
        )
    )

    add_subheading(story, "Run with a one-time input override", styles)
    story.append(
        code_block(
            r"""
.\.venv\Scripts\python.exe main.py --category scope2 --input "C:/Users/My PC/Desktop/raw_json"
            """,
            styles,
        )
    )
    story.append(
        Paragraph(
            "The --input value overrides only the input folder for that run. Output folders still come from settings.yaml.",
            styles["Body"],
        )
    )

    add_subheading(story, "Start the review app", styles)
    story.append(
        code_block(
            r"""
.\.venv\Scripts\streamlit.exe run review_app.py
            """,
            styles,
        )
    )
    story.append(
        Paragraph(
            "The review app reads the same configured bronze, silver, checkpoint, and manual upload folders. "
            "If you change output paths, restart the app so it loads the new settings.",
            styles["Body"],
        )
    )

    add_heading(story, "7. Recommended Path Patterns", styles)
    story.append(
        table(
            [
                ["Scenario", "Recommended setting"],
                ["Testing inside the project", "Use relative paths such as data/source and data/silver"],
                ["Daily work with synced raw OCR files", "Use an absolute raw_json path pointing to the synced folder"],
                ["Sharing outputs with a team", "Use absolute output paths inside a synced team folder"],
                ["Avoiding category conflicts", "Leave category_checkpoint_dirs set to true"],
                ["Temporary experiment", "Use --input for the input folder and leave settings.yaml unchanged"],
            ],
            [2.35 * inch, 4.45 * inch],
            styles,
        )
    )

    add_heading(story, "8. Rules For Editing YAML Paths", styles)
    story.append(
        bullets(
            [
                "Keep paths inside quotation marks when they contain spaces.",
                "Use forward slashes, for example C:/Users/My PC/Desktop/raw_json.",
                "Indent child settings with two spaces under paths.",
                "Do not use tabs in YAML.",
                "Make sure the folder exists or that the pipeline has permission to create it.",
                "Close output CSV or Excel files before running the pipeline again.",
            ],
            styles,
        )
    )

    add_heading(story, "9. Step-By-Step Example", styles)
    story.append(
        Paragraph(
            "This example changes Scope 2 input files to a SharePoint folder and writes all generated outputs to a Desktop folder.",
            styles["Body"],
        )
    )
    story.append(
        numbered(
            [
                "Open config/settings.yaml.",
                "Change raw_json_scope2 to the folder that contains your OCR JSON files.",
                "Change bronze_output, silver_excel_output, review_checkpoint_output, manual_data_entry_uploads, and gold_output if you want generated files somewhere else.",
                "Save settings.yaml.",
                "Run main.py with --category scope2.",
                "Check the bronze CSV and silver Excel files in the output folders.",
            ],
            styles,
        )
    )
    story.append(
        code_block(
            """
paths:
  raw_json_scope2: "C:/Users/My PC/SharePoint/raw_json"

  bronze_output: "C:/Users/My PC/Desktop/esg_outputs/bronze"
  silver_excel_output: "C:/Users/My PC/Desktop/esg_outputs/silver"
  review_checkpoint_output: "C:/Users/My PC/Desktop/esg_outputs/checkpoints"
  manual_data_entry_uploads: "C:/Users/My PC/Desktop/esg_outputs/manual_uploads"
  category_checkpoint_dirs: true
  gold_output: "C:/Users/My PC/Desktop/esg_outputs/gold"
            """,
            styles,
        )
    )
    story.append(
        code_block(
            r"""
.\.venv\Scripts\python.exe main.py --category scope2
            """,
            styles,
        )
    )

    add_heading(story, "10. Troubleshooting", styles)
    story.append(
        table(
            [
                ["Problem", "Likely cause", "Fix"],
                ["No JSON files found", "Input path points to the wrong folder or folder is empty", "Check raw_json_<category> or rerun with --input"],
                ["YAML error", "Bad indentation, missing quote, or tab character", "Use two spaces under paths and quote paths with spaces"],
                ["Cannot write CSV or Excel", "Output file is open in Excel or locked", "Close the output file and run again"],
                ["Review app shows old files", "App cache or old running session", "Click refresh in the app or restart Streamlit"],
                ["Checkpoints mixed between categories", "category_checkpoint_dirs disabled", "Set category_checkpoint_dirs: true"],
                ["One category uses wrong input", "Running without the intended --category", "Pass --category scope1/scope2/water/waste explicitly"],
            ],
            [1.75 * inch, 2.45 * inch, 2.6 * inch],
            styles,
        )
    )

    add_heading(story, "11. Final Checklist", styles)
    story.append(
        bullets(
            [
                "config/settings.yaml exists and contains the desired paths.",
                "The selected raw_json_<category> folder contains .json files.",
                "Output folders are correct and writable.",
                "category_checkpoint_dirs is true unless you intentionally want one shared checkpoint folder.",
                "The command includes the correct --category value.",
                "Any previously generated CSV or Excel files are closed before rerunning.",
            ],
            styles,
        )
    )

    story.append(Spacer(1, 0.15 * inch))
    story.append(
        Paragraph(
            "Generated for the local workspace at C:/Users/My PC/Desktop/snl-esg-ocr.",
            ParagraphStyle(
                "SmallNote",
                parent=styles["Body"],
                fontSize=8,
                leading=10,
                textColor=colors.HexColor("#627d98"),
                alignment=TA_LEFT,
            ),
        )
    )

    doc.build(story)


if __name__ == "__main__":
    build()
