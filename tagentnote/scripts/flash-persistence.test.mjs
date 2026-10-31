import assert from 'node:assert/strict';
import { register } from 'node:module';
import test from 'node:test';

register('./lib-alias-hooks.mjs', import.meta.url);

const { advance, clearFlashDeck, createSession, currentCard, loadFlashDeck, saveFlashDeck } =
	await import('../src/lib/data/flash.ts');

const storage = new Map();
globalThis.sessionStorage = {
	getItem: (key) => storage.get(key) ?? null,
	setItem: (key, value) => storage.set(key, value),
	removeItem: (key) => storage.delete(key)
};

const deck = {
	deck_id: 'deck-1',
	title: '排队论',
	total_cards: 2,
	cards: [
		{ id: 'F1', type: 'cloze', text: '第一张 ____', accept: ['甲'], accept_normalized: ['甲'] },
		{ id: 'F2', type: 'cloze', text: '第二张 ____', accept: ['乙'], accept_normalized: ['乙'] }
	]
};
const base = { modelId: 'deepseek', topic: '排队论', notebookIds: [] };

test('退出再进来：卡组和刷到第几张都还在', () => {
	storage.clear();
	const session = advance(createSession(deck), 'known');
	saveFlashDeck({ ...base, session });

	const saved = loadFlashDeck();
	assert.equal(saved.session.deck.cards.length, 2);
	assert.deepEqual(saved.session.known, ['F1']);
	assert.equal(currentCard(saved.session).id, 'F2');
	assert.equal(saved.modelId, 'deepseek');
});

test('清掉以后就没有了（明确放弃、开始新一轮）', () => {
	storage.clear();
	saveFlashDeck({ ...base, session: createSession(deck) });
	clearFlashDeck();
	assert.equal(loadFlashDeck(), null);
});

test('一张卡都没有的存档不算数：接回来也没东西可刷', () => {
	storage.clear();
	saveFlashDeck({ ...base, session: createSession({ ...deck, cards: [] }) });
	assert.equal(loadFlashDeck(), null);
});

test('两小时前的存档不要了，存储坏了也不报错', () => {
	storage.clear();
	saveFlashDeck({ ...base, session: createSession(deck, 1000) });
	assert.equal(loadFlashDeck(1000 + 2 * 60 * 60 * 1000 + 1), null);
	storage.set('tagent:flash-deck', '{坏的');
	assert.equal(loadFlashDeck(), null);
});
