#!/usr/bin/env python3
from pathlib import Path
import json, uuid
BASE=Path(__file__).resolve().parents[1]
WF=BASE/'workflows'; WF.mkdir(exist_ok=True)

def uid(name): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'n8n-ecommerce-ops:'+name))
def node(name, typ, ver, x,y, params, **extra):
    d={'parameters':params,'id':uid(name),'name':name,'type':typ,'typeVersion':ver,'position':[x,y]}; d.update(extra); return d

def write(name,data): (WF/name).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')

def if_params(left,right):
    return {'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':uid(left+right),'leftValue':left,'rightValue':right,'operator':{'type':'string','operation':'equals'}}],'combinator':'and'},'options':{}}

normalize_js=r'''const input = $json.body ?? $json;
const source = String(input.source ?? '').toLowerCase();
const p = input.payload ?? input;
let c = { source, raw_payload: p };
if (source === 'shopify') {
  const li = (p.line_items ?? [])[0] ?? {};
  Object.assign(c, { external_order_id:p.id, customer_email:p.email, sku:li.sku, quantity:li.quantity, unit_price:li.price, currency:p.currency, order_status:p.financial_status, created_at:p.created_at, integration_mode:p.integration_mode ?? 'normal', notification_mode:p.notification_mode ?? 'normal' });
} else if (source === 'amazon') {
  Object.assign(c, { external_order_id:p.amazon_order_id, customer_email:p.buyer_email, sku:p.seller_sku, quantity:p.item_quantity, unit_price:p.item_price, currency:p.currency_code, order_status:p.order_status, created_at:p.purchase_date, integration_mode:p.integration_mode ?? 'normal', notification_mode:p.notification_mode ?? 'normal' });
} else if (source === 'marketplace') {
  Object.assign(c, { external_order_id:p.order_no, customer_email:p.email, sku:p.product_sku, quantity:p.qty, unit_price:p.price, currency:p.currency, order_status:p.status, created_at:p.created, integration_mode:p.integration_mode ?? 'normal', notification_mode:p.notification_mode ?? 'normal' });
} else {
  c = { ...c, ...p };
}
c.external_order_id = String(c.external_order_id ?? '').trim();
c.customer_email = String(c.customer_email ?? '').trim().toLowerCase();
c.sku = String(c.sku ?? '').trim();
c.currency = String(c.currency ?? '').trim().toUpperCase();
c.order_status = String(c.order_status ?? '').trim().toLowerCase();
c.order_key = `${c.source}:${c.external_order_id}`;
c.quantity = Number(c.quantity);
c.unit_price = Number(c.unit_price);
c.payload_b64 = Buffer.from(JSON.stringify(c), 'utf8').toString('base64');
return [{json:c}];'''

validate_js=r'''const p = $json;
const emailOk = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(p.customer_email);
let error_code = null, error_message = null;
if (['cancelled','canceled'].includes(p.order_status)) { error_code='ORDER_CANCELLED'; error_message='Cancelled orders are excluded from normal processing'; }
else if (!p.external_order_id || !p.customer_email || !p.sku || !p.created_at) { error_code='MISSING_FIELD'; error_message='Required order field is missing'; }
else if (!emailOk) { error_code='MALFORMED_EMAIL'; error_message='Customer email is malformed'; }
else if (!Number.isFinite(p.quantity)) { error_code='MALFORMED_INPUT'; error_message='Quantity is not numeric'; }
else if (p.quantity <= 0) { error_code='INVALID_QUANTITY'; error_message='Quantity must be greater than zero'; }
else if (!Number.isFinite(p.unit_price) || p.unit_price < 0) { error_code='MALFORMED_INPUT'; error_message='Unit price is invalid'; }
else if (!['KRW','USD','JPY','EUR'].includes(p.currency)) { error_code='INVALID_CURRENCY'; error_message='Unsupported currency'; }
return [{json:{...p, validation_status:error_code ? 'invalid' : 'valid', error_code, error_message}}];'''

