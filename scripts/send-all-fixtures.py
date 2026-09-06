#!/usr/bin/env python3
from pathlib import Path
import csv,json,sys,urllib.request
BASE=Path(__file__).resolve().parents[1]
URL=sys.argv[1] if len(sys.argv)>1 else 'http://localhost:5678/webhook/ecommerce-order-intake'
items=[]
for p in json.loads((BASE/'fixtures/shopify_orders.json').read_text(encoding='utf-8')): items.append({'source':'shopify','payload':p})
with (BASE/'fixtures/amazon_orders.csv').open(encoding='utf-8-sig',newline='') as f:
    for p in csv.DictReader(f): items.append({'source':'amazon','payload':p})
with (BASE/'fixtures/marketplace_orders.csv').open(encoding='utf-8-sig',newline='') as f:
    for p in csv.DictReader(f): items.append({'source':'marketplace','payload':p})
for i,item in enumerate(items,1):
    req=urllib.request.Request(URL,data=json.dumps(item).encode(),headers={'content-type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=20) as r: print(i,r.status,r.read().decode())
    except Exception as e: print(i,'ERROR',e)
