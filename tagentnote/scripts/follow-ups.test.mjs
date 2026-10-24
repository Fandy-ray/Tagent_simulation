import assert from 'node:assert/strict';
import test from 'node:test';

const { buildFollowUps, buildTags, excerpt } = await import('../src/lib/data/followUps.ts');

test('截断时补省略号，不留半截词', () => {
	const long = '排队论里服务强度和系统稳定性的关系到底是怎么回事呢';
	const got = excerpt(long, 24);
	assert.ok(got.endsWith('…'), `应当以省略号收口，实际是「${got}」`);
	assert.ok(got.length <= 25);
});

test('短问题原样引用，不画蛇添足加省略号', () => {
	assert.equal(excerpt('什么是排队论'), '什么是排队论');
});

test('英文在空格处收口', () => {
	assert.equal(excerpt('what is the service intensity of a queue', 24), 'what is the service…');
});

test('截断处的尾随标点要去掉', () => {
	const got = excerpt('排队论的核心是什么，以及它怎么用，还有别的吗', 10);
	assert.ok(!/[，,]…$/.test(got), `不该是「标点+省略号」：${got}`);
});

test('追问建议引用的是截断后的问题', () => {
	const ups = buildFollowUps('排队论里服务强度和系统稳定性的关系到底是怎么回事呢');
	assert.equal(ups.length, 3);
	assert.ok(ups[0].includes('…'), '引用过长问题时要有省略号');
});

test('空问题不产出追问', () => {
	assert.deepEqual(buildFollowUps('   '), []);
});

test('M/M/1 要被当成一个标签，而不是被斜杠拆散丢掉', () => {
	const tags = buildTags('M/M/1 模型的服务强度怎么算');
	assert.ok(tags.includes('M/M/1'), `M/M/1 丢了：${JSON.stringify(tags)}`);
});

test('希腊字母的比值记号也不拆', () => {
	assert.ok(buildTags('λ/μ 表示什么').includes('λ/μ'));
});

test('标签末尾的虚词削掉', () => {
	const tags = buildTags('排队系统里的服务台有几个');
	assert.ok(
		tags.includes('排队系统'),
		`应当是「排队系统」而不是「排队系统里」：${JSON.stringify(tags)}`
	);
});

test('削虚词不能把词削到剩一个字', () => {
	// 「上下」削掉尾字只剩「上」，那还不如不削
	assert.ok(buildTags('上下 浮动').every((t) => t.length >= 2));
});

test('重复的词只出一个标签', () => {
	const tags = buildTags('排队论和排队论的区别');
	assert.equal(tags.filter((t) => t === '排队论').length, 1);
});

test('单字一律不当标签', () => {
	assert.ok(buildTags('a b c 的 了').every((t) => t.length >= 2));
});

test('实在没词时给一个兜底标签', () => {
	assert.deepEqual(buildTags('？？？'), ['答疑']);
});

test('标签数量有上限', () => {
	assert.ok(buildTags('排队论 仿真模型 随机过程 泊松分布 指数分布').length <= 3);
});

test('指代型追问不原样引进追问建议', () => {
	// 实测：问完 M/M/1 再问「那它的前提呢」，第一条建议是「请更详细地解释「那它的前提呢」」
	const [first] = buildFollowUps('那它的前提呢');
	assert.ok(!first.includes('那它'), `不该引用光杆追问：${first}`);
});

test('自足的问题照旧引用原话', () => {
	assert.equal(buildFollowUps('什么是排队论')[0], '请更详细地解释「什么是排队论」');
	// 长问题里带「它」也不算光杆追问
	const long = '排队论里服务强度和它对系统稳定性的影响';
	assert.ok(buildFollowUps(long)[0].startsWith('请更详细地解释「'));
});

test('疑问词和指代词的碎片不当标签', () => {
	// 实测：「什么是 M/M/1 排队模型？」出了 #什么，「那它的前提呢」出了 #那它
	assert.deepEqual(buildTags('什么是 M/M/1 排队模型？'), ['M/M/1', '排队模型']);
	assert.deepEqual(buildTags('那它的前提呢'), ['前提']);
});