nodes=[]
nodes += [node('Order Intake Webhook','n8n-nodes-base.webhook',2.1,-1320,0,{'httpMethod':'POST','path':'ecommerce-order-intake','responseMode':'responseNode','options':{}},webhookId=uid('order-intake-webhook'))]
nodes += [node('Normalize Incoming Order','n8n-nodes-base.code',2,-1100,0,{'jsCode':normalize_js})]
nodes += [node('Validate Canonical Order','n8n-nodes-base.code',2,-880,0,{'jsCode':validate_js})]
nodes += [node('Validation Passed?','n8n-nodes-base.if',2.2,-650,0,if_params('={{ $json.validation_status }}','valid'))]
nodes += [node('Record Validation Exception','n8n-nodes-base.postgres',2.5,-400,220,{'operation':'executeQuery','query':'SELECT record_exception_b64($1, $2, $3);','options':{'queryReplacement':'={{ $json.payload_b64 }},={{ $json.error_code }},={{ $json.error_message }}'}})]
nodes += [node('Check Idempotency','n8n-nodes-base.postgres',2.5,-400,-80,{'operation':'executeQuery','query':"INSERT INTO processed_events(event_key, order_key) VALUES($1,$1) ON CONFLICT(event_key) DO UPDATE SET last_seen_at=now(), delivery_count=processed_events.delivery_count+1; SELECT EXISTS(SELECT 1 FROM orders WHERE order_key = $1) AS is_duplicate;",'options':{'queryReplacement':'={{ $json.order_key }}'}})]
nodes += [node('Attach Duplicate Result','n8n-nodes-base.code',2,-180,-80,{'jsCode':"const p=$('Validate Canonical Order').first().json; return [{json:{...p,is_duplicate:Boolean($json.is_duplicate)}}];"})]
nodes += [node('Duplicate?','n8n-nodes-base.if',2.2,40,-80,{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':uid('dupcond'),'leftValue':'={{ $json.is_duplicate }}','rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}})]
nodes += [node('Record Duplicate','n8n-nodes-base.postgres',2.5,260,100,{'operation':'executeQuery','query':"SELECT record_exception_b64($1, 'DUPLICATE_ORDER', 'Order already processed; duplicate delivery ignored');",'options':{'queryReplacement':'={{ $json.payload_b64 }}'}})]
nodes += [node('Load SKU Inventory','n8n-nodes-base.postgres',2.5,260,-180,{'operation':'executeQuery','query':'SELECT $1::text AS sku, $2::integer AS requested_quantity, EXISTS(SELECT 1 FROM sku_master WHERE sku=$1 AND active) AS sku_exists, COALESCE((SELECT available_quantity FROM inventory WHERE sku=$1),0) AS available_quantity;','options':{'queryReplacement':'={{ $json.sku }},={{ $json.quantity }}'}})]
nodes += [node('Classify Inventory','n8n-nodes-base.code',2,480,-180,{'jsCode':"const p=$('Validate Canonical Order').first().json; const exists=Boolean($json.sku_exists); const available=Number($json.available_quantity??0); let error_code=null,error_message=null; if(!exists){error_code='UNKNOWN_SKU';error_message='SKU does not exist in SKU master';} else if(available < p.quantity){error_code='INSUFFICIENT_STOCK';error_message='Warehouse stock is lower than requested quantity';} return [{json:{...p,inventory_status:error_code?'invalid':'valid',available_quantity:available,error_code,error_message}}];"})]
nodes += [node('Inventory Valid?','n8n-nodes-base.if',2.2,700,-180,if_params('={{ $json.inventory_status }}','valid'))]
nodes += [node('Record Inventory Exception','n8n-nodes-base.postgres',2.5,920,40,{'operation':'executeQuery','query':'SELECT record_exception_b64($1, $2, $3);','options':{'queryReplacement':'={{ $json.payload_b64 }},={{ $json.error_code }},={{ $json.error_message }}'}})]

def http_attempt(name,x,y):
    return node(name,'n8n-nodes-base.httpRequest',4.3,x,y,{'method':'POST','url':'http://mock-api:3000/api/warehouse/reserve','sendBody':True,'contentType':'raw','rawContentType':'application/json','body':'={{ JSON.stringify({order_key: $json.order_key, sku: $json.sku, quantity: $json.quantity, mode: $json.integration_mode}) }}','options':{'response':{'response':{'fullResponse':True,'neverError':True}},'timeout':1200}})

