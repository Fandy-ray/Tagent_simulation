import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { preview } from 'vite';

let authEnabled = false;
let notebookMode = 'tagent';
const backend = createServer((request, response) => {
	response.setHeader('content-type', 'application/json');
	if (request.url === '/auth/status') {
		response.end(JSON.stringify({ enabled: authEnabled }));
		return;
	}
	if (request.url === '/auth/me') {
		const role = request.headers.cookie?.includes('admin=ok')
			? 'admin'
			: request.headers.cookie?.includes('student=ok')
				? 'student'
				: null;
		if (!role) {
			response.statusCode = 401;
			response.end('{}');
			return;
		}
		response.end(JSON.stringify({ user: { role }, csrf: 'csrf-1' }));
		return;
	}
	response.end(
		JSON.stringify({
			path: request.url,
			viaFrontend: request.headers['x-tagent-via-frontend'],
			clientIp: request.headers['x-tagent-client-ip']
		})
	);
});
const notebook = createServer((request, response) => {
	response.setHeader('content-type', 'application/json');
	if (request.url === '/api/auth/status') {
		response.end(JSON.stringify({ mode: notebookMode }));
		return;
	}
	response.end(JSON.stringify({ path: request.url, method: request.method }));
});

backend.listen(0, '127.0.0.1');
await once(backend, 'listening');
const backendAddress = backend.address();
assert(backendAddress && typeof backendAddress !== 'string');
process.env.AGENT_API_TARGET = `http://127.0.0.1:${backendAddress.port}`;
notebook.listen(0, '127.0.0.1');
await once(notebook, 'listening');
const notebookAddress = notebook.address();
assert(notebookAddress && typeof notebookAddress !== 'string');
process.env.OPENNOTEBOOK_API_TARGET = `http://127.0.0.1:${notebookAddress.port}`;

let frontend;
try {
	frontend = await preview({ preview: { host: '127.0.0.1', port: 0 } });
	const frontendAddress = frontend.httpServer.address();
	assert(frontendAddress && typeof frontendAddress !== 'string');
	process.env.TAGENT_PUBLIC_ORIGIN = `http://127.0.0.1:${frontendAddress.port}`;
	const response = await fetch(`http://127.0.0.1:${frontendAddress.port}/agent-api/health`, {
		headers: { 'x-tagent-client-ip': '203.0.113.9', 'x-tagent-via-frontend': 'spoofed' }
	});
	assert.equal(response.status, 200);
	const result = await response.json();
	assert.equal(result.path, '/health');
	assert.equal(result.viaFrontend, '1');
	assert.equal(result.clientIp, '127.0.0.1');
	const prefix = `http://127.0.0.1:${frontendAddress.port}/opennotebook-api`;
	const list = `${prefix}/api/notebooks?archived=false&order_by=updated+desc`;
	assert.equal((await fetch(list)).status, 200);
	authEnabled = true;
	assert.equal((await fetch(list)).status, 404);
	assert.equal((await fetch(list, { headers: { cookie: 'student=ok' } })).status, 200);
	notebookMode = 'none';
	assert.equal((await fetch(list, { headers: { cookie: 'student=ok' } })).status, 404);
	assert.equal((await fetch(list, { headers: { cookie: 'admin=ok' } })).status, 200);
	notebookMode = 'tagent';
	const writeHeaders = {
		cookie: 'student=ok',
		origin: process.env.TAGENT_PUBLIC_ORIGIN,
		'x-tagent-csrf': 'csrf-1'
	};
	assert.equal(
		(await fetch(`${prefix}/api/search`, { method: 'POST', headers: writeHeaders })).status,
		200
	);
	assert.equal(
		(await fetch(`${prefix}/api/notes`, { method: 'POST', headers: writeHeaders })).status,
		200
	);
	assert.equal(
		(
			await fetch(`${prefix}/api/notes`, {
				method: 'POST',
				headers: {
					...writeHeaders,
					cookie: 'admin=ok'
				}
			})
		).status,
		200
	);
	assert.equal(
		(
			await fetch(`${prefix}/api/search`, {
				method: 'POST',
				headers: {
					...writeHeaders,
					'x-tagent-csrf': 'wrong'
				}
			})
		).status,
		404
	);
	process.stdout.write('Vite preview auth and notebook proxies: PASS\n');
} finally {
	if (frontend) await frontend.close();
	backend.close();
	await once(backend, 'close');
	notebook.close();
	await once(notebook, 'close');
}
