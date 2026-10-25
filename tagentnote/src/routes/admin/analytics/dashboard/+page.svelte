<script lang="ts">
	type Period = '24h' | '7d' | '30d' | '90d' | 'all';
	type ModelStat = { id: string; name: string; count: number; tokens: number };
	type UserStat = {
		id: string;
		name: string;
		email: string;
		count: number;
		tokens: number;
		group: string;
	};
	type ChartPoint = { label: string; values: number[] };

	const periods: { id: Period; label: string; days: number }[] = [
		{ id: '24h', label: '最近 24 小时', days: 1 },
		{ id: '7d', label: '最近 7 天', days: 7 },
		{ id: '30d', label: '最近 30 天', days: 30 },
		{ id: '90d', label: '最近 90 天', days: 90 },
		{ id: 'all', label: '全部时间', days: 180 }
	];
	const chartColors = ['#3b82f6', '#10b981', '#f59e0b', '#a78bfa'];
	const modelCatalog = [
		{ id: 'tagent-chat', name: 'TAgent Chat', share: 0.36 },
		{ id: 'qwen-2.5', name: 'Qwen 2.5', share: 0.29 },
		{ id: 'deepseek-v3', name: 'DeepSeek V3', share: 0.21 },
		{ id: 'gpt-4o', name: 'GPT-4o', share: 0.14 }
	];
	const userCatalog: UserStat[] = [
		{
			id: 'u-1001',
			name: '林知夏',
			email: 'lin.zx@example.com',
			count: 486,
			tokens: 1284300,
			group: '研究生'
		},
		{
			id: 'u-1002',
			name: '陈嘉木',
			email: 'chen.jm@example.com',
			count: 362,
			tokens: 948200,
			group: '研究生'
		},
		{
			id: 'u-1003',
			name: '周予安',
			email: 'zhou.ya@example.com',
			count: 294,
			tokens: 731800,
			group: '教师'
		},
		{
			id: 'u-1004',
			name: '许清禾',
			email: 'xu.qh@example.com',
			count: 218,
			tokens: 602100,
			group: '本科生'
		},
		{
			id: 'u-1005',
			name: '沈星野',
			email: 'shen.xy@example.com',
			count: 164,
			tokens: 418600,
			group: '本科生'
		},
		{
			id: 'u-1006',
			name: '顾言之',
			email: 'gu.yz@example.com',
			count: 121,
			tokens: 286400,
			group: '教师'
		}
	];
	const groupOptions = ['全部用户', '教师', '研究生', '本科生'];

	let period = $state<Period>('7d');
	let group = $state('全部用户');
	let modelSort = $state<'name' | 'count' | 'tokens' | 'percentage'>('count');
	let modelDirection = $state<'asc' | 'desc'>('desc');
	let userSort = $state<'name' | 'count' | 'tokens'>('count');
	let userDirection = $state<'asc' | 'desc'>('desc');
	let selectedModel = $state<ModelStat | null>(null);
	let hoverIndex = $state<number | null>(null);

	if (typeof localStorage !== 'undefined') {
		const saved = localStorage.getItem('admin-analytics-period');
		if (saved && periods.some((item) => item.id === saved)) period = saved as Period;
	}

	const dayCount = $derived(periods.find((item) => item.id === period)?.days ?? 7);
	const scale = $derived(Math.min(dayCount / 7, 5.4));
	const visibleUsers = $derived(
		userCatalog.filter((user) => group === '全部用户' || user.group === group)
	);
	const totalMessages = $derived(
		Math.round(visibleUsers.reduce((sum, user) => sum + user.count, 0) * scale)
	);
	const totalTokens = $derived(
		Math.round(visibleUsers.reduce((sum, user) => sum + user.tokens, 0) * scale)
	);
	const totalChats = $derived(Math.round(totalMessages * 0.31));
	const totalUsers = $derived(visibleUsers.length);
	const modelStats = $derived<ModelStat[]>(
		modelCatalog.map((model, index) => ({
			id: model.id,
			name: model.name,
			count: Math.round(totalMessages * model.share),
			tokens: Math.round(totalTokens * model.share * (0.88 + index * 0.08))
		}))
	);
	const sortedModels = $derived(
		[...modelStats].sort((a, b) => {
			const result =
				modelSort === 'name'
					? a.name.localeCompare(b.name)
					: modelSort === 'tokens'
						? a.tokens - b.tokens
						: a.count - b.count;
			return modelDirection === 'asc' ? result : -result;
		})
	);
	const sortedUsers = $derived(
		[...visibleUsers].sort((a, b) => {
			const result =
				userSort === 'name'
					? a.name.localeCompare(b.name)
					: userSort === 'tokens'
						? a.tokens - b.tokens
						: a.count - b.count;
			return userDirection === 'asc' ? result : -result;
		})
	);
	const chartData = $derived.by<ChartPoint[]>(() => {
		const points = period === '24h' ? 24 : Math.min(dayCount, 30);
		return Array.from({ length: points }, (_, index) => {
			const angle = index * 1.47;
			const trend =
				0.34 + 0.38 * Math.abs(Math.sin(angle)) + 0.16 * Math.abs(Math.sin(angle * 0.37 + 1.1));
			return {
				label:
					period === '24h'
						? `${String(index).padStart(2, '0')}:00`
						: new Date(Date.now() - (points - index - 1) * 86400000).toLocaleDateString('zh-CN', {
								month: 'numeric',
								day: 'numeric'
							}),
				values: modelStats.map((model, modelIndex) =>
					Math.round((model.count / points) * trend * (0.78 + modelIndex * 0.11))
				)
			};
		});
	});
	const maxChartValue = $derived(Math.max(1, ...chartData.flatMap((point) => point.values)));
	const linePoints = (modelIndex: number) =>
		chartData
			.map((point, index) => {
				const x = chartData.length <= 1 ? 50 : (index / (chartData.length - 1)) * 100;
				const y = 100 - (point.values[modelIndex] / maxChartValue) * 96;
				return `${x},${y}`;
			})
			.join(' ');
	const formatNumber = (value: number) =>
		Intl.NumberFormat('zh-CN', {
			notation: value >= 1000000 ? 'compact' : 'standard',
			maximumFractionDigits: 1
		}).format(value);

	const axisLabels = $derived.by(() => {
		const total = chartData.length;
		const ticks = Math.min(6, total);
		return Array.from({ length: ticks }, (_, index) => {
			const pointIndex = ticks <= 1 ? 0 : Math.round((index / (ticks - 1)) * (total - 1));
			return {
				index: pointIndex,
				left: total <= 1 ? 0 : (pointIndex / (total - 1)) * 100,
				label: chartData[pointIndex]?.label ?? ''
			};
		});
	});

	function updatePeriod(value: Period) {
		period = value;
		if (typeof localStorage !== 'undefined') localStorage.setItem('admin-analytics-period', value);
	}

	function sortModels(key: typeof modelSort) {
		if (modelSort === key) modelDirection = modelDirection === 'asc' ? 'desc' : 'asc';
		else {
			modelSort = key;
			modelDirection = key === 'name' ? 'asc' : 'desc';
		}
	}

	function sortUsers(key: typeof userSort) {
		if (userSort === key) userDirection = userDirection === 'asc' ? 'desc' : 'asc';
		else {
			userSort = key;
			userDirection = key === 'name' ? 'asc' : 'desc';
		}
	}
