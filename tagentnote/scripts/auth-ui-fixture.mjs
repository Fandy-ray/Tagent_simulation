/** 本机页面验收专用假后端；不连接真实账号库，也不发送邮件。 */
import { createServer } from 'node:http';

const origin = 'http://127.0.0.1:4173';
const student = {
	id: 'fixture-student',
	email: 'student@example.test',
	name: '测试学生',
	role: 'student',
	verified: true,
	active: true
};
const course = {
	id: 'fixture-course',
	name: '系统仿真课程',
	description: '',
	active: true,
	model_ids: ['fixture-model'],
	notebook_ids: []
};
const personal = new Map();

const server = createServer(async (request, response) => {
	const url = new URL(request.url || '/', 'http://localhost');
	const signedIn = request.headers.cookie?.includes('tagent_session_dev=fixture-session');
	const method = request.method || 'GET';
	response.setHeader('content-type', 'application/json; charset=utf-8');
	response.setHeader('cache-control', 'no-store');
	const send = (status, payload) => {
		response.statusCode = status;
		response.end(JSON.stringify(payload));
	};
	if (url.pathname === '/auth/status') return send(200, { enabled: true, registration_open: true });
	if (url.pathname === '/health') return send(200, { status: 'ok' });
	if (url.pathname === '/auth/login' && method === 'POST') {
		let body = '';
		for await (const chunk of request) body += chunk;
		const input = JSON.parse(body || '{}');
		if (input.email !== student.email || input.password !== 'fixture-password-123')
			return send(401, { error: { message: '测试账号或密码不正确。' } });
		response.setHeader(
			'set-cookie',
			'tagent_session_dev=fixture-session; Path=/; HttpOnly; SameSite=Lax'
		);
		return send(200, { user: student, csrf: 'fixture-csrf' });
	}
	if (url.pathname === '/auth/logout' && method === 'POST') {
		response.setHeader('set-cookie', 'tagent_session_dev=; Max-Age=0; Path=/');
		return send(200, { logged_out: true });
	}
	if (url.pathname === '/auth/register' && method === 'POST')
		return send(202, { message: '测试验证邮件已发出。' });
	if (url.pathname === '/auth/password/forgot' && method === 'POST')
		return send(202, { message: '测试重置邮件已发出。' });
	if (url.pathname === '/auth/verify-email' && method === 'POST')
		return send(200, { verified: true });
	if (url.pathname === '/auth/password/reset' && method === 'POST')
		return send(200, { reset: true });
	if (!signedIn) return send(401, { error: { message: '请先登录。', code: 'login_required' } });
	if (url.pathname === '/auth/me') return send(200, { user: student, csrf: 'fixture-csrf' });
	if (url.pathname === '/me/courses') return send(200, { courses: [course] });
	if (url.pathname.startsWith('/me/data/')) {
		const key = `${request.headers['x-tagent-course-id'] || 'general'}:${url.pathname}`;
		if (method === 'GET') return send(200, personal.get(key) || { version: 0, data: null });
		if (method === 'PUT') {
			if (request.headers['x-tagent-csrf'] !== 'fixture-csrf')
				return send(403, { error: { message: '测试页面校验失败。' } });
			let body = '';
			for await (const chunk of request) body += chunk;
			const input = JSON.parse(body || '{}');
			const previous = personal.get(key) || { version: 0 };
			if (input.version !== previous.version)
				return send(409, { error: { message: '版本冲突。' } });
			const saved = { version: previous.version + 1, data: input.data };
			personal.set(key, saved);
			return send(200, { version: saved.version });
		}
	}
	if (url.pathname === '/v1/models')
		return send(200, {
			object: 'list',
			data: [
				{ id: 'fixture-model', name: '测试模型', object: 'model', created: 0, owned_by: 'fixture' }
			]
		});
	return send(404, { error: { message: '测试接口未实现。' } });
});

server.listen(5009, '127.0.0.1', () => {
	process.stdout.write(`auth fixture ready on 127.0.0.1:5009; frontend origin ${origin}\n`);
});
