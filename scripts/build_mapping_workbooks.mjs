import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(".");
const mappingDir = path.join(projectRoot, "mappings");
const outputDir = mappingDir;

const colors = {
  navy: "#17365D",
  blue: "#D9EAF7",
  green: "#E2F0D9",
  gray: "#F2F2F2",
  border: "#B7C9D6",
  text: "#1F2933",
};

const workbookSpecs = [
  {
    fileName: "mapping.xlsx",
    sheetName: "mapping",
    tableName: "MappingTable",
    headers: [
      "active",
      "account_number",
      "supplier_name",
      "ocr_legal_entity_name_list",
      "ocr_unit_name_list",
      "legal_entity",
      "unit_name",
      "division",
      "division_shorthand",
      "facility_type",
      "facility_identifier",
      "scope",
      "activity_group",
      "document_type",
      "document_language",
      "invoice_frequency",
      "invoice_count",
      "supplier_number_oracle",
      "operating_unit_oracle",
      "supplier_site_name_oracle",
      "currency",
      "consumption_unit",
      "decimal_separator",
      "date_format",
      "allocation",
      "division_allocation",
      "ocr_trained",
      "labeled_by",
      "last_date_reviewed",
      "msm_facility_name",
      "msm_organizational_unit",
      "notes",
    ],
    rows: [
      {
        active: "Yes",
        account_number: "ABC123-1",
        supplier_name: "CONSTELLATION NEWENERGY INCORPORATED",
        legal_entity: "Stolt_Nielsen_USA_Inc._Corporate",
        unit_name: "Houston (Corporate)",
        division: "Corporate",
        division_shorthand: "Multiple",
        facility_type: "Office",
        facility_identifier: "Office - Houston",
        scope: "Scope 2",
        activity_group: "Electricity",
        document_type: "Invoice",
        document_language: "EN",
        invoice_frequency: "Monthly",
        invoice_count: 3,
        supplier_number_oracle: 1002219,
        operating_unit_oracle: "OF USD OU",
        supplier_site_name_oracle: "CARO-PO 4640",
        currency: "USD",
        consumption_unit: "kWh",
        decimal_separator: ".",
        date_format: "mm/dd/yyyy",
        allocation: "No",
        division_allocation: "Yes",
        ocr_trained: "Yes",
        labeled_by: "JZS",
        last_date_reviewed: new Date(Date.UTC(2026, 5, 1)),
      },
      {
        active: "Yes",
        account_number: "ABC123-2",
        supplier_name: "CONSTELLATION NEWENERGY INCORPORATED",
        legal_entity: "Stolt_Nielsen_USA_Inc._Corporate",
        unit_name: "Houston (Corporate)",
        division: "Corporate",
        division_shorthand: "Multiple",
        facility_type: "Office",
        facility_identifier: "Office - Houston",
        scope: "Scope 2",
        activity_group: "Electricity",
        document_type: "Invoice",
        document_language: "EN",
        invoice_frequency: "Monthly",
        invoice_count: 3,
        supplier_number_oracle: 1002219,
        operating_unit_oracle: "OF USD OU",
        supplier_site_name_oracle: "CARO-PO 4640",
        currency: "USD",
        consumption_unit: "kWh",
        decimal_separator: ".",
        date_format: "mm/dd/yyyy",
        allocation: "No",
        division_allocation: "Yes",
        ocr_trained: "Yes",
        labeled_by: "JZS",
        last_date_reviewed: new Date(Date.UTC(2026, 5, 1)),
      },
      {
        active: "Yes",
        account_number: "ABC123-3",
        supplier_name: "CONSTELLATION NEWENERGY INCORPORATED",
        legal_entity: "Stolt_Nielsen_USA_Inc._Corporate",
        unit_name: "Houston (Corporate)",
        division: "Corporate",
        division_shorthand: "Multiple",
        facility_type: "Office",
        facility_identifier: "Office - Houston",
        scope: "Scope 2",
        activity_group: "Electricity",
        document_type: "Invoice",
        document_language: "EN",
        invoice_frequency: "Monthly",
        invoice_count: 3,
        supplier_number_oracle: 1002219,
        operating_unit_oracle: "OF USD OU",
        supplier_site_name_oracle: "CARO-PO 4640",
        currency: "USD",
        consumption_unit: "kWh",
        decimal_separator: ".",
        date_format: "mm/dd/yyyy",
        allocation: "No",
        division_allocation: "Yes",
        ocr_trained: "Yes",
        labeled_by: "JZS",
        last_date_reviewed: new Date(Date.UTC(2026, 5, 1)),
      },
    ],
    widths: {
      A: 11, B: 18, C: 34, D: 30, E: 26, F: 34, G: 24, H: 18, I: 20,
      J: 16, K: 24, L: 14, M: 18, N: 16, O: 18, P: 18, Q: 14, R: 20,
      S: 20, T: 24, U: 12, V: 16, W: 16, X: 16, Y: 14, Z: 18, AA: 14,
      AB: 14, AC: 18, AD: 24, AE: 24, AF: 34,
    },
  },
  {
    fileName: "energy_source_allocation.xlsx",
    sheetName: "energy_source_allocation",
    tableName: "EnergySourceAllocationTable",
    keyColumns: ["unit_name", "supplier_name", "start_date"],
    keyDelimiter: "_",
    dateKeyColumns: ["start_date"],
    headers: [
      "lookup_key",
      "active",
      "division",
      "legal_entity",
      "unit_name",
      "facility_type",
      "supplier_name",
      "start_date",
      "scope",
      "activity_group",
      "unit",
      "fossil_fuel_%",
      "renewable_energy_%",
      "nuclear_%",
      "source",
      "created_by",
      "reviewed_by",
      "notes",
    ],
    rows: [
      {
        active: "Yes",
        division: "Corporate",
        legal_entity: "Stolt_Nielsen_USA_Inc._Corporate",
        unit_name: "Houston (Corporate)",
        facility_type: "Office",
        supplier_name: "CONSTELLATION NEWENERGY INCORPORATED",
        start_date: new Date(Date.UTC(2024, 11, 1)),
        scope: "Scope 2",
        activity_group: "Electricity",
        unit: "kWh",
        "fossil_fuel_%": 0.294,
        "renewable_energy_%": 0.507,
        "nuclear_%": 0.199,
      },
    ],
    widths: {
      A: 70, B: 11, C: 18, D: 34, E: 24, F: 16, G: 34, H: 14, I: 14,
      J: 18, K: 12, L: 16, M: 20, N: 14, O: 26, P: 16, Q: 16, R: 34,
    },
  },
  {
    fileName: "contracts.xlsx",
    sheetName: "contracts",
    tableName: "ContractsTable",
    keyColumns: ["unit_name", "supplier_name", "contract_start_date"],
    keyDelimiter: "_",
    dateKeyColumns: ["contract_start_date"],
    headers: [
      "lookup_key",
      "active",
      "division",
      "legal_entity",
      "unit_name",
      "supplier_name",
      "contract_start_date",
      "contract_end_date",
      "contractual_instruments",
      "bundle_or_unbundle",
      "energy_source",
      "energy_type",
      "energy_unit",
      "co2e",
      "co2e_unit",
      "ch4",
      "ch4_unit",
      "co2",
      "co2_unit",
      "hfcs",
      "hfcs_unit",
      "n2o",
      "n2o_unit",
      "nf3",
      "nf3_unit",
      "pfcs",
      "pfcs_unit",
      "sf6",
      "sf6_unit",
      "otherghgs",
      "otherghgs_unit",
      "source",
      "created_by",
      "reviewed_by",
      "notes",
    ],
    rows: [
      {
        active: "Yes",
        division: "Corporate",
        legal_entity: "Stolt_Nielsen_USA_Inc._Corporate",
        unit_name: "Houston (Corporate)",
        supplier_name: "CONSTELLATION NEWENERGY INCORPORATED",
        contract_start_date: new Date(Date.UTC(2025, 0, 9)),
        contract_end_date: new Date(Date.UTC(2025, 8, 30)),
        contractual_instruments: "Contracts(e.g. PPAs)",
        bundle_or_unbundle: "Unbundled",
        energy_source: "Mix-renewable",
        energy_type: "Electricity",
        energy_unit: "kWh",
        co2e: 0,
        co2e_unit: "kg",
        ch4: 0,
        ch4_unit: "kg",
        co2: 0,
        co2_unit: "kg",
        n2o: 0,
        n2o_unit: "kg",
      },
    ],
    widths: {
      A: 82, B: 11, C: 18, D: 34, E: 24, F: 34, G: 18, H: 18, I: 28,
      J: 20, K: 18, L: 16, M: 14, N: 12, O: 12, P: 12, Q: 12, R: 12,
      S: 12, T: 12, U: 12, V: 12, W: 12, X: 12, Y: 12, Z: 12, AA: 12,
      AB: 12, AC: 12, AD: 14, AE: 16, AF: 26, AG: 16, AH: 16, AI: 34,
    },
  },
];

