import http, { IncomingMessage, ServerResponse } from 'node:http';

const port = Number(process.env.PORT ?? 3000);
const attempts = new Map<string, number>();

function json(res: ServerResponse, status: number, body: unknown) {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(body));
}

async function readJson(req: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`);

  if (req.method === 'GET' && url.pathname === '/health') {
    return json(res, 200, { ok: true, service: 'ecommerce-ops-mock-api' });
  }

  if (req.method === 'POST' && url.pathname === '/api/reset') {
    attempts.clear();
    return json(res, 200, { ok: true });
  }

  if (req.method === 'POST' && url.pathname === '/api/warehouse/reserve') {
    const body = await readJson(req);
    const key = String(body.order_key ?? 'missing-order-key');
    const mode = String(body.mode ?? 'normal');
    const attempt = (attempts.get(key) ?? 0) + 1;
    attempts.set(key, attempt);

    if (mode === 'timeout') {
      await new Promise(resolve => setTimeout(resolve, 6000));
      return json(res, 504, { ok: false, attempt, code: 'SIMULATED_TIMEOUT' });
    }
    if (mode === 'always_500') {
      return json(res, 500, { ok: false, attempt, code: 'SIMULATED_500' });
    }
    if (mode === 'fail_twice_then_success' && attempt <= 2) {
      return json(res, 500, { ok: false, attempt, code: 'SIMULATED_TEMPORARY_FAILURE' });
    }
    if (mode === 'permanent_400') {
      return json(res, 400, { ok: false, attempt, code: 'SIMULATED_PERMANENT_FAILURE' });
    }

    return json(res, 200, { ok: true, attempt, reservation_id: `RSV-${key.replace(/[^A-Za-z0-9]/g, '-').slice(0, 48)}` });
  }

  if (req.method === 'POST' && url.pathname === '/api/notify') {
    const body = await readJson(req);
    if (body.mode === 'fail_notification') {
      return json(res, 500, { ok: false, code: 'SIMULATED_NOTIFICATION_FAILURE' });
    }
    return json(res, 200, { ok: true, delivered: true, received: body });
  }

  json(res, 404, { ok: false, error: 'not_found' });
});

server.listen(port, '0.0.0.0', () => {
  console.log(`mock-api listening on ${port}`);
});
