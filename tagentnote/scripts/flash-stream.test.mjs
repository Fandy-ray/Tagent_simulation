import assert from 'node:assert/strict';
import test from 'node:test';

const { appendCards, parseEvent, splitLines } = await import('../src/lib/data/flashStream.ts');

const card = (id) => ({
	id,
	type: 'choice',
	question: `题 ${id}`,
	options: ['甲', '乙', '丙', '丁'],
	correct_index: 0,
	explanation: ''
});

const emptySession = () => ({
	deck: { deck_id: 'd', title: 't', total_cards: 0, cards: [] },
	queue: [],
	known: [],
	attempts: {},
	startedAt: 0,
	endedAt: null
});

test('一行被切成好几块：拼回来再拆，半行留着等下一块', () => {
	let rest = '';
	const lines = [];
	for (const chunk of ['{"type":"de', 'ck"}\n{"type":"ca', 'rd"}\n', '{"type":"done"}']) {
		const split = splitLines(rest, chunk);
		lines.push(...split.lines);
		rest = split.rest;
	}
	assert.deepEqual(lines, ['{"type":"deck"}', '{"type":"card"}']);
	assert.equal(rest, '{"type":"done"}');
	assert.deepEqual(splitLines(rest, '\n').lines, ['{"type":"done"}']);
});

test('空行和首尾空白不算一行', () => {
	assert.deepEqual(splitLines('', '\n  {"a":1}  \r\n\n').lines, ['{"a":1}']);
});

test('坏行、没有 type 的行跳过', () => {
	assert.equal(parseEvent('{"type":'), null);
	assert.equal(parseEvent('{"title":"x"}'), null);
	assert.deepEqual(parseEvent('{"type":"done","total_cards":3}'), { type: 'done', total_cards: 3 });
});

test('新到的卡排到队尾，总数跟着变', () => {
	let session = appendCards(emptySession(), [card('F1')]);
	session = { ...session, queue: [], known: ['F1'], endedAt: 5 };
	session = appendCards(session, [card('F2'), card('F3')]);
	assert.deepEqual(session.queue, ['F2', 'F3']);
	assert.equal(session.deck.total_cards, 3);
	assert.deepEqual(
		session.deck.cards.map((item) => item.id),
		['F1', 'F2', 'F3']
	);
	// 已经到的刷完了（advance 盖了结束时间），又来了新卡：这一轮还没完
	assert.equal(session.endedAt, null);
});

test('同一个 id 不会进两次', () => {
	const once = appendCards(emptySession(), [card('F1')]);
	assert.equal(appendCards(once, [card('F1')]), once);
});