def eval_attempt(name,x,y,attempt):
    return node(name,'n8n-nodes-base.code',2,x,y,{'jsCode':f"const p=$('Classify Inventory').first().json; const status=Number($json.statusCode ?? 599); return [{{json:{{...p,http_status:status,attempt:{attempt},api_ok:status>=200&&status<300,api_permanent:status>=400&&status<500}}}}];"})

nodes += [http_attempt('Warehouse Reserve Attempt 1',920,-260), eval_attempt('Evaluate Attempt 1',1140,-260,1)]
nodes += [node('Attempt 1 Success?','n8n-nodes-base.if',2.2,1360,-260,{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':uid('a1'),'leftValue':'={{ $json.api_ok }}','rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}})]
nodes += [node('Attempt 1 Permanent?','n8n-nodes-base.if',2.2,1570,-80,{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':uid('a1p'),'leftValue':'={{ $json.api_permanent }}','rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}})]
nodes += [node('Wait 1 Second','n8n-nodes-base.wait',1.1,1790,-140,{'amount':1,'unit':'seconds'},webhookId=uid('wait1'))]
nodes += [http_attempt('Warehouse Reserve Attempt 2',2010,-140), eval_attempt('Evaluate Attempt 2',2230,-140,2)]
nodes += [node('Attempt 2 Success?','n8n-nodes-base.if',2.2,2450,-140,{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':uid('a2'),'leftValue':'={{ $json.api_ok }}','rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}})]
nodes += [node('Wait 2 Seconds','n8n-nodes-base.wait',1.1,2670,20,{'amount':2,'unit':'seconds'},webhookId=uid('wait2'))]
nodes += [http_attempt('Warehouse Reserve Attempt 3',2890,20), eval_attempt('Evaluate Attempt 3',3110,20,3)]
nodes += [node('Attempt 3 Success?','n8n-nodes-base.if',2.2,3330,20,{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':uid('a3'),'leftValue':'={{ $json.api_ok }}','rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}})]
nodes += [node('Wait 4 Seconds','n8n-nodes-base.wait',1.1,3550,180,{'amount':4,'unit':'seconds'},webhookId=uid('wait4'))]
nodes += [node('Dead Letter Failure','n8n-nodes-base.postgres',2.5,3770,180,{'operation':'executeQuery','query':"SELECT record_failed_job_b64($1, 'API_TEMPORARY_FAILURE', 'Warehouse reservation failed after all retry attempts', $2::integer); SELECT record_exception_b64($1, 'API_TEMPORARY_FAILURE', 'Warehouse reservation did not recover');",'options':{'queryReplacement':'={{ $json.payload_b64 }},={{ $json.attempt }}','queryBatching':'transaction'}})]
nodes += [node('Permanent Failure','n8n-nodes-base.postgres',2.5,1790,160,{'operation':'executeQuery','query':"SELECT record_failed_job_b64($1, 'API_PERMANENT_FAILURE', 'Warehouse API returned a non-retryable 4xx response', 1); SELECT record_exception_b64($1, 'API_PERMANENT_FAILURE', 'Warehouse reservation rejected permanently');",'options':{'queryReplacement':'={{ $json.payload_b64 }}','queryBatching':'transaction'}})]
nodes += [node('Mark First Attempt Success','n8n-nodes-base.code',2,1570,-420,{'jsCode':"const p=$('Classify Inventory').first().json; return [{json:{...p,retry_recovered:false}}];"})]
nodes += [node('Mark Retry Recovered 2','n8n-nodes-base.code',2,2670,-260,{'jsCode':"const p=$('Classify Inventory').first().json; return [{json:{...p,retry_recovered:true}}];"})]
nodes += [node('Mark Retry Recovered 3','n8n-nodes-base.code',2,3550,-60,{'jsCode':"const p=$('Classify Inventory').first().json; return [{json:{...p,retry_recovered:true}}];"})]
nodes += [node('Commit Order Transaction','n8n-nodes-base.postgres',2.5,3990,-260,{'operation':'executeQuery','query':'SELECT reserve_inventory_and_insert_order_b64($1, $2::boolean) AS result, $2::boolean AS retry_recovered;','options':{'queryReplacement':'={{ $json.payload_b64 }},={{ $json.retry_recovered }}','queryBatching':'transaction'}})]
nodes += [node('Attach Commit Result','n8n-nodes-base.code',2,4210,-260,{'jsCode':"const p=$('Classify Inventory').first().json; return [{json:{...p,db_result:$json.result,retry_recovered:Boolean($json.retry_recovered)}}];"})]
nodes += [node('Notify Processed','n8n-nodes-base.httpRequest',4.3,4430,-260,{'method':'POST','url':'http://mock-api:3000/api/notify','sendBody':True,'contentType':'raw','rawContentType':'application/json','body':'={{ JSON.stringify({event:"order_processed",order_key:$json.order_key,mode:$json.notification_mode}) }}','options':{'response':{'response':{'fullResponse':True,'neverError':True}},'timeout':2000}})]
nodes += [node('Notification OK?','n8n-nodes-base.if',2.2,4650,-260,{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':uid('notifyok'),'leftValue':'={{ $json.statusCode >= 200 && $json.statusCode < 300 }}','rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}})]
nodes += [node('Record Notification Failure','n8n-nodes-base.postgres',2.5,4870,-80,{'operation':'executeQuery','query':"SELECT record_exception_b64($1, 'NOTIFICATION_FAILURE', 'Order was stored but downstream notification failed');",'options':{'queryReplacement':"={{ $('Classify Inventory').first().json.payload_b64 }}"}})]
nodes += [node('Respond Success','n8n-nodes-base.respondToWebhook',1.4,4870,-360,{'respondWith':'json','responseBody':'={{ {ok:true,order_key:$("Classify Inventory").first().json.order_key,status:"processed"} }}','options':{'responseCode':200}})]
nodes += [node('Respond Exception','n8n-nodes-base.respondToWebhook',1.4,620,300,{'respondWith':'json','responseBody':'={{ {ok:false,order_key:$("Validate Canonical Order").first().json.order_key,status:"exception"} }}','options':{'responseCode':202}})]
nodes += [node('Respond Failure','n8n-nodes-base.respondToWebhook',1.4,3990,180,{'respondWith':'json','responseBody':'={{ {ok:false,order_key:$("Classify Inventory").first().json.order_key,status:"dead_letter"} }}','options':{'responseCode':202}})]