</script>

<svelte:head><title>分析 | 管理员面板</title></svelte:head>

<section class="w-full px-2 pb-6 text-gray-900 dark:text-gray-100">
	<header
		class="sticky top-0 z-10 flex items-center justify-between gap-3 bg-white/95 py-1.5 backdrop-blur dark:bg-gray-900/95"
	>
		<h1 class="px-0.5 text-sm font-medium">分析</h1>
		<div class="flex items-center gap-2">
			<select
				class="w-fit max-w-32 rounded-sm bg-transparent px-1.5 py-1 text-right text-xs text-gray-600 outline-none dark:text-gray-300"
				bind:value={group}
				aria-label="筛选用户组"
			>
				{#each groupOptions as option (option)}<option value={option}>{option}</option>{/each}
			</select>
			<select
				class="w-fit rounded-sm bg-transparent px-1.5 py-1 text-right text-xs text-gray-600 outline-none dark:text-gray-300"
				value={period}
				onchange={(event) => updatePeriod(event.currentTarget.value as Period)}
				aria-label="统计时间范围"
			>
				{#each periods as option (option.id)}<option value={option.id}>{option.label}</option
					>{/each}
			</select>
		</div>
	</header>

	<div
		class="flex flex-wrap items-center gap-x-4 gap-y-0.5 px-0.5 pb-1 text-xs text-gray-500 dark:text-gray-400"
	>
		<span
			><span class="font-medium text-gray-900 dark:text-gray-300"
				>{totalMessages.toLocaleString()}</span
			> 条消息</span
		>
		<span title="Token 数量为估算值"
			><span class="font-medium text-gray-900 dark:text-gray-300">{formatNumber(totalTokens)}</span> tokens</span
		>
		<span
			><span class="font-medium text-gray-900 dark:text-gray-300"
				>{totalChats.toLocaleString()}</span
			> 对话</span
		>
		<span><span class="font-medium text-gray-900 dark:text-gray-300">{totalUsers}</span> 用户</span>
	</div>

	<div class="px-0.5 pb-1 text-xs font-medium text-gray-600 dark:text-gray-400">
		{period === '24h' ? '每小时消息数' : '每日消息数'}
	</div>

	<div class="relative h-44 w-full overflow-hidden px-0.5">
		<div class="absolute inset-x-0 top-0 bottom-6 flex flex-col justify-between" aria-hidden="true">
			<div class="dark:border-gray-850/40 border-t border-gray-100"></div>
			<div class="dark:border-gray-850/40 border-t border-gray-100"></div>
			<div class="dark:border-gray-850/40 border-t border-gray-100"></div>
			<div class="dark:border-gray-850/40 border-t border-gray-100"></div>
			<div class="dark:border-gray-850/40 border-t border-gray-100"></div>
		</div>

		<div class="absolute inset-x-0 top-0 bottom-6">
			<svg
				viewBox="0 0 100 100"
				preserveAspectRatio="none"
				class="block h-full w-full"
				role="img"
				aria-label="按模型统计的消息趋势"
				onmousemove={(event) => {
					const rect = event.currentTarget.getBoundingClientRect();
					const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
					hoverIndex = Math.round(ratio * (chartData.length - 1));
				}}
				onmouseleave={() => (hoverIndex = null)}
			>
				{#each modelStats as model, index (model.id)}
					<polyline
						points={linePoints(index)}
						fill="none"
						stroke={chartColors[index]}
						stroke-width="1.5"
						stroke-linejoin="round"
						vector-effect="non-scaling-stroke"
					/>
				{/each}
				{#if hoverIndex !== null}
					<line
						x1={(hoverIndex / Math.max(1, chartData.length - 1)) * 100}
						y1="0"
						x2={(hoverIndex / Math.max(1, chartData.length - 1)) * 100}
						y2="100"
						stroke="currentColor"
						stroke-opacity=".25"
						stroke-width="1"
						vector-effect="non-scaling-stroke"
					/>
				{/if}
			</svg>
		</div>

		<div class="absolute inset-x-0 bottom-0 h-6 text-[10px] text-gray-400">
			{#each axisLabels as tick (tick.index)}
				<span
					class="absolute top-1 -translate-x-1/2 whitespace-nowrap first:translate-x-0 last:-translate-x-full"
					style={`left:${tick.left}%`}
				>
					{tick.label}
				</span>
			{/each}
		</div>

		{#if hoverIndex !== null}
			<div
				class="pointer-events-none absolute top-0 right-1 min-w-[132px] rounded border border-gray-100 bg-white/95 px-2 py-1.5 text-[10px] shadow-sm dark:border-gray-800 dark:bg-gray-900/95"
			>
				<p class="mb-1 text-gray-400">{chartData[hoverIndex]?.label}</p>
				{#each modelStats as model, index (model.id)}
					<div class="flex items-center justify-between gap-3 py-0.5">
						<span style={`color:${chartColors[index]}`}>{model.name}</span>
						<span class="text-gray-900 tabular-nums dark:text-white"
							>{chartData[hoverIndex]?.values[index]}</span
						>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<div class="mt-2 grid gap-4 md:grid-cols-2">
		<section class="min-w-0">
			<h2 class="mb-1 px-0.5 text-xs font-medium text-gray-700 dark:text-gray-300">模型用量</h2>
			<div class="overflow-x-auto whitespace-nowrap">
				<table class="w-full min-w-[420px] text-left text-xs text-gray-500 dark:text-gray-400">
					<thead class="text-[10px] text-gray-800 uppercase dark:text-gray-200">
						<tr class="dark:border-gray-850/40 border-b border-gray-100">
							<th class="w-8 px-2.5 py-2">#</th>
							<th class="px-2.5 py-2"
								><button class="inline-flex items-center gap-1" onclick={() => sortModels('name')}
									>模型{#if modelSort === 'name'}<span class="font-normal"
											>{modelDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								></th
							>
							<th class="px-2.5 py-2 text-right"
								><button class="inline-flex items-center gap-1" onclick={() => sortModels('count')}
									>消息{#if modelSort === 'count'}<span class="font-normal"
											>{modelDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								></th
							>
							<th class="px-2.5 py-2 text-right"
								><button class="inline-flex items-center gap-1" onclick={() => sortModels('tokens')}
									>Tokens{#if modelSort === 'tokens'}<span class="font-normal"
											>{modelDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								></th
							>
							<th class="px-2.5 py-2 text-right"
								><button
									class="inline-flex items-center gap-1"
									onclick={() => sortModels('percentage')}
									>%{#if modelSort === 'percentage'}<span class="font-normal"
											>{modelDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								></th
							>
						</tr>
					</thead>
					<tbody>
						{#each sortedModels as model, index (model.id)}
							<tr
								class="dark:border-gray-850/30 dark:hover:bg-gray-850 cursor-pointer border-b border-gray-50 text-gray-700 transition hover:bg-gray-50 dark:text-gray-300"
								onclick={() => (selectedModel = model)}
								onkeydown={(event) => {
									if (event.key === 'Enter') selectedModel = model;
								}}
								role="button"
								tabindex="0"
							>
								<td class="px-2.5 py-1.5 text-gray-400">{index + 1}</td>
								<td class="px-2.5 py-1.5 font-medium text-gray-900 dark:text-white">
									<span
										class="mr-2 inline-block size-2 rounded-full align-middle"
										style={`background:${chartColors[index]}`}
									></span>{model.name}
								</td>
								<td class="px-2.5 py-1.5 text-right">{model.count.toLocaleString()}</td>
								<td class="px-2.5 py-1.5 text-right">{formatNumber(model.tokens)}</td>
								<td class="px-2.5 py-1.5 text-right text-gray-400"
									>{totalMessages ? ((model.count / totalMessages) * 100).toFixed(1) : '0.0'}%</td
								>
							</tr>
						{:else}
							<tr><td colspan="5" class="px-2.5 py-3 text-center text-gray-400">暂无数据</td></tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>

		<section class="min-w-0">
			<h2 class="mb-1 px-0.5 text-xs font-medium text-gray-700 dark:text-gray-300">用户活动</h2>
			<div class="overflow-x-auto whitespace-nowrap">
				<table class="w-full min-w-[360px] text-left text-xs text-gray-500 dark:text-gray-400">
					<thead class="text-[10px] text-gray-800 uppercase dark:text-gray-200">
						<tr class="dark:border-gray-850/40 border-b border-gray-100">
							<th class="w-8 px-2.5 py-2">#</th>
							<th class="px-2.5 py-2"
								><button class="inline-flex items-center gap-1" onclick={() => sortUsers('name')}
									>用户{#if userSort === 'name'}<span class="font-normal"
											>{userDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								></th
							>
							<th class="px-2.5 py-2 text-right"
								><button class="inline-flex items-center gap-1" onclick={() => sortUsers('count')}
									>消息{#if userSort === 'count'}<span class="font-normal"
											>{userDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								></th
							>
							<th class="px-2.5 py-2 text-right"
								><button class="inline-flex items-center gap-1" onclick={() => sortUsers('tokens')}
									>Tokens{#if userSort === 'tokens'}<span class="font-normal"
											>{userDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								></th
							>
						</tr>
					</thead>
					<tbody>
						{#each sortedUsers as user, index (user.id)}
							<tr
								class="dark:border-gray-850/30 border-b border-gray-50 text-gray-700 dark:text-gray-300"
							>
								<td class="px-2.5 py-1.5 text-gray-400">{index + 1}</td>
								<td class="px-2.5 py-1.5">
									<span
										class="mr-2 inline-flex size-5 items-center justify-center rounded-full bg-blue-100 align-middle text-[9px] font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300"
										>{user.name.slice(0, 1)}</span
									>
									<span class="font-medium text-gray-900 dark:text-white">{user.name}</span>
									<span class="ml-1.5 text-[10px] text-gray-400">{user.email}</span>
								</td>
								<td class="px-2.5 py-1.5 text-right"
									>{Math.round(user.count * scale).toLocaleString()}</td
								>
								<td class="px-2.5 py-1.5 text-right"
									>{formatNumber(Math.round(user.tokens * scale))}</td
								>
							</tr>
						{:else}
							<tr><td colspan="4" class="px-2.5 py-3 text-center text-gray-400">暂无数据</td></tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	</div>

	<p class="mt-1.5 pr-1 text-right text-[10px] text-gray-400">
		ⓘ 消息条数仅统计模型的回复（不含用户发送的消息）。
	</p>
</section>

{#if selectedModel}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget) selectedModel = null;
		}}
	>
		<div
			class="w-full max-w-lg rounded-2xl border border-gray-200 bg-white p-5 shadow-2xl dark:border-gray-700 dark:bg-gray-900"
			role="dialog"
			aria-modal="true"
			aria-labelledby="model-detail-title"
			tabindex="-1"
		>
			<div class="flex items-start justify-between">
				<div>
					<h2 id="model-detail-title" class="text-lg font-semibold">{selectedModel.name}</h2>
					<p class="mt-1 text-xs text-gray-500">
						模型使用明细 · {periods.find((item) => item.id === period)?.label}
					</p>
				</div>
				<button
					class="rounded-lg px-2 py-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
					onclick={() => (selectedModel = null)}
					aria-label="关闭">×</button
				>
			</div>
			<div class="mt-5 grid grid-cols-2 gap-3">
				<div class="rounded-xl border border-gray-200 p-3 dark:border-gray-800">
					<p class="text-xs text-gray-500">消息数</p>
					<p class="mt-1 text-xl font-semibold">{selectedModel.count.toLocaleString()}</p>
				</div>
				<div class="rounded-xl border border-gray-200 p-3 dark:border-gray-800">
					<p class="text-xs text-gray-500">Token 用量</p>
					<p class="mt-1 text-xl font-semibold">{formatNumber(selectedModel.tokens)}</p>
				</div>
			</div>
			<div class="mt-5 flex justify-end">
				<button
					class="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white dark:bg-white dark:text-gray-900"
					onclick={() => (selectedModel = null)}>完成</button
				>
			</div>
		</div>
	</div>
{/if}
