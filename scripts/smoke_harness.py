#!/usr/bin/env python3
from pathlib import Path
import base64, csv, json, re, sqlite3, time, urllib.request, urllib.error, sys

BASE = Path(__file__).resolve().parents[1]
FIX = BASE / 'fixtures'
GEN = BASE / 'generated'
GEN.mkdir(exist_ok=True)
DB = GEN / 'smoke.db'
API = 'http://127.0.0.1:3000'
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
VALID_CURRENCIES = {'KRW','USD','JPY','EUR'}

SCHEMA = '''
CREATE TABLE sku_master(sku TEXT PRIMARY KEY, product_name TEXT NOT NULL, active INTEGER NOT NULL);
CREATE TABLE inventory(sku TEXT PRIMARY KEY, available_quantity INTEGER NOT NULL CHECK(available_quantity >= 0), reserved_quantity INTEGER NOT NULL DEFAULT 0 CHECK(reserved_quantity >= 0));
CREATE TABLE orders(order_key TEXT PRIMARY KEY, source TEXT NOT NULL, external_order_id TEXT NOT NULL, customer_email TEXT NOT NULL, sku TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), unit_price REAL NOT NULL, currency TEXT NOT NULL, order_status TEXT NOT NULL, retry_recovered INTEGER NOT NULL, payload TEXT NOT NULL, processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE exceptions(idempotency_key TEXT PRIMARY KEY, order_key TEXT, source TEXT, external_order_id TEXT, error_code TEXT NOT NULL, error_message TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE failed_jobs(job_key TEXT PRIMARY KEY, order_key TEXT, source TEXT, external_order_id TEXT, error_code TEXT NOT NULL, error_message TEXT NOT NULL, payload TEXT NOT NULL, attempts INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'dead_letter', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE processed_events(event_key TEXT PRIMARY KEY, order_key TEXT NOT NULL, delivery_count INTEGER NOT NULL DEFAULT 1);
'''

SKU = {'SKU-RED-001':'Red Widget','SKU-BLU-002':'Blue Widget','SKU-GRN-003':'Green Widget','SKU-BLK-004':'Black Widget','SKU-WHT-005':'White Widget','SKU-LTD-006':'Limited Widget'}
INV = {'SKU-RED-001':120,'SKU-BLU-002':100,'SKU-GRN-003':90,'SKU-BLK-004':80,'SKU-WHT-005':70,'SKU-LTD-006':2}

def reset_db(path=DB):
    if path.exists(): path.unlink()
    con = sqlite3.connect(path, isolation_level=None)
    con.executescript(SCHEMA)
    con.executemany('INSERT INTO sku_master VALUES (?,?,1)', SKU.items())
    con.executemany('INSERT INTO inventory VALUES (?,?,0)', INV.items())
    con.commit(); return con

def load_rows():
    out=[]
    for r in json.loads((FIX/'shopify_orders.json').read_text(encoding='utf-8')):
        li=(r.get('line_items') or [{}])[0]
        out.append({'source':'shopify','external_order_id':r.get('id'),'customer_email':r.get('email'),'sku':li.get('sku'),'quantity':li.get('quantity'),'unit_price':li.get('price'),'currency':r.get('currency'),'order_status':r.get('financial_status'),'created_at':r.get('created_at'),'integration_mode':r.get('integration_mode','normal'),'notification_mode':r.get('notification_mode','normal'),'raw_payload':r})
    with (FIX/'amazon_orders.csv').open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            out.append({'source':'amazon','external_order_id':r.get('amazon_order_id'),'customer_email':r.get('buyer_email'),'sku':r.get('seller_sku'),'quantity':r.get('item_quantity'),'unit_price':r.get('item_price'),'currency':r.get('currency_code'),'order_status':r.get('order_status'),'created_at':r.get('purchase_date'),'integration_mode':r.get('integration_mode','normal'),'notification_mode':r.get('notification_mode','normal'),'raw_payload':r})
    with (FIX/'marketplace_orders.csv').open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            out.append({'source':'marketplace','external_order_id':r.get('order_no'),'customer_email':r.get('email'),'sku':r.get('product_sku'),'quantity':r.get('qty'),'unit_price':r.get('price'),'currency':r.get('currency'),'order_status':r.get('status'),'created_at':r.get('created'),'integration_mode':r.get('integration_mode','normal'),'notification_mode':r.get('notification_mode','normal'),'raw_payload':r})
    return out