C={
'Order Intake Webhook':{'main':[[{'node':'Normalize Incoming Order','type':'main','index':0}]]},
'Normalize Incoming Order':{'main':[[{'node':'Validate Canonical Order','type':'main','index':0}]]},
'Validate Canonical Order':{'main':[[{'node':'Validation Passed?','type':'main','index':0}]]},
'Validation Passed?':{'main':[[{'node':'Check Idempotency','type':'main','index':0}],[{'node':'Record Validation Exception','type':'main','index':0}]]},
'Record Validation Exception':{'main':[[{'node':'Respond Exception','type':'main','index':0}]]},
'Check Idempotency':{'main':[[{'node':'Attach Duplicate Result','type':'main','index':0}]]},
'Attach Duplicate Result':{'main':[[{'node':'Duplicate?','type':'main','index':0}]]},
'Duplicate?':{'main':[[{'node':'Record Duplicate','type':'main','index':0}],[{'node':'Load SKU Inventory','type':'main','index':0}]]},
'Record Duplicate':{'main':[[{'node':'Respond Exception','type':'main','index':0}]]},
'Load SKU Inventory':{'main':[[{'node':'Classify Inventory','type':'main','index':0}]]},
'Classify Inventory':{'main':[[{'node':'Inventory Valid?','type':'main','index':0}]]},
'Inventory Valid?':{'main':[[{'node':'Warehouse Reserve Attempt 1','type':'main','index':0}],[{'node':'Record Inventory Exception','type':'main','index':0}]]},
'Record Inventory Exception':{'main':[[{'node':'Respond Exception','type':'main','index':0}]]},
'Warehouse Reserve Attempt 1':{'main':[[{'node':'Evaluate Attempt 1','type':'main','index':0}]]},
'Evaluate Attempt 1':{'main':[[{'node':'Attempt 1 Success?','type':'main','index':0}]]},
'Attempt 1 Success?':{'main':[[{'node':'Mark First Attempt Success','type':'main','index':0}],[{'node':'Attempt 1 Permanent?','type':'main','index':0}]]},
'Attempt 1 Permanent?':{'main':[[{'node':'Permanent Failure','type':'main','index':0}],[{'node':'Wait 1 Second','type':'main','index':0}]]},
'Wait 1 Second':{'main':[[{'node':'Warehouse Reserve Attempt 2','type':'main','index':0}]]},
'Warehouse Reserve Attempt 2':{'main':[[{'node':'Evaluate Attempt 2','type':'main','index':0}]]},
'Evaluate Attempt 2':{'main':[[{'node':'Attempt 2 Success?','type':'main','index':0}]]},
'Attempt 2 Success?':{'main':[[{'node':'Mark Retry Recovered 2','type':'main','index':0}],[{'node':'Wait 2 Seconds','type':'main','index':0}]]},
'Wait 2 Seconds':{'main':[[{'node':'Warehouse Reserve Attempt 3','type':'main','index':0}]]},
'Warehouse Reserve Attempt 3':{'main':[[{'node':'Evaluate Attempt 3','type':'main','index':0}]]},
'Evaluate Attempt 3':{'main':[[{'node':'Attempt 3 Success?','type':'main','index':0}]]},
'Attempt 3 Success?':{'main':[[{'node':'Mark Retry Recovered 3','type':'main','index':0}],[{'node':'Wait 4 Seconds','type':'main','index':0}]]},
'Wait 4 Seconds':{'main':[[{'node':'Dead Letter Failure','type':'main','index':0}]]},
'Permanent Failure':{'main':[[{'node':'Respond Failure','type':'main','index':0}]]},
'Dead Letter Failure':{'main':[[{'node':'Respond Failure','type':'main','index':0}]]},
'Mark First Attempt Success':{'main':[[{'node':'Commit Order Transaction','type':'main','index':0}]]},
'Mark Retry Recovered 2':{'main':[[{'node':'Commit Order Transaction','type':'main','index':0}]]},
'Mark Retry Recovered 3':{'main':[[{'node':'Commit Order Transaction','type':'main','index':0}]]},
'Commit Order Transaction':{'main':[[{'node':'Attach Commit Result','type':'main','index':0}]]},
'Attach Commit Result':{'main':[[{'node':'Notify Processed','type':'main','index':0}]]},
'Notify Processed':{'main':[[{'node':'Notification OK?','type':'main','index':0}]]},
'Notification OK?':{'main':[[{'node':'Respond Success','type':'main','index':0}],[{'node':'Record Notification Failure','type':'main','index':0}]]},
'Record Notification Failure':{'main':[[{'node':'Respond Success','type':'main','index':0}]]},
}
main={'id':'3e7b03e1-93af-4a51-8a16-819aff10b352','name':'E-commerce Order Intake - Reliability Demo','nodes':nodes,'pinData':{},'connections':C,'active':False,'settings':{'executionOrder':'v1','errorWorkflow':''},'versionId':uid('main-version'),'meta':{'templateCredsSetupCompleted':False},'tags':[]}
write('ecommerce-order-intake.json',main)

