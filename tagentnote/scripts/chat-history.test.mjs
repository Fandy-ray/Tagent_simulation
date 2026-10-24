import assert from 'node:assert/strict';
import test from 'node:test';

const { historyForRequest, HISTORY_MAX_MESSAGES } = await import('../src/lib/data/chatHistory.ts');

const msg = (role, content, extra = {}) => ({
	id: Math.random().toString(),
	role,
	content,
	...extra
});

test('在此之前答疑没有多轮记忆：现在能把前几轮带上', () => {
	const history = historyForRequest([
		msg('user', '什么是排队论'),
		msg('assistant', '排队论研究随机服务系统。'),
		msg('user', '那它的前提呢')
	]);
	assert.deepEqual(history, [
		{ role: 'user', content: '什么是排队论' },
		{ role: 'assistant', content: '排队论研究随机服务系统。' }
	]);
});

test('当前这一问不进历史（它由 question 单独发，带上会重复）', () => {
	const history = historyForRequest([msg('user', '只有一句')]);
	assert.deepEqual(history, []);
});

test('还在流式写入的占位不带进去', () => {
	// 真实时序：上一轮问答已完成，本轮 user 刚入列、assistant 占位正在流式写
	const history = historyForRequest([
		msg('user', '问题一'),
		msg('assistant', '回答一'),
		msg('user', '问题二'),
		msg('assistant', '', { streaming: true })
	]);
	assert.deepEqual(history, [
		{ role: 'user', content: '问题一' },
		{ role: 'assistant', content: '回答一' }
	]);
});

test('空内容的占位不带进去（否则模型会收到一条空的 assistant）', () => {
	const history = historyForRequest([
		msg('user', '问题一'),
		msg('assistant', '回答一'),
		msg('assistant', '   '),
		msg('user', '问题二')
	]);
	assert.deepEqual(history, [
		{ role: 'user', content: '问题一' },
		{ role: 'assistant', content: '回答一' }
	]);
});

test('卡片操作用 requestContent，不用展示用的短标签', () => {
	const history = historyForRequest([
		msg('user', '出题', { requestContent: '请按排队论出一道小论文题' }),
		msg('assistant', '题目如下……'),
		msg('user', '再来一道')
	]);
	assert.equal(history[0].content, '请按排队论出一道小论文题');
});

test('只保留最近若干条', () => {
	const many = [];
	for (let i = 0; i < 20; i += 1) {
		many.push(msg('user', `问题${i}`), msg('assistant', `回答${i}`));
	}
	many.push(msg('user', '当前这一问'));
	const history = historyForRequest(many);
	assert.equal(history.length, HISTORY_MAX_MESSAGES);
	assert.equal(history.at(-1).content, '回答19', '保留的该是最近的');
});

test('超字符预算时从旧的开始丢', () => {
	const history = historyForRequest(
		[
			msg('user', 'A'.repeat(500)),
			msg('assistant', 'B'.repeat(500)),
			msg('user', 'C'.repeat(500)),
			msg('assistant', 'D'.repeat(500)),
			msg('user', '当前')
		],
		{ maxChars: 1100 }
	);
	// 预算 1100：C+D=1000 装得下，再加 B 就是 1500，超了
	assert.deepEqual(
		history.map((m) => m.content[0]),
		['C', 'D'],
		'该从最旧的开始丢，保留离当前最近的'
	);
});

test('单条就超预算时仍然至少带一条，不返回空历史', () => {
	const history = historyForRequest(
		[msg('user', 'X'.repeat(9000)), msg('assistant', 'Y'.repeat(9000)), msg('user', '当前')],
		{ maxChars: 100 }
	);
	assert.equal(history.length, 1);
	assert.equal(history[0].role, 'assistant');
});

test('空会话返回空历史', () => {
	assert.deepEqual(historyForRequest([]), []);
});