def canonicalize(p):
    p = dict(p)
    p['source'] = str(p.get('source') or '').strip().lower()
    p['external_order_id'] = str(p.get('external_order_id') or '').strip()
    p['order_key'] = f"{p['source']}:{p['external_order_id']}" if p['source'] else f"unknown:{p['external_order_id']}"
    p['customer_email'] = str(p.get('customer_email') or '').strip().lower()
    p['sku'] = str(p.get('sku') or '').strip()
    p['currency'] = str(p.get('currency') or '').strip().upper()
    p['order_status'] = str(p.get('order_status') or '').strip().lower()
    try: p['quantity'] = int(p.get('quantity'))
    except (TypeError, ValueError): p['quantity'] = None
    try: p['unit_price'] = float(p.get('unit_price'))
    except (TypeError, ValueError): p['unit_price'] = None
    return p

def classify(p):
    if p['order_status'] in {'cancelled','canceled'}:
        return ('ORDER_CANCELLED','Cancelled orders are excluded from normal processing')
    if not p['external_order_id'] or not p['customer_email'] or not p['sku'] or not p.get('created_at'):
        return ('MISSING_FIELD','Required order field is missing')
    if not EMAIL.match(p['customer_email']):
        return ('MALFORMED_EMAIL','Customer email is malformed')
    if p['quantity'] is None:
        return ('MALFORMED_INPUT','Quantity is not numeric')
    if p['quantity'] <= 0:
        return ('INVALID_QUANTITY','Quantity must be greater than zero')
    if p['unit_price'] is None or p['unit_price'] < 0:
        return ('MALFORMED_INPUT','Unit price is invalid')
    if p['currency'] not in VALID_CURRENCIES:
        return ('INVALID_CURRENCY','Unsupported currency')
    return None

def exc(con, p, code, message):
    key=f"{p['order_key']}:{code}"
    con.execute('INSERT OR IGNORE INTO exceptions(idempotency_key,order_key,source,external_order_id,error_code,error_message,payload) VALUES(?,?,?,?,?,?,?)', (key,p['order_key'],p['source'],p['external_order_id'],code,message,json.dumps(p['raw_payload'],ensure_ascii=False)))

def failed(con, p, code, message, attempts):
    key=f"{p['order_key']}:{code}"
    con.execute('INSERT OR REPLACE INTO failed_jobs(job_key,order_key,source,external_order_id,error_code,error_message,payload,attempts) VALUES(?,?,?,?,?,?,?,?)', (key,p['order_key'],p['source'],p['external_order_id'],code,message,json.dumps(p['raw_payload'],ensure_ascii=False),attempts))

