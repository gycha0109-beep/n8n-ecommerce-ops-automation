import fs from 'node:fs';
import path from 'node:path';

const base = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const dir = path.join(base, 'workflows');
const expected = [
  ['ecommerce-order-intake.json', 'E-commerce Order Intake - Reliability Demo', '3e7b03e1-93af-4a51-8a16-819aff10b352'],
  ['ecommerce-error-handler.json', 'E-commerce Ops - Global Error Handler', 'e0f539bd-1abc-405c-a4f8-7e8861ac83bc'],
  ['ecommerce-daily-summary.json', 'E-commerce Daily Summary', '83131f1e-3aba-4e04-a3b6-bc1946c30661'],
];
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const loaded = expected.map(([file, name, id]) => {
  const raw = fs.readFileSync(path.join(dir, file));
  if (raw.length >= 3 && raw[0] === 0xef && raw[1] === 0xbb && raw[2] === 0xbf) {
    throw new Error(`${file}: UTF-8 BOM is not allowed`);
  }
  const text = raw.toString('utf8');
  const workflow = JSON.parse(text);
  if (workflow.name !== name) throw new Error(`${file}: unexpected workflow name ${workflow.name}`);
  if (workflow.id !== id || !uuid.test(workflow.id)) throw new Error(`${file}: invalid workflow id`);
  if (!uuid.test(workflow.versionId ?? '')) throw new Error(`${file}: invalid versionId`);
  if (/\.item(?:\.|\b)/.test(text)) throw new Error(`${file}: paired-item .item reference detected`);
  if (/\$env\b/.test(text)) throw new Error(`${file}: blocked $env expression detected`);
  if (/"name"\s*:\s*"[^"]*\?\?[^"]*"/.test(text)) throw new Error(`${file}: broken ?? workflow/node name detected`);
  return [file, workflow];
});

for (const [file, workflow] of loaded) {
  if (!Array.isArray(workflow.nodes) || !workflow.connections) throw new Error(`${file}: invalid workflow export shape`);
  const names = new Set(workflow.nodes.map((n) => n.name));
  for (const [src, ports] of Object.entries(workflow.connections)) {
    if (!names.has(src)) throw new Error(`${file}: missing source node ${src}`);
    for (const branch of ports.main ?? []) {
      for (const connection of branch ?? []) {
        if (!names.has(connection.node)) throw new Error(`${file}: missing target node ${connection.node}`);
      }
    }
  }
  const serialized = JSON.stringify(workflow);
  if (/sk-[A-Za-z0-9_-]{12,}/.test(serialized) || /password\s*[:=]\s*[^}$]/i.test(serialized)) {
    throw new Error(`${file}: possible embedded secret`);
  }
}

const main = loaded[0][1];
const types = main.nodes.map((n) => n.type);
for (const type of ['n8n-nodes-base.webhook', 'n8n-nodes-base.code', 'n8n-nodes-base.postgres', 'n8n-nodes-base.httpRequest', 'n8n-nodes-base.wait']) {
  if (!types.includes(type)) throw new Error(`main: missing ${type}`);
}
for (const [name, amount] of [['Wait 1 Second', 1], ['Wait 2 Seconds', 2], ['Wait 4 Seconds', 4]]) {
  const node = main.nodes.find((n) => n.name === name);
  if (!node || node.parameters.amount !== amount) throw new Error(`main: bad backoff ${name}`);
}
for (const name of ['Record Duplicate', 'Record Inventory Exception', 'Dead Letter Failure', 'Commit Order Transaction', 'Record Notification Failure']) {
  if (!main.nodes.some((node) => node.name === name)) throw new Error(`main: missing reliability node ${name}`);
}
for (const node of main.nodes.filter((node) => node.type === 'n8n-nodes-base.httpRequest')) {
  if (!String(node.parameters.url ?? '').startsWith('http://mock-api:3000/')) throw new Error(`main: unexpected mock URL in ${node.name}`);
}
const errorWorkflow = loaded[1][1];
for (const node of errorWorkflow.nodes.filter((node) => node.type === 'n8n-nodes-base.httpRequest')) {
  if (!String(node.parameters.url ?? '').startsWith('http://mock-api:3000/')) throw new Error(`error workflow: unexpected mock URL in ${node.name}`);
}
const summary = loaded[2][1];
if (!summary.nodes.some((node) => node.type === 'n8n-nodes-base.scheduleTrigger')) throw new Error('summary: no schedule trigger');
// Keep a sub-workflow trigger so n8n CLI regression can execute the same DB-derived summary path as the schedule trigger.
const executeTrigger = summary.nodes.find((node) => node.type === 'n8n-nodes-base.executeWorkflowTrigger');
if (!executeTrigger || executeTrigger.typeVersion !== 1.1 || executeTrigger.parameters?.inputSource !== 'passthrough') {
  throw new Error('summary: no CLI-compatible execute workflow trigger');
}
for (const node of summary.nodes.filter((node) => node.type === 'n8n-nodes-base.httpRequest')) {
  if (!String(node.parameters.url ?? '').startsWith('http://mock-api:3000/')) throw new Error(`summary: unexpected mock URL in ${node.name}`);
}
console.log(`verify-workflows: PASS (${main.nodes.length} intake nodes, ${errorWorkflow.nodes.length} error nodes, ${summary.nodes.length} summary nodes)`);
