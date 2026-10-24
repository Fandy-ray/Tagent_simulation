import assert from 'node:assert/strict';
import test from 'node:test';

const { cueRepeatsText } = await import('../src/lib/data/cue.ts');

test('cue 只是题干去掉挖空的前半句：不显示', () => {
	// 2026-10-24 闪卡实测原样
	assert.ok(
		cueRepeatsText(
			'在单服务台排队系统中，若顾客按泊松过程到达，服务时间服从指数分布，则该系统通常记为',
			'在单服务台排队系统中，若顾客按泊松过程到达，服务时间服从指数分布，则该系统通常记为 ____。'
		)
	);
});

test('cue 连挖空一起抄、下划线条数还不一样：也算复述', () => {
	// 2026-10-24 整卷实测原样
	assert.ok(
		cueRepeatsText(
			'在M/M/1排队模型中，若平均到达率为$\\lambda$，则服务强度$\\rho$的计算公式为___。',
			'在 M/M/1 排队模型中，若平均到达率为 $\\lambda$，则服务强度 $\\rho$ 的计算公式为 ____。'
		)
	);
});

test('另给的提示照常显示', () => {
	assert.equal(cueRepeatsText('服务强度的定义', 'M/M/1 系统中 ρ = ____。'), false);
	assert.equal(
		cueRepeatsText('Little 公式', '系统中平均顾客数 L 与平均逗留时间 W 满足 L = ____。'),
		false
	);
});

test('空提示不显示', () => {
	assert.ok(cueRepeatsText('  ', '任意题干 ____。'));
});
