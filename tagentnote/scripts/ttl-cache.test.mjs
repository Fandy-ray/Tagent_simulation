import assert from 'node:assert/strict';
import test from 'node:test';

const { createTtlCache } = await import('../src/lib/data/ttlCache.ts');

const clock = () => {
	let now = 0;
	const fn = () => now;
	fn.advance = (ms) => (now += ms);
	return fn;
};

test('窗口内复用同一份结果，不重复请求', async () => {
	const now = clock();
	const cache = createTtlCache(1000, now);
	let calls = 0;
	const load = async () => (calls += 1);

	assert.equal(await cache.get(load), 1);
	now.advance(500);
	assert.equal(await cache.get(load), 1);
	assert.equal(calls, 1);
});

test('过期后重新取', async () => {
	const now = clock();
	const cache = createTtlCache(1000, now);
	let calls = 0;
	const load = async () => (calls += 1);

	await cache.get(load);
	now.advance(1001);
	assert.equal(await cache.get(load), 2);
});

test('并发调用合并成一次请求', async () => {
	const cache = createTtlCache(1000, clock());
	let calls = 0;
	const load = async () => {
		calls += 1;
		await new Promise((r) => setTimeout(r, 10));
		return calls;
	};

	const [a, b, c] = await Promise.all([cache.get(load), cache.get(load), cache.get(load)]);
	assert.deepEqual([a, b, c], [1, 1, 1]);
	assert.equal(calls, 1, '三个调用方该共用同一个在飞的请求');
});

test('失败的结果不被缓存住，下次能重试', async () => {
	const cache = createTtlCache(10_000, clock());
	let calls = 0;
	const load = async () => {
		calls += 1;
		if (calls === 1) throw new Error('网络抖了一下');
		return 'ok';
	};

	await assert.rejects(() => cache.get(load));
	assert.equal(await cache.get(load), 'ok', '一次失败不该把缓存钉死');
});

test('invalidate 之后立刻重新取', async () => {
	const cache = createTtlCache(10_000, clock());
	let calls = 0;
	const load = async () => (calls += 1);

	await cache.get(load);
	cache.invalidate();
	assert.equal(await cache.get(load), 2);
});

test('一个调用方中断，不该拖垮共用同一次请求的其他调用方', async () => {
	// 实测路径：KnowledgeCombobox 传了自己的 signal，答疑页和笔记本页没传，
	// 三者拿到同一个 Promise；Combobox 一卸载 abort，另外两个也跟着失败。
	const cache = createTtlCache(10_000, clock());
	let calls = 0;
	const load = async () => {
		calls += 1;
		await new Promise((r) => setTimeout(r, 20));
		return 'ok';
	};

	// 模拟 listNotebookKnowledge 的包法：共享请求不绑 signal
	const shared = cache.get(load);
	const controller = new AbortController();
	const withSignal = new Promise((resolve, reject) => {
		controller.signal.addEventListener('abort', () => reject(new Error('aborted')), {
			once: true
		});
		shared.then(resolve, reject);
	});

	controller.abort();
	await assert.rejects(() => withSignal);
	assert.equal(await cache.get(load), 'ok', '别人中断不该影响这一个');
	assert.equal(calls, 1, '仍然只打一次请求');
});