# Global error handler for unexpected n8n execution failures.
errnodes=[
 node('Error Trigger','n8n-nodes-base.errorTrigger',1,-540,0,{}),
 node('Build Failure Envelope','n8n-nodes-base.code',2,-300,0,{'jsCode':"const e=$json; const order_key=e.execution?.data?.resultData?.lastNodeExecuted ?? 'workflow'; const payload={source:'n8n',external_order_id:String(e.execution?.id??'unknown'),order_key:`n8n:${e.execution?.id??'unknown'}`,raw_payload:e}; payload.payload_b64=Buffer.from(JSON.stringify(payload),'utf8').toString('base64'); return [{json:payload}];"}),
 node('Store Unexpected Failure','n8n-nodes-base.postgres',2.5,-40,0,{'operation':'executeQuery','query':"SELECT record_failed_job_b64($1, 'WORKFLOW_EXECUTION_FAILURE', 'Unhandled n8n workflow execution failure', 1);",'options':{'queryReplacement':'={{ $json.payload_b64 }}'}}),
 node('Alert Operator','n8n-nodes-base.httpRequest',4.3,220,0,{'method':'POST','url':'http://mock-api:3000/api/notify','sendBody':True,'contentType':'raw','rawContentType':'application/json','body':'={{ JSON.stringify({event:"workflow_error",order_key:$json.order_key}) }}','options':{'response':{'response':{'fullResponse':True,'neverError':True}},'timeout':2000}}),
]
errcon={'Error Trigger':{'main':[[{'node':'Build Failure Envelope','type':'main','index':0}]]},'Build Failure Envelope':{'main':[[{'node':'Store Unexpected Failure','type':'main','index':0}]]},'Store Unexpected Failure':{'main':[[{'node':'Alert Operator','type':'main','index':0}]]}}
write('ecommerce-error-handler.json',{'id':'e0f539bd-1abc-405c-a4f8-7e8861ac83bc','name':'E-commerce Ops - Global Error Handler','nodes':errnodes,'pinData':{},'connections':errcon,'active':False,'settings':{'executionOrder':'v1'},'versionId':uid('err-version'),'meta':{'templateCredsSetupCompleted':False},'tags':[]})

