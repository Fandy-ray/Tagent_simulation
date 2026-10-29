import assert from 'node:assert/strict';
import test from 'node:test';

const { notebookRouteAllowed } = await import('../notebook-proxy.ts');

const P = '/opennotebook-api';
const allowed = (method, path) => notebookRouteAllowed(method, P + path);

test('前端发的每一种请求都放行（照抄 $lib/apis/opennotebook.ts）', () => {
	for (const [method, path] of [
		['GET', '/api/notebooks?archived=false&order_by=updated+desc'],
		['POST', '/api/notebooks'],
		['GET', '/api/notes?notebook_id=notebook%3A8m6qkcoq3hyn1uhcgmm1'],
		['GET', '/api/notes/note%3A8u832vy1ifeh9y1mc5qn'],
		['GET', '/api/notes/note:8u832vy1ifeh9y1mc5qn'],
		['POST', '/api/notes'],
		['POST', '/api/search'],
		['GET', '/api/sources?notebook_id=notebook%3Aabc&limit=100&sort_by=updated&sort_order=desc'],
		['GET', '/api/sources/source%3Aabc123']
	]) {
		assert.ok(allowed(method, path), `${method} ${path} 应该放行`);
	}
});

test('设置、模型、密钥、删改、没用到的接口和别的方法一律不转', () => {
	for (const [method, path] of [
		['GET', '/api/settings'],
		['GET', '/api/models'],
		['POST', '/api/models'],
		['GET', '/api/credentials'],
		['GET', '/api/notebooks/notebook%3Aabc'],
		['DELETE', '/api/notebooks/notebook%3Aabc'],
		['PUT', '/api/notes/note%3Aabc'],
		['PATCH', '/api/notes/note%3Aabc'],
		['POST', '/api/sources'],
		['POST', '/api/search/ask'],
		['GET', '/api/sources/source%3Aabc/insights'],
		['GET', '/api/notes/a/b'],
		['GET', '/api/notebooksX'],
		['HEAD', '/api/notebooks'],
		['OPTIONS', '/api/notebooks'],
		['GET', '/docs'],
		['GET', '']
	]) {
		assert.ok(!allowed(method, path), `${method} ${path} 应该拦下`);
	}
});

test('查询参数逐个核对：没用到的参数、塞进去的语句、重复的参数都不放', () => {
	for (const path of [
		'/api/notebooks?order_by=updated+desc%3B+DELETE+notebook',
		'/api/notebooks?order_by=updated desc; DELETE notebook',
		'/api/notebooks?order_by=updated+desc,name',
		'/api/notebooks?order_by=(SELECT+*+FROM+credential)',
		'/api/notebooks?archived=1',
		'/api/notebooks?archived=',
		'/api/notebooks?archived=false&archived=true',
		'/api/notebooks?foo=1',
		'/api/notes?notebook_id=notebook%3Aabc%27',
		'/api/notes?notebook_id=notebook%3Aabc%20OR%201%3D1',
		'/api/notes',
		'/api/sources?notebook_id=notebook%3Aabc&limit=1000',
		'/api/sources?notebook_id=notebook%3Aabc&sort_by=updated%20desc',
		'/api/sources?notebook_id=notebook%3Aabc&sort_order=desc;'
	]) {
		const wanted = path === '/api/notes';
		assert.equal(allowed('GET', path), wanted, `${path} 应该${wanted ? '放行' : '拦下'}`);
	}
	assert.ok(!allowed('POST', '/api/search?type=vector'), 'POST 不带查询参数');
});

test('转发时会被规整成别的路径的写法一律不转', () => {
	// 实测 /api/notes/%2e%2e 到了上游成了 /api/
	for (const path of [
		'/api/notes/%2e%2e',
		'/api/notes/%2E%2E',
		'/api/sources/%2e',
		'/api/notes/..',
		'/api/notes/..%2Fsettings',
		'/api/notes/%2fsettings',
		'/api/notes/%5csettings',
		'/api/notes/x\\settings',
		'/api/notes?notebook_id=..',
		'/api/notes/note%3Aabc#x'
	]) {
		assert.ok(!allowed('GET', path), `${path} 应该拦下`);
	}
});

test('前缀要完整匹配：/opennotebook-apiX 不算', () => {
	assert.ok(!notebookRouteAllowed('GET', '/opennotebook-apiX/api/notebooks'));
	assert.ok(!notebookRouteAllowed(undefined, undefined));
});
