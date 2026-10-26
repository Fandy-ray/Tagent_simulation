import assert from 'node:assert/strict';
import { register } from 'node:module';
import test from 'node:test';

register('./lib-alias-hooks.mjs', import.meta.url);

const { enrichCitationsWithPages } = await import('../src/lib/data/citations.ts');

const citation = (fileId, extra = {}) => ({
	id: fileId,
	collectionId: 'nb',
	collectionName: '排队论笔记',
	fileId,
	title: '排队论讲义',
	kind: 'file',
	href: '#',
	grounded: true,
	...extra
});

test('要补页码的几条同时去取原文，不是一条等一条', async () => {
	let inFlight = 0;
	let peak = 0;
	const getText = async () => {
		inFlight += 1;
		peak = Math.max(peak, inFlight);
		await new Promise((resolve) => setTimeout(resolve, 30));
		inFlight -= 1;
		return '第3章 排队论\n第45页\nM/M/1 排队系统的平均等待时间';
	};
	const started = Date.now();
	const kept = await enrichCitationsWithPages(
		[citation('source:a'), citation('source:b'), citation('source:c')],
		'M/M/1 排队系统的平均等待时间',
		getText
	);
	assert.equal(peak, 3);
	assert.ok(Date.now() - started < 80, '三条一起取，用时约一个来回');
	assert.equal(kept.length, 3);
});

test('同一份来源只取一次；教材、论文（不在笔记本里）不取原文', async () => {
	const calls = [];
	const kept = await enrichCitationsWithPages(
		[
			citation('source:a'),
			citation('source:a', { id: 'dup', snippet: '另一段' }),
			citation('textbook:ch3', { chapter: '第3章', page: '第45页' })
		],
		'M/M/1 排队系统',
		async (fileId) => {
			calls.push(fileId);
			return '';
		}
	);
	assert.deepEqual(calls, ['source:a']);
	assert.ok(kept.some((item) => item.fileId === 'textbook:ch3'));
});

test('取原文出错不拖垮整次收尾：那条照常保留（回答确实用到了它）', async () => {
	const kept = await enrichCitationsWithPages([citation('source:a')], 'M/M/1', async () => {
		throw new Error('OpenNotebook 卡住了');
	});
	assert.equal(kept.length, 1);
});
