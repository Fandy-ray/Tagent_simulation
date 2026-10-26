import assert from 'node:assert/strict';
import test from 'node:test';

const { integerPoints } = await import('../src/lib/data/essay.ts');

const dims = (content, argument, language) => [
	{ name: 'content', weight: 0.4, score_ratio: content },
	{ name: 'argument', weight: 0.35, score_ratio: argument },
	{ name: 'language', weight: 0.25, score_ratio: language }
];
const sum = (map) => [...map.values()].reduce((a, b) => a + b, 0);

test('只有一格带小数：差的那一分给它', () => {
	// 40×0.75=30，35×1=35，25×0.5=12.5 → 77.5，后端 round 成 78
	const points = integerPoints(dims(0.75, 1, 0.5), 78);
	assert.deepEqual(Object.fromEntries(points), { content: 30, argument: 35, language: 13 });
});

test('带 .25/.75 的：三格加起来等于后端的总分（Python 的 round 是四舍六入五成双）', () => {
	// 40×0.75=30，35×0.75=26.25，25×0.5=12.5 → 68.75，后端 round 成 69
	const points = integerPoints(dims(0.75, 0.75, 0.5), 69);
	assert.equal(sum(points), 69);
	assert.deepEqual(Object.fromEntries(points), { content: 30, argument: 26, language: 13 });
});

test('总分是 .5 被五成双舍掉时也对得上', () => {
	// 40×0.5=20，35×0.5=17.5，25×0.5=12.5 → 50，没有小数
	assert.equal(sum(integerPoints(dims(0.5, 0.5, 0.5), 50)), 50);
	// 40×0.25=10，35×0.5=17.5，25×0.5=12.5 → 40；后端给 40
	const points = integerPoints(dims(0.25, 0.5, 0.5), 40);
	assert.equal(sum(points), 40);
	// 35×0.25=8.75，25×0.25=6.25，40×0.5=20 → 35
	assert.equal(sum(integerPoints(dims(0.5, 0.25, 0.25), 35)), 35);
});

test('每格都不超过满分、不低于整数部分', () => {
	for (const a of [0, 0.25, 0.5, 0.75, 1])
		for (const b of [0, 0.25, 0.5, 0.75, 1])
			for (const c of [0, 0.25, 0.5, 0.75, 1]) {
				const exact = 40 * a + 35 * b + 25 * c;
				const total = Math.round(exact);
				const points = integerPoints(dims(a, b, c), total);
				assert.equal(sum(points), total, `${a} ${b} ${c}`);
				assert.ok(
					points.get('content') <= 40 &&
						points.get('argument') <= 35 &&
						points.get('language') <= 25
				);
				assert.ok(points.get('argument') >= Math.floor(35 * b + 1e-9));
			}
});

test('还没有总分时按合计四舍五入', () => {
	assert.equal(sum(integerPoints(dims(0.75, 0.75, 0.5))), 69);
});
