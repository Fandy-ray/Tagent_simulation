import assert from 'node:assert/strict';
import test from 'node:test';

const { composeMessage, isTextFile, unsupportedReason, MAX_ATTACHMENT_CHARS } =
	await import('../src/lib/data/attachments.ts');

test('没有附件、技能：原样发，检索也用原话', () => {
	const result = composeMessage('  什么是排队论？ ', []);
	assert.equal(result.request, '什么是排队论？');
	assert.equal(result.display, '什么是排队论？');
	assert.equal(result.retrievalQuery, undefined);
});

test('文本附件把内容带上；气泡里只列文件名；检索只用学生打的那句', () => {
	const result = composeMessage('帮我看看这段代码', [
		{ name: 'mm1.py', content: 'lam = 0.5\nmu = 1.0\nprint(lam / mu)' }
	]);
	assert.match(result.request, /^帮我看看这段代码\n\n【附件：mm1\.py】\n```\nlam = 0\.5/);
	assert.ok(!result.display.includes('lam = 0.5'));
	assert.match(result.display, /📎 mm1\.py/);
	assert.equal(result.retrievalQuery, '帮我看看这段代码');
});

test('读不了的附件不假装发了，单独列出来', () => {
	const result = composeMessage('总结一下', [
		{ name: '论文.pdf', unsupported: 'PDF 目前还不能读' },
		{ name: 'notes.md', content: '# 笔记' }
	]);
	assert.deepEqual(
		result.skipped.map((item) => item.name),
		['论文.pdf']
	);
	assert.ok(!result.request.includes('论文.pdf'));
	assert.match(result.display, /📎 论文\.pdf、notes\.md/);
});

test('附件太长：从后面截，并写明截掉了多少', () => {
	const long = '字'.repeat(MAX_ATTACHMENT_CHARS + 500);
	const result = composeMessage('看看', [
		{ name: 'a.txt', content: long },
		{ name: 'b.txt', content: '第二个' }
	]);
	assert.match(result.request, /后面还有 500 字/);
	assert.match(result.request, /【附件：b\.txt】（太长了，没有放进来）/);
	assert.ok(result.request.length < MAX_ATTACHMENT_CHARS + 200);
});

test('只传附件不打字：补一句「请结合附件回答」，检索用附件开头', () => {
	const result = composeMessage('', [
		{ name: 'q.txt', content: '  M/M/1   排队系统的平均等待时间 ' }
	]);
	assert.match(result.request, /^请结合附件回答。/);
	assert.equal(result.retrievalQuery, 'M/M/1 排队系统的平均等待时间');
});

test('技能变成回答要求；空内容的技能忽略', () => {
	const result = composeMessage(
		'解释泊松过程',
		[],
		[
			{ name: '通俗讲解', content: '用高中生能懂的话讲，举一个生活里的例子。' },
			{ name: '空的', content: '  ' }
		]
	);
	assert.match(result.request, /【回答要求】\n- 通俗讲解：用高中生能懂的话讲/);
	assert.ok(!result.request.includes('空的'));
	assert.match(result.display, /🧩 通俗讲解/);
	assert.equal(result.retrievalQuery, '解释泊松过程');
});

test('哪些文件按文本读', () => {
	assert.ok(isTextFile({ name: 'a.md', type: '' }));
	assert.ok(isTextFile({ name: 'data.CSV', type: '' }));
	assert.ok(isTextFile({ name: 'x', type: 'text/plain' }));
	assert.ok(isTextFile({ name: 'cfg', type: 'application/json' }));
	assert.equal(isTextFile({ name: 'paper.pdf', type: 'application/pdf' }), false);
	assert.equal(isTextFile({ name: 'shot.png', type: 'image/png' }), false);
	assert.match(unsupportedReason({ name: 'paper.pdf', type: 'application/pdf' }), /PDF/);
	assert.match(unsupportedReason({ name: 'big.txt', type: 'text/plain', size: 3_000_000 }), /太大/);
});
