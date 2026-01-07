-- ============================================================================
-- CAPACITY NORMALIZATION MIGRATION SCRIPT
-- ============================================================================
-- Purpose: Populate 'capacity' field from 'cooling_capacity' and 'power_capacity'
--          for records created >= 2026-01-01
--
-- Logic:
--   - If both cooling AND power exist: capacity = cooling || '/' || power
--   - If only cooling exists: capacity = cooling_capacity
--   - If only power exists: capacity = power_capacity
--   - Skip records where capacity already has value
-- ============================================================================

-- Start transaction
BEGIN;

-- ============================================================================
-- TABLE 1: equipment_product (Table 1.2 - Form 01)
-- ============================================================================
UPDATE equipment_product
SET capacity = CASE
    WHEN cooling_capacity IS NOT NULL AND cooling_capacity != ''
         AND power_capacity IS NOT NULL AND power_capacity != ''
    THEN cooling_capacity || '/' || power_capacity

    WHEN cooling_capacity IS NOT NULL AND cooling_capacity != ''
    THEN cooling_capacity

    WHEN power_capacity IS NOT NULL AND power_capacity != ''
    THEN power_capacity

    ELSE NULL
END
WHERE create_date >= '2026-01-01 00:00:00'
  AND (capacity IS NULL OR capacity = '')
  AND (cooling_capacity IS NOT NULL OR power_capacity IS NOT NULL);

-- Log result
SELECT 'equipment_product' AS table_name, COUNT(*) AS migrated_count
FROM equipment_product
WHERE create_date >= '2026-01-01 00:00:00'
  AND capacity IS NOT NULL
  AND capacity != ''
  AND (cooling_capacity IS NOT NULL OR power_capacity IS NOT NULL);


-- ============================================================================
-- TABLE 2: equipment_ownership (Table 1.3 - Form 01)
-- ============================================================================
UPDATE equipment_ownership
SET capacity = CASE
    WHEN cooling_capacity IS NOT NULL AND cooling_capacity != ''
         AND power_capacity IS NOT NULL AND power_capacity != ''
    THEN cooling_capacity || '/' || power_capacity

    WHEN cooling_capacity IS NOT NULL AND cooling_capacity != ''
    THEN cooling_capacity

    WHEN power_capacity IS NOT NULL AND power_capacity != ''
    THEN power_capacity

    ELSE NULL
END
WHERE create_date >= '2026-01-01 00:00:00'
  AND (capacity IS NULL OR capacity = '')
  AND (cooling_capacity IS NOT NULL OR power_capacity IS NOT NULL);

-- Log result
SELECT 'equipment_ownership' AS table_name, COUNT(*) AS migrated_count
FROM equipment_ownership
WHERE create_date >= '2026-01-01 00:00:00'
  AND capacity IS NOT NULL
  AND capacity != ''
  AND (cooling_capacity IS NOT NULL OR power_capacity IS NOT NULL);


-- ============================================================================
-- TABLE 3: equipment_product_report (Table 2.2 - Form 02)
-- ============================================================================
UPDATE equipment_product_report
SET capacity = CASE
    WHEN cooling_capacity IS NOT NULL AND cooling_capacity != ''
         AND power_capacity IS NOT NULL AND power_capacity != ''
    THEN cooling_capacity || '/' || power_capacity

    WHEN cooling_capacity IS NOT NULL AND cooling_capacity != ''
    THEN cooling_capacity

    WHEN power_capacity IS NOT NULL AND power_capacity != ''
    THEN power_capacity

    ELSE NULL
END
WHERE create_date >= '2026-01-01 00:00:00'
  AND (capacity IS NULL OR capacity = '')
  AND (cooling_capacity IS NOT NULL OR power_capacity IS NOT NULL);

-- Log result
SELECT 'equipment_product_report' AS table_name, COUNT(*) AS migrated_count
FROM equipment_product_report
WHERE create_date >= '2026-01-01 00:00:00'
  AND capacity IS NOT NULL
  AND capacity != ''
  AND (cooling_capacity IS NOT NULL OR power_capacity IS NOT NULL);


-- ============================================================================
-- TABLE 4: equipment_ownership_report (Table 2.3 - Form 02)
-- ============================================================================
UPDATE equipment_ownership_report
SET capacity = CASE
    WHEN cooling_capacity IS NOT NULL AND cooling_capacity != ''
         AND power_capacity IS NOT NULL AND power_capacity != ''
    THEN cooling_capacity || '/' || power_capacity

    WHEN cooling_capacity IS NOT NULL AND cooling_capacity != ''
    THEN cooling_capacity

    WHEN power_capacity IS NOT NULL AND power_capacity != ''
    THEN power_capacity

    ELSE NULL
END
WHERE create_date >= '2026-01-01 00:00:00'
  AND (capacity IS NULL OR capacity = '')
  AND (cooling_capacity IS NOT NULL OR power_capacity IS NOT NULL);

-- Log result
SELECT 'equipment_ownership_report' AS table_name, COUNT(*) AS migrated_count
FROM equipment_ownership_report
WHERE create_date >= '2026-01-01 00:00:00'
  AND capacity IS NOT NULL
  AND capacity != ''
  AND (cooling_capacity IS NOT NULL OR power_capacity IS NOT NULL);


-- ============================================================================
-- SUMMARY: Total migrated records across all tables
-- ============================================================================
SELECT
    'TOTAL' AS summary,
    (SELECT COUNT(*) FROM equipment_product
     WHERE create_date >= '2026-01-01' AND capacity IS NOT NULL AND capacity != '') +
    (SELECT COUNT(*) FROM equipment_ownership
     WHERE create_date >= '2026-01-01' AND capacity IS NOT NULL AND capacity != '') +
    (SELECT COUNT(*) FROM equipment_product_report
     WHERE create_date >= '2026-01-01' AND capacity IS NOT NULL AND capacity != '') +
    (SELECT COUNT(*) FROM equipment_ownership_report
     WHERE create_date >= '2026-01-01' AND capacity IS NOT NULL AND capacity != '')
    AS total_migrated_records;

-- Commit transaction
COMMIT;

-- ============================================================================
-- VERIFICATION QUERY (Optional - Run after migration)
-- ============================================================================
-- Check sample records to verify migration
/*
SELECT 'equipment_product' AS table_name, id, cooling_capacity, power_capacity, capacity
FROM equipment_product
WHERE create_date >= '2026-01-01 00:00:00'
LIMIT 5;

SELECT 'equipment_ownership' AS table_name, id, cooling_capacity, power_capacity, capacity
FROM equipment_ownership
WHERE create_date >= '2026-01-01 00:00:00'
LIMIT 5;

SELECT 'equipment_product_report' AS table_name, id, cooling_capacity, power_capacity, capacity
FROM equipment_product_report
WHERE create_date >= '2026-01-01 00:00:00'
LIMIT 5;

SELECT 'equipment_ownership_report' AS table_name, id, cooling_capacity, power_capacity, capacity
FROM equipment_ownership_report
WHERE create_date >= '2026-01-01 00:00:00'
LIMIT 5;
*/
