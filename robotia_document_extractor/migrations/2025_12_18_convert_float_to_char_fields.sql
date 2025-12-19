-- BEFORE

ALTER TABLE res_partner
RENAME COLUMN business_license_number TO business_id;

ALTER TABLE document_extraction
RENAME COLUMN business_license_number TO business_id;


-- AFTER


UPDATE quota_usage
SET average_price = regexp_replace(average_price, '\.0+$', '')
WHERE average_price ~ '\.0+$';

UPDATE equipment_product
SET substance_quantity_per_unit = regexp_replace(substance_quantity_per_unit, '\.0+$', '')
WHERE substance_quantity_per_unit ~ '\.0+$';

UPDATE equipment_product_report
SET substance_quantity_per_unit = regexp_replace(substance_quantity_per_unit, '\.0+$', '')
WHERE substance_quantity_per_unit ~ '\.0+$';
