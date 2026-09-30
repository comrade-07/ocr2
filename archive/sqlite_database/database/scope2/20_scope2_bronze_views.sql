-- ---------------------------------------------------------------------------
-- Bronze helper views
-- ---------------------------------------------------------------------------

CREATE VIEW IF NOT EXISTS v_bronze_ocr_scope2 AS
SELECT
    ocr_record_id,
    source_file,
    source_path,
    sharepoint_link,
    legal_entity,
    unit_name,
    supplier,
    invoice_date,
    invoice_date_normalized,
    account_number,
    total_amount,
    consumption_start_date_1,
    consumption_start_date_1_normalized,
    consumption_end_date_1,
    consumption_end_date_1_normalized,
    consumption_start_date_2,
    consumption_start_date_2_normalized,
    consumption_end_date_2,
    consumption_end_date_2_normalized,
    quantity_1,
    quantity_2,
    quantity_3,
    quantity_4,
    quantity_5,
    quantity_6,
    quantity_unit_1,
    quantity_unit_2,
    document_confidence,
    status,
    needs_review,
    missing_fields,
    low_confidence_fields,
    bronze_record_key
FROM bronze_ocr_scope2;

CREATE VIEW IF NOT EXISTS v_bronze_ocr_quantities AS
SELECT ocr_record_id, source_file, 'quantity_1' AS quantity_column, quantity_1 AS quantity_value, quantity_1_confidence AS quantity_confidence, quantity_unit_1 AS quantity_unit
FROM bronze_ocr_scope2
WHERE nullif(trim(coalesce(quantity_1, '')), '') IS NOT NULL
UNION ALL
SELECT ocr_record_id, source_file, 'quantity_2', quantity_2, quantity_2_confidence, quantity_unit_1
FROM bronze_ocr_scope2
WHERE nullif(trim(coalesce(quantity_2, '')), '') IS NOT NULL
UNION ALL
SELECT ocr_record_id, source_file, 'quantity_3', quantity_3, quantity_3_confidence, quantity_unit_1
FROM bronze_ocr_scope2
WHERE nullif(trim(coalesce(quantity_3, '')), '') IS NOT NULL
UNION ALL
SELECT ocr_record_id, source_file, 'quantity_4', quantity_4, quantity_4_confidence, quantity_unit_1
FROM bronze_ocr_scope2
WHERE nullif(trim(coalesce(quantity_4, '')), '') IS NOT NULL
UNION ALL
SELECT ocr_record_id, source_file, 'quantity_5', quantity_5, quantity_5_confidence, quantity_unit_1
FROM bronze_ocr_scope2
WHERE nullif(trim(coalesce(quantity_5, '')), '') IS NOT NULL
UNION ALL
SELECT ocr_record_id, source_file, 'quantity_6', quantity_6, quantity_6_confidence, quantity_unit_2
FROM bronze_ocr_scope2
WHERE nullif(trim(coalesce(quantity_6, '')), '') IS NOT NULL;

CREATE VIEW IF NOT EXISTS v_bronze_selected_energy_quantity AS
SELECT
    o.ocr_record_id,
    o.source_file,
    coalesce(qs.selected_quantity_column, 'quantity_1') AS selected_quantity_column,
    CASE coalesce(qs.selected_quantity_column, 'quantity_1')
        WHEN 'quantity_1' THEN o.quantity_1
        WHEN 'quantity_2' THEN o.quantity_2
        WHEN 'quantity_3' THEN o.quantity_3
        WHEN 'quantity_4' THEN o.quantity_4
        WHEN 'quantity_5' THEN o.quantity_5
        WHEN 'quantity_6' THEN o.quantity_6
    END AS amount_of_energy_consumed_raw,
    CASE coalesce(qs.selected_quantity_unit_column, 'quantity_unit_1')
        WHEN 'quantity_unit_1' THEN o.quantity_unit_1
        WHEN 'quantity_unit_2' THEN o.quantity_unit_2
    END AS energy_unit,
    qs.reason AS quantity_selection_reason
FROM bronze_ocr_scope2 o
LEFT JOIN ocr_quantity_selection qs
    ON qs.ocr_record_id = o.ocr_record_id;
