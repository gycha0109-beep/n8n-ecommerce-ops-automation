INSERT INTO sku_master (sku, product_name, active) VALUES
  ('SKU-RED-001', 'Red Widget', true),
  ('SKU-BLU-002', 'Blue Widget', true),
  ('SKU-GRN-003', 'Green Widget', true),
  ('SKU-BLK-004', 'Black Widget', true),
  ('SKU-WHT-005', 'White Widget', true),
  ('SKU-LTD-006', 'Limited Widget', true)
ON CONFLICT (sku) DO UPDATE SET product_name = EXCLUDED.product_name, active = EXCLUDED.active;

INSERT INTO inventory (sku, available_quantity, reserved_quantity) VALUES
  ('SKU-RED-001', 120, 0),
  ('SKU-BLU-002', 100, 0),
  ('SKU-GRN-003', 90, 0),
  ('SKU-BLK-004', 80, 0),
  ('SKU-WHT-005', 70, 0),
  ('SKU-LTD-006', 2, 0)
ON CONFLICT (sku) DO UPDATE SET available_quantity = EXCLUDED.available_quantity, reserved_quantity = 0, updated_at = now();