function columnLetter(index) {
  let n = index + 1;
  let s = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    s = String.fromCharCode(65 + r) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function makeLookupFormula(headers, spec, rowNumber) {
  const refs = spec.keyColumns.map((header) => {
    const index = headers.indexOf(header);
    if (index < 0) {
      throw new Error(`Missing key column ${header}`);
    }
    return { header, ref: `${columnLetter(index)}${rowNumber}` };
  });
  const countA = refs.map(({ ref }) => ref).join(",");
  const delimiter = spec.keyDelimiter ?? "|";
  const dateKeyColumns = new Set(spec.dateKeyColumns ?? []);
  const joined = refs.map(({ header, ref }) => {
    if (dateKeyColumns.has(header)) {
      return `TEXT(${ref},"0")`;
    }
    return `LOWER(TRIM(${ref}&""))`;
  }).join(`&"${delimiter}"&`);
  return `=IF(COUNTA(${countA})=0,"",${joined})`;
}

function matrixForSpec(spec, reservedRows = 25) {
  const rows = [];
  for (let i = 0; i < reservedRows; i += 1) {
    const source = spec.rows[i] ?? {};
    rows.push(spec.headers.map((header) => {
      if (spec.keyColumns?.length && header === "lookup_key") {
        return null;
      }
      return source[header] ?? null;
    }));
  }
  return rows;
}

async function buildWorkbook(spec) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add(spec.sheetName);
  const notes = workbook.worksheets.add("_notes");

  const rowCount = 26;
  const colCount = spec.headers.length;
  const lastCol = columnLetter(colCount - 1);
  const tableRange = `A1:${lastCol}${rowCount}`;

  sheet.showGridLines = false;
  sheet.getRange(`A1:${lastCol}1`).values = [spec.headers];
  sheet.getRange(`A2:${lastCol}${rowCount}`).values = matrixForSpec(spec, rowCount - 1);
  if (spec.keyColumns?.length) {
    sheet.getRange(`A2:A${rowCount}`).formulas = Array.from({ length: rowCount - 1 }, (_, idx) => [
      makeLookupFormula(spec.headers, spec, idx + 2),
    ]);
  }

  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: colors.navy,
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    horizontalAlignment: "center",
  };
  sheet.getRange(tableRange).format.borders = {
    insideHorizontal: { style: "thin", color: colors.border },
    top: { style: "thin", color: colors.border },
    bottom: { style: "thin", color: colors.border },
  };
  if (spec.keyColumns?.length) {
    sheet.getRange(`A2:A${rowCount}`).format = {
      fill: colors.gray,
      font: { color: "#52616B" },
    };
  }
  const activeColumnIndex = spec.headers.indexOf("active");
  const activeColumn = activeColumnIndex >= 0 ? columnLetter(activeColumnIndex) : "B";
  sheet.getRange(`${activeColumn}2:${activeColumn}${rowCount}`).dataValidation = {
    rule: { type: "list", values: ["Yes", "No"] },
  };
  sheet.getRange(`A1:${lastCol}${rowCount}`).format.wrapText = true;
  sheet.freezePanes.freezeRows(1);
  sheet.tables.add(tableRange, true, spec.tableName);

  for (const [letter, width] of Object.entries(spec.widths)) {
    sheet.getRange(`${letter}:${letter}`).format.columnWidth = width;
  }

  const dateHeaders = ["start_date", "contract_start_date", "contract_end_date", "last_date_reviewed"];
  for (const header of dateHeaders) {
    const index = spec.headers.indexOf(header);
    if (index >= 0) {
      const letter = columnLetter(index);
      sheet.getRange(`${letter}2:${letter}${rowCount}`).format.numberFormat = "yyyy-mm-dd";
    }
  }

  const percentHeaders = ["fossil_fuel_%", "renewable_energy_%", "nuclear_%"];
  for (const header of percentHeaders) {
    const index = spec.headers.indexOf(header);
    if (index >= 0) {
      const letter = columnLetter(index);
      sheet.getRange(`${letter}2:${letter}${rowCount}`).format.numberFormat = "0.0%";
    }
  }

  notes.showGridLines = false;
  notes.getRange("A1:D1").values = [["Workbook", "Purpose", "Python lookup key", "Update notes"]];
  notes.getRange("A2:D2").values = [[
    spec.sheetName,
    "Editable reference table used by OCR-to-gold enrichment.",
    spec.keyColumns?.length ? spec.keyColumns.join(spec.keyDelimiter ?? " | ") : "No workbook lookup_key column.",
    spec.keyColumns?.length
      ? "Edit rows in the main table. Keep lookup_key formulas intact or copy the formula down for new rows."
      : "Edit rows in the main table. This workbook intentionally has no lookup_key column.",
  ]];
  notes.getRange("A1:D1").format = {
    fill: colors.navy,
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
  notes.getRange("A2:D2").format = {
    fill: colors.blue,
    font: { color: colors.text },
    wrapText: true,
  };
  notes.getRange("A:A").format.columnWidth = 28;
  notes.getRange("B:B").format.columnWidth = 46;
  notes.getRange("C:C").format.columnWidth = 62;
  notes.getRange("D:D").format.columnWidth = 68;
  notes.freezePanes.freezeRows(1);

  const preview = await workbook.render({
    sheetName: spec.sheetName,
    range: `A1:${lastCol}8`,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(mappingDir, `${path.basename(spec.fileName, ".xlsx")}_preview.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );

  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(outputDir, spec.fileName));
}

await fs.mkdir(mappingDir, { recursive: true });

const requestedNames = new Set(process.argv.slice(2));
for (const spec of workbookSpecs) {
  if (requestedNames.size && !requestedNames.has(path.basename(spec.fileName, ".xlsx"))) {
    continue;
  }
  await buildWorkbook(spec);
}
