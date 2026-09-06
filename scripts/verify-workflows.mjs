import fs from 'node:fs';
import path from 'node:path';
const base = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const dir = path.join(base,'workflows');
const files=['ecommerce-order-intake.json','ecommerce-error-handler.json','ecommerce-daily-summary.json'];
const loaded=files.map(f=>[f,JSON.parse(fs.readFileSync(path.join(dir,f),'utf8'))]);
for(const [f,w] of loaded){
  if(!w.name || !Array.isArray(w.nodes) || !w.connections) throw new Error(`${f}: invalid workflow export shape`);
  const names=new Set(w.nodes.map(n=>n.name));
  for(const [src,ports] of Object.entries(w.connections)){
    if(!names.has(src)) throw new Error(`${f}: missing source node ${src}`);
    for(const branch of ports.main ?? []) for(const c of branch ?? []) if(!names.has(c.node)) throw new Error(`${f}: missing target node ${c.node}`);
  }
  const raw=JSON.stringify(w);
  if(/sk-[A-Za-z0-9_-]{12,}/.test(raw) || /password\s*[:=]\s*[^}$]/i.test(raw)) throw new Error(`${f}: possible embedded secret`);
}
const main=loaded[0][1];
const types=main.nodes.map(n=>n.type);
for(const t of ['n8n-nodes-base.webhook','n8n-nodes-base.code','n8n-nodes-base.postgres','n8n-nodes-base.httpRequest','n8n-nodes-base.wait']) if(!types.includes(t)) throw new Error(`main: missing ${t}`);
for(const wait of [['Wait 1 Second',1],['Wait 2 Seconds',2],['Wait 4 Seconds',4]]){
  const n=main.nodes.find(n=>n.name===wait[0]); if(!n || n.parameters.amount!==wait[1]) throw new Error(`main: bad backoff ${wait[0]}`);
}
for(const name of ['Record Duplicate','Record Inventory Exception','Dead Letter Failure','Commit Order Transaction','Record Notification Failure']) if(!main.nodes.some(n=>n.name===name)) throw new Error(`main: missing reliability node ${name}`);
const summary=loaded[2][1];
if(!summary.nodes.some(n=>n.type==='n8n-nodes-base.scheduleTrigger')) throw new Error('summary: no schedule trigger');
console.log(`verify-workflows: PASS (${main.nodes.length} intake nodes, ${loaded[1][1].nodes.length} error nodes, ${summary.nodes.length} summary nodes)`);
