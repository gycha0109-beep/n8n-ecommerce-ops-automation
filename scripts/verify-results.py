#!/usr/bin/env python3
from pathlib import Path
import json, sqlite3, sys
BASE=Path(__file__).resolve().parents[1]
report=json.loads((BASE/'generated/smoke-report.json').read_text(encoding='utf-8'))
if not all(v=='PASS' for v in report['tests'].values()):
    raise SystemExit('smoke report contains failures')
con=sqlite3.connect(BASE/'generated/smoke.db')
s=report['summary']
assert s['orders_processed']==con.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
assert s['exceptions']==con.execute('SELECT COUNT(*) FROM exceptions').fetchone()[0]
assert con.execute('SELECT MIN(available_quantity) FROM inventory').fetchone()[0] >= 0
print('verify-results: PASS')
