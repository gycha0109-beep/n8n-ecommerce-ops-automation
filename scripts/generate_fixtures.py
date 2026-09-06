#!/usr/bin/env python3
from pathlib import Path
import csv, json

BASE = Path(__file__).resolve().parents[1]
FIX = BASE / 'fixtures'
FIX.mkdir(exist_ok=True)

# 42 synthetic orders. Every identifier and value is deterministic.
rows = []

def add(source, oid, email, sku, qty, price, currency='KRW', status='paid', mode='normal', notify='normal', created='2026-09-01T09:00:00+09:00'):
    rows.append(dict(source=source, external_order_id=oid, email=email, sku=sku, quantity=qty,
                     price=price, currency=currency, status=status, integration_mode=mode,
                     notification_mode=notify, created_at=created))

# 24 valid baseline orders, distributed across channels.
for i in range(1, 25):
    source = ('shopify', 'amazon', 'marketplace')[(i-1) % 3]
    sku = ('SKU-RED-001','SKU-BLU-002','SKU-GRN-003','SKU-BLK-004','SKU-WHT-005')[(i-1) % 5]
    add(source, f'{source[:4].upper()}-{10000+i}', f'demo{i:02d}@example.com', sku, (i % 3)+1, 10000 + i*100)

# Structured exceptions / failures.
add('shopify', 'SHOP-CANCEL-01', 'cancel@example.com', 'SKU-RED-001', 1, 12000, status='cancelled')
add('amazon', 'AMZN-CANCEL-01', 'cancel2@example.com', 'SKU-BLU-002', 1, 13000, status='cancelled')
add('marketplace', 'MKT-CANCEL-01', 'cancel3@example.com', 'SKU-GRN-003', 1, 14000, status='cancelled')
add('shopify', 'SHOP-MISSING-SKU', 'missing-sku@example.com', '', 1, 11000)
add('amazon', 'AMZN-UNKNOWN-SKU', 'unknown@example.com', 'SKU-NOT-FOUND', 1, 11000)
add('marketplace', 'MKT-QTY-ZERO', 'zero@example.com', 'SKU-RED-001', 0, 11000)
add('shopify', 'SHOP-QTY-NEG', 'neg@example.com', 'SKU-BLU-002', -2, 11000)
add('amazon', 'AMZN-LOW-STOCK', 'stock@example.com', 'SKU-LTD-006', 5, 11000)
add('marketplace', 'MKT-BAD-EMAIL', 'not-an-email', 'SKU-GRN-003', 1, 11000)
add('shopify', '', 'missing-order@example.com', 'SKU-BLK-004', 1, 11000)
add('amazon', 'AMZN-BAD-CURRENCY', 'currency@example.com', 'SKU-WHT-005', 1, 11000, currency='BTC')
add('marketplace', 'MKT-MALFORMED-QTY', 'csv@example.com', 'SKU-RED-001', 'not-a-number', 11000)
add('shopify', 'SHOP-RETRY-RECOVER', 'retry@example.com', 'SKU-BLU-002', 1, 15000, mode='fail_twice_then_success')
add('amazon', 'AMZN-API-FAIL', 'fail@example.com', 'SKU-GRN-003', 1, 15000, mode='always_500')
add('marketplace', 'MKT-TIMEOUT', 'timeout@example.com', 'SKU-BLK-004', 1, 15000, mode='timeout')
add('shopify', 'SHOP-NOTIFY-FAIL', 'notify@example.com', 'SKU-WHT-005', 1, 15000, notify='fail_notification')

assert len(rows) == 40, len(rows)

# Explicit duplicate webhook / duplicate CSV deliveries.
rows.append(dict(rows[0]))
rows.append(dict(rows[1]))
assert len(rows) == 42, len(rows)

shopify = []
amazon = []
market = []
for r in rows:
    if r['source'] == 'shopify':
        shopify.append({
            'id': r['external_order_id'], 'email': r['email'], 'financial_status': r['status'],
            'created_at': r['created_at'], 'currency': r['currency'],
            'line_items': [{'sku': r['sku'], 'quantity': r['quantity'], 'price': r['price']}],
            'integration_mode': r['integration_mode'], 'notification_mode': r['notification_mode']
        })
    elif r['source'] == 'amazon':
        amazon.append({
            'amazon_order_id': r['external_order_id'], 'buyer_email': r['email'], 'seller_sku': r['sku'],
            'item_quantity': r['quantity'], 'item_price': r['price'], 'currency_code': r['currency'],
            'order_status': r['status'], 'purchase_date': r['created_at'],
            'integration_mode': r['integration_mode'], 'notification_mode': r['notification_mode']
        })
    else:
        market.append({
            'order_no': r['external_order_id'], 'email': r['email'], 'product_sku': r['sku'],
            'qty': r['quantity'], 'price': r['price'], 'currency': r['currency'], 'status': r['status'],
            'created': r['created_at'], 'integration_mode': r['integration_mode'],
            'notification_mode': r['notification_mode']
        })

(FIX / 'shopify_orders.json').write_text(json.dumps(shopify, indent=2), encoding='utf-8')

def write_csv(path, data, fields):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        w.writeheader(); w.writerows(data)

write_csv(FIX / 'amazon_orders.csv', amazon, ['amazon_order_id','buyer_email','seller_sku','item_quantity','item_price','currency_code','order_status','purchase_date','integration_mode','notification_mode'])
write_csv(FIX / 'marketplace_orders.csv', market, ['order_no','email','product_sku','qty','price','currency','status','created','integration_mode','notification_mode'])

with (FIX / 'inventory.csv').open('w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, lineterminator='\n'); w.writerow(['sku','available_quantity'])
    w.writerows([['SKU-RED-001',120],['SKU-BLU-002',100],['SKU-GRN-003',90],['SKU-BLK-004',80],['SKU-WHT-005',70],['SKU-LTD-006',2]])
with (FIX / 'sku_master.csv').open('w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, lineterminator='\n'); w.writerow(['sku','product_name','active'])
    w.writerows([['SKU-RED-001','Red Widget',1],['SKU-BLU-002','Blue Widget',1],['SKU-GRN-003','Green Widget',1],['SKU-BLK-004','Black Widget',1],['SKU-WHT-005','White Widget',1],['SKU-LTD-006','Limited Widget',1]])

print(f'generated {len(shopify)+len(amazon)+len(market)} synthetic rows')