# Daily summary calculated from DB, never hard-coded.
sumnodes=[
 node('Daily 09:00','n8n-nodes-base.scheduleTrigger',1.2,-560,0,{'rule':{'interval':[{'field':'cronExpression','expression':'0 9 * * *'}]}}),
 node('Query Daily Summary','n8n-nodes-base.postgres',2.5,-320,0,{'operation':'executeQuery','query':"SELECT (SELECT count(*) FROM orders WHERE processed_at >= date_trunc('day', now()))::int AS successful, (SELECT count(*) FROM exceptions WHERE created_at >= date_trunc('day', now()))::int AS exceptions, (SELECT count(*) FROM exceptions WHERE created_at >= date_trunc('day', now()) AND error_code='ORDER_CANCELLED')::int AS cancelled, (SELECT count(*) FROM exceptions WHERE created_at >= date_trunc('day', now()) AND error_code='DUPLICATE_ORDER')::int AS duplicates_ignored, (SELECT count(*) FROM orders WHERE processed_at >= date_trunc('day', now()) AND retry_recovered)::int AS retry_recovered, (SELECT count(*) FROM failed_jobs WHERE created_at >= date_trunc('day', now()) AND status='dead_letter')::int AS permanent_failures;",'options':{}}),
 node('Build Summary Message','n8n-nodes-base.code',2,-80,0,{'jsCode':"return [{json:{event:'daily_summary',date:new Date().toISOString().slice(0,10),...$json}}];"}),
 node('Send Summary','n8n-nodes-base.httpRequest',4.3,180,0,{'method':'POST','url':'http://mock-api:3000/api/notify','sendBody':True,'contentType':'raw','rawContentType':'application/json','body':'={{ JSON.stringify($json) }}','options':{'response':{'response':{'fullResponse':True,'neverError':True}},'timeout':2000}})
]
sumcon={'Daily 09:00':{'main':[[{'node':'Query Daily Summary','type':'main','index':0}]]},'Query Daily Summary':{'main':[[{'node':'Build Summary Message','type':'main','index':0}]]},'Build Summary Message':{'main':[[{'node':'Send Summary','type':'main','index':0}]]}}
write('ecommerce-daily-summary.json',{'id':'83131f1e-3aba-4e04-a3b6-bc1946c30661','name':'E-commerce Daily Summary','nodes':sumnodes,'pinData':{},'connections':sumcon,'active':False,'settings':{'executionOrder':'v1','timezone':'Asia/Seoul'},'versionId':uid('sum-version'),'meta':{'templateCredsSetupCompleted':False},'tags':[]})
print('generated workflows')