def api_post(path, body, timeout=.55):
    req=urllib.request.Request(API+path, data=json.dumps(body).encode(), headers={'content-type':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw=e.read().decode() if e.fp else '{}'
        return e.code, json.loads(raw or '{}')
    except Exception as e:
        return 599, {'ok':False,'code':'CLIENT_TIMEOUT','detail':type(e).__name__}

def reserve_with_retry(p):
    mode=p.get('integration_mode','normal')
    last=(599,{})
    max_attempts = 1 if mode == 'permanent_400' else 3
    for attempt in range(1,max_attempts+1):
        last=api_post('/api/warehouse/reserve', {'order_key':p['order_key'],'sku':p['sku'],'quantity':p['quantity'],'mode':mode})
        if 200 <= last[0] < 300:
            return True, attempt, last
        if 400 <= last[0] < 500:
            return False, attempt, last
        if attempt < max_attempts:
            time.sleep(.03 * (2 ** (attempt-1)))
    return False, max_attempts, last

def process(con, raw):
    p=canonicalize(raw)
    event_key=p['order_key']
    row=con.execute('SELECT delivery_count FROM processed_events WHERE event_key=?',(event_key,)).fetchone()
    if row:
        con.execute('UPDATE processed_events SET delivery_count=delivery_count+1 WHERE event_key=?',(event_key,))
    else:
        con.execute('INSERT INTO processed_events VALUES(?,?,1)',(event_key,p['order_key']))

    if con.execute('SELECT 1 FROM orders WHERE order_key=?',(p['order_key'],)).fetchone():
        exc(con,p,'DUPLICATE_ORDER','Order already processed; duplicate delivery ignored')
        con.commit(); return 'duplicate'
    c=classify(p)
    if c:
        exc(con,p,*c); con.commit(); return c[0]
    if p['sku'] not in SKU:
        exc(con,p,'UNKNOWN_SKU','SKU does not exist in SKU master'); con.commit(); return 'UNKNOWN_SKU'
    avail=con.execute('SELECT available_quantity FROM inventory WHERE sku=?',(p['sku'],)).fetchone()[0]
    if avail < p['quantity']:
        exc(con,p,'INSUFFICIENT_STOCK','Warehouse stock is lower than requested quantity'); con.commit(); return 'INSUFFICIENT_STOCK'

    ok, attempts, detail=reserve_with_retry(p)
    if not ok:
        code='API_PERMANENT_FAILURE' if 400 <= detail[0] < 500 else 'API_TEMPORARY_FAILURE'
        failed(con,p,code,f'Warehouse reservation failed after {attempts} attempt(s)',attempts)
        exc(con,p,code,'Warehouse reservation did not recover')
        con.commit(); return code

    # Local transaction mirrors the PostgreSQL row-lock + insert function.
    try:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT 1 FROM orders WHERE order_key=?',(p['order_key'],)).fetchone():
            con.rollback(); exc(con,p,'DUPLICATE_ORDER','Concurrent duplicate ignored'); con.commit(); return 'duplicate'
        avail=con.execute('SELECT available_quantity FROM inventory WHERE sku=?',(p['sku'],)).fetchone()[0]
        if avail < p['quantity']:
            con.rollback(); exc(con,p,'INSUFFICIENT_STOCK','Stock changed before commit'); con.commit(); return 'INSUFFICIENT_STOCK'
        con.execute('UPDATE inventory SET available_quantity=available_quantity-?, reserved_quantity=reserved_quantity+? WHERE sku=?',(p['quantity'],p['quantity'],p['sku']))
        con.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)',(p['order_key'],p['source'],p['external_order_id'],p['customer_email'],p['sku'],p['quantity'],p['unit_price'],p['currency'],p['order_status'],1 if attempts>1 else 0,json.dumps(p['raw_payload'],ensure_ascii=False)))
        con.commit()
    except:
        con.rollback(); raise

    nstatus,_=api_post('/api/notify', {'event':'order_processed','order_key':p['order_key'],'mode':p.get('notification_mode','normal')})
    if nstatus >= 400:
        exc(con,p,'NOTIFICATION_FAILURE','Order was stored but downstream notification failed')
        con.commit()
    return 'processed_recovered' if attempts>1 else 'processed'

def summary(con):
    codes=dict(con.execute('SELECT error_code,COUNT(*) FROM exceptions GROUP BY error_code').fetchall())
    return {
        'orders_processed': con.execute('SELECT COUNT(*) FROM orders').fetchone()[0],
        'successful': con.execute('SELECT COUNT(*) FROM orders').fetchone()[0],
        'cancelled': codes.get('ORDER_CANCELLED',0),
        'exceptions': con.execute('SELECT COUNT(*) FROM exceptions').fetchone()[0],
        'duplicates_ignored': codes.get('DUPLICATE_ORDER',0),
        'retry_recovered': con.execute('SELECT COUNT(*) FROM orders WHERE retry_recovered=1').fetchone()[0],
        'permanent_failures': con.execute("SELECT COUNT(*) FROM failed_jobs WHERE status='dead_letter'").fetchone()[0],
        'failed_jobs': con.execute('SELECT COUNT(*) FROM failed_jobs').fetchone()[0],
        'exception_codes': codes,
    }

def main():
    try: api_post('/api/reset', {})
    except: pass
    con=reset_db()
    rows=load_rows()
    assert len(rows)==42, len(rows)
    results=[process(con,r) for r in rows]

    # Test A normal order
    assert con.execute("SELECT COUNT(*) FROM orders WHERE order_key='shopify:SHOP-10001'").fetchone()[0] == 1
    # Test B duplicate webhook / CSV
    assert con.execute("SELECT COUNT(*) FROM orders WHERE order_key='shopify:SHOP-10001'").fetchone()[0] == 1
    # Test C unknown SKU
    assert con.execute("SELECT COUNT(*) FROM exceptions WHERE error_code='UNKNOWN_SKU'").fetchone()[0] >= 1
    # Test D insufficient stock + non-negative inventory
    assert con.execute("SELECT COUNT(*) FROM exceptions WHERE error_code='INSUFFICIENT_STOCK'").fetchone()[0] >= 1
    assert con.execute('SELECT MIN(available_quantity) FROM inventory').fetchone()[0] >= 0
    # Test E temporary failure recovers on third attempt
    assert con.execute("SELECT retry_recovered FROM orders WHERE order_key='shopify:SHOP-RETRY-RECOVER'").fetchone()[0] == 1
    # Test F permanent/fully exhausted integration failures are dead-lettered
    assert con.execute('SELECT COUNT(*) FROM failed_jobs').fetchone()[0] >= 2
    # Test G cancelled orders not stored
    assert con.execute("SELECT COUNT(*) FROM orders WHERE external_order_id LIKE '%CANCEL%'").fetchone()[0] == 0
    # downstream failure after DB write
    assert con.execute("SELECT COUNT(*) FROM orders WHERE order_key='shopify:SHOP-NOTIFY-FAIL'").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM exceptions WHERE order_key='shopify:SHOP-NOTIFY-FAIL' AND error_code='NOTIFICATION_FAILURE'").fetchone()[0] == 1

    # Test H re-run safety in a cloned database so first-run summary remains stable.
    clone=sqlite3.connect(':memory:', isolation_level=None); con.backup(clone)
    inv_before=clone.execute('SELECT sku,available_quantity,reserved_quantity FROM inventory ORDER BY sku').fetchall()
    orders_before=clone.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    api_post('/api/reset', {})
    for r in rows: process(clone,r)
    assert clone.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == orders_before
    assert clone.execute('SELECT sku,available_quantity,reserved_quantity FROM inventory ORDER BY sku').fetchall() == inv_before

    s=summary(con)
    # Test I summary values are queried from the database itself.
    assert s['orders_processed'] == con.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    assert s['exceptions'] == con.execute('SELECT COUNT(*) FROM exceptions').fetchone()[0]

    report={'fixture_rows':len(rows),'tests':{k:'PASS' for k in list('ABCDEFGHI')},'summary':s,'result_counts':{x:results.count(x) for x in sorted(set(results))},'database':'SQLite contract harness mirroring db/schema.sql; PostgreSQL runtime is the deployment target'}
    (GEN/'summary.json').write_text(json.dumps(s,indent=2,ensure_ascii=False),encoding='utf-8')
    (GEN/'smoke-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__': main()
