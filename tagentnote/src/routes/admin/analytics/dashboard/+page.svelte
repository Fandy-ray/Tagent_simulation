<script lang="ts">
	import { onMount } from 'svelte';

	import {
		AdminError,
		getLearningAnalytics,
		getModelStats,
		MODE_LABELS,
		percent,
		type ActiveStudent,
		type DailyActivity,
		type LearningAnalytics,
		type ModelStat
	} from '$lib/apis/admin';

	type Period = '7d' | '14d' | '30d' | '90d' | '365d';
	type Series = { key: keyof Omit<DailyActivity, 'day' | 'active_students'>; name: string };

	const periods: { id: Period; label: string; days: number }[] = [
		{ id: '7d', label: '最近 7 天', days: 7 },
		{ id: '14d', label: '最近 14 天', days: 14 },
		{ id: '30d', label: '最近 30 天', days: 30 },
		{ id: '90d', label: '最近 90 天', days: 90 },
		{ id: '365d', label: '最近一年', days: 365 }
	];
	const chartColors = ['#3b82f6', '#10b981', '#f59e0b', '#a78bfa'];
	const series: Series[] = [
		{ key: 'chat_turns', name: '答疑' },
		{ key: 'essay_reviews', name: '论文批改' },
		{ key: 'exams_generated', name: '出卷' },
		{ key: 'exams_reviewed', name: '交卷' }
	];

	let period = $state<Period>('7d');
	let analytics = $state<LearningAnalytics | null>(null);
	let models = $state<ModelStat[]>([]);
	let loadError = $state('');
	let loading = $state(false);
	let modelSort = $state<'name' | 'count' | 'duration' | 'percentage'>('count');
	let modelDirection = $state<'asc' | 'desc'>('desc');
	let userSort = $state<'name' | 'count' | 'essays' | 'exams'>('count');
	let userDirection = $state<'asc' | 'desc'>('desc');
	let selectedModel = $state<ModelStat | null>(null);
	let hoverIndex = $state<number | null>(null);

	try {
		const saved = localStorage.getItem('admin-analytics-period');
		if (saved && periods.some((item) => item.id === saved)) period = saved as Period;
	} catch {
		/* 读不到就用默认 */
	}

	const dayCount = $derived(periods.find((item) => item.id === period)?.days ?? 7);
	const totals = $derived(
		analytics?.totals ?? { chat_turns: 0, essay_reviews: 0, exams_generated: 0, exams_reviewed: 0 }
	);
	const modelTurns = $derived(models.reduce((sum, model) => sum + model.chat_turns, 0));
	const nameOf = (user: ActiveStudent) => user.name.trim() || '未填昵称';
	const sortedModels = $derived(
		[...models].sort((a, b) => {
			const result =
				modelSort === 'name'
					? a.model.localeCompare(b.model)
					: modelSort === 'duration'
						? (a.avg_duration_ms ?? -1) - (b.avg_duration_ms ?? -1)
						: a.chat_turns - b.chat_turns;
			return modelDirection === 'asc' ? result : -result;
		})
	);
	const sortedUsers = $derived(
		[...(analytics?.students ?? [])].sort((a, b) => {
			const result =
				userSort === 'name'
					? nameOf(a).localeCompare(nameOf(b))
					: userSort === 'essays'
						? a.essay_reviews - b.essay_reviews
						: userSort === 'exams'
							? a.exams_reviewed - b.exams_reviewed
							: a.chat_turns - b.chat_turns;
			return userDirection === 'asc' ? result : -result;
		})
	);
	const chartData = $derived(
		(analytics?.daily ?? []).map((point) => ({
			label: new Date(`${point.day}T00:00:00`).toLocaleDateString('zh-CN', {
				month: 'numeric',
				day: 'numeric'
			}),
			values: series.map((item) => point[item.key])
		}))
	);
	const maxChartValue = $derived(Math.max(1, ...chartData.flatMap((point) => point.values)));
	const linePoints = (seriesIndex: number) =>
		chartData
			.map((point, index) => {
				const x = chartData.length <= 1 ? 50 : (index / (chartData.length - 1)) * 100;
				const y = 100 - (point.values[seriesIndex] / maxChartValue) * 96;
				return `${x},${y}`;
			})
			.join(' ');
	const seconds = (ms: number | null) => (ms === null ? '—' : `${(ms / 1000).toFixed(1)} 秒`);

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

	// 快速来回切时间范围时，先发的请求可能后回来（一年的比七天的慢）：只认最后发出的那一次
	let latestRequest = 0;

	async function refresh() {
		const request = ++latestRequest;
		loading = true;
		try {
			const result = await Promise.all([getLearningAnalytics(dayCount), getModelStats(dayCount)]);
			if (request !== latestRequest) return;
			[analytics, models] = result;
			loadError = '';
		} catch (error) {
			if (request !== latestRequest) return;
			loadError = error instanceof AdminError ? error.message : '读取失败，再试一次。';
		} finally {
			if (request === latestRequest) loading = false;
		}
	}

	function updatePeriod(value: Period) {
		period = value;
		try {
			localStorage.setItem('admin-analytics-period', value);
		} catch {
			/* 记不住也不要紧 */
		}
		void refresh();
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

	onMount(refresh);
</script>

<svelte:head><title>分析 | 管理员面板</title></svelte:head>

<section class="w-full px-2 pb-6 text-gray-900 dark:text-gray-100">
	<header
		class="sticky top-0 z-10 flex items-center justify-between gap-3 bg-white/95 py-1.5 backdrop-blur dark:bg-gray-900/95"
	>
		<h1 class="px-0.5 text-sm font-medium">分析</h1>
		<div class="flex items-center gap-2">
			{#if loading}<span class="text-[10px] text-gray-400">读取中…</span>{/if}
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

	{#if loadError}<div
			class="mb-2 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200"
			role="alert"
		>
			{loadError}
		</div>{/if}

	<div
		class="flex flex-wrap items-center gap-x-4 gap-y-0.5 px-0.5 pb-1 text-xs text-gray-500 dark:text-gray-400"
	>
		<span
			><span class="font-medium text-gray-900 dark:text-gray-300"
				>{totals.chat_turns.toLocaleString()}</span
			> 次答疑</span
		>
		<span
			><span class="font-medium text-gray-900 dark:text-gray-300"
				>{totals.essay_reviews.toLocaleString()}</span
			> 篇论文批改</span
		>
		<span
			><span class="font-medium text-gray-900 dark:text-gray-300"
				>{totals.exams_generated.toLocaleString()}</span
			>
			份试卷 · {totals.exams_reviewed.toLocaleString()} 份交卷</span
		>
		<span
			><span class="font-medium text-gray-900 dark:text-gray-300"
				>{analytics?.active_students ?? 0}</span
			> 位学生</span
		>
		{#if analytics && Object.keys(analytics.chat_modes).length}
			<span class="text-gray-400"
				>（{Object.entries(analytics.chat_modes)
					.map(([mode, count]) => `${MODE_LABELS[mode] ?? mode} ${count}`)
					.join(' · ')}）</span
			>
		{/if}
	</div>

	<div class="px-0.5 pb-1 text-xs font-medium text-gray-600 dark:text-gray-400">每日活动</div>

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
				aria-label="每日答疑、批改、出卷、交卷数"
				onmousemove={(event) => {
					const rect = event.currentTarget.getBoundingClientRect();
					const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
					hoverIndex = Math.round(ratio * (chartData.length - 1));
				}}
				onmouseleave={() => (hoverIndex = null)}
			>
				{#each series as item, index (item.key)}
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
				{#each series as item, index (item.key)}
					<div class="flex items-center justify-between gap-3 py-0.5">
						<span style={`color:${chartColors[index]}`}>{item.name}</span>
						<span class="text-gray-900 tabular-nums dark:text-white"
							>{chartData[hoverIndex]?.values[index]}</span
						>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<div class="flex flex-wrap gap-3 px-0.5 pt-1 text-[10px] text-gray-500">
		{#each series as item, index (item.key)}
			<span class="inline-flex items-center gap-1"
				><span class="inline-block size-2 rounded-full" style={`background:${chartColors[index]}`}
				></span>{item.name}</span
			>
		{/each}
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
									>答疑{#if modelSort === 'count'}<span class="font-normal"
											>{modelDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								></th
							>
							<th class="px-2.5 py-2 text-right"
								><button
									class="inline-flex items-center gap-1"
									onclick={() => sortModels('duration')}
									>平均耗时{#if modelSort === 'duration'}<span class="font-normal"
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
						{#each sortedModels as model, index (model.model)}
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
										style={`background:${chartColors[index % chartColors.length]}`}
									></span>{model.model}
								</td>
								<td class="px-2.5 py-1.5 text-right">{model.chat_turns.toLocaleString()}</td>
								<td class="px-2.5 py-1.5 text-right">{seconds(model.avg_duration_ms)}</td>
								<td class="px-2.5 py-1.5 text-right text-gray-400"
									>{modelTurns ? ((model.chat_turns / modelTurns) * 100).toFixed(1) : '0.0'}%</td
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
									>答疑{#if userSort === 'count'}<span class="font-normal"
											>{userDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								></th
							>
							<th class="px-2.5 py-2 text-right"
								><button class="inline-flex items-center gap-1" onclick={() => sortUsers('essays')}
									>批改{#if userSort === 'essays'}<span class="font-normal"
											>{userDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								></th
							>
							<th class="px-2.5 py-2 text-right"
								><button class="inline-flex items-center gap-1" onclick={() => sortUsers('exams')}
									>交卷{#if userSort === 'exams'}<span class="font-normal"
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
										>{nameOf(user).slice(0, 1)}</span
									>
									<span class="font-medium text-gray-900 dark:text-white">{nameOf(user)}</span>
									<span class="ml-1.5 font-mono text-[10px] text-gray-400" title={user.id}
										>{user.id.slice(0, 8)}</span
									>
								</td>
								<td class="px-2.5 py-1.5 text-right">{user.chat_turns.toLocaleString()}</td>
								<td class="px-2.5 py-1.5 text-right">{user.essay_reviews.toLocaleString()}</td>
								<td class="px-2.5 py-1.5 text-right">{user.exams_reviewed.toLocaleString()}</td>
							</tr>
						{:else}
							<tr><td colspan="5" class="px-2.5 py-3 text-center text-gray-400">暂无数据</td></tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	</div>

	<p class="mt-1.5 pr-1 text-right text-[10px] text-gray-400">
		ⓘ 「答疑」只算课程答疑和论文助手，模型用量里还含 Playground 的直接对话；按本机时区的自然日统计。
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
					<h2 id="model-detail-title" class="text-lg font-semibold">{selectedModel.model}</h2>
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
					<p class="text-xs text-gray-500">答疑次数</p>
					<p class="mt-1 text-xl font-semibold">{selectedModel.chat_turns.toLocaleString()}</p>
				</div>
				<div class="rounded-xl border border-gray-200 p-3 dark:border-gray-800">
					<p class="text-xs text-gray-500">平均耗时</p>
					<p class="mt-1 text-xl font-semibold">{seconds(selectedModel.avg_duration_ms)}</p>
				</div>
				<div class="rounded-xl border border-gray-200 p-3 dark:border-gray-800">
					<p class="text-xs text-gray-500">答完率</p>
					<p class="mt-1 text-xl font-semibold">{percent(selectedModel.completion_rate)}</p>
					<p class="mt-0.5 text-[10px] text-gray-400">
						中途停止或出错 {selectedModel.interrupted} 次
					</p>
				</div>
				<div class="rounded-xl border border-gray-200 p-3 dark:border-gray-800">
					<p class="text-xs text-gray-500">好评率</p>
					<p class="mt-1 text-xl font-semibold">{percent(selectedModel.thumbs_up_rate)}</p>
					<p class="mt-0.5 text-[10px] text-gray-400">
						👍 {selectedModel.thumbs_up} · 👎 {selectedModel.thumbs_down}
					</p>
				</div>
				<div class="rounded-xl border border-gray-200 p-3 dark:border-gray-800">
					<p class="text-xs text-gray-500">论文批改</p>
					<p class="mt-1 text-xl font-semibold">{selectedModel.essay_reviews}</p>
					<p class="mt-0.5 text-[10px] text-gray-400">平均 {selectedModel.essay_avg ?? '—'} 分</p>
				</div>
				<div class="rounded-xl border border-gray-200 p-3 dark:border-gray-800">
					<p class="text-xs text-gray-500">整卷</p>
					<p class="mt-1 text-xl font-semibold">{selectedModel.exams_reviewed}</p>
					<p class="mt-0.5 text-[10px] text-gray-400">
						平均得分率 {selectedModel.exam_avg_percent ?? '—'}{selectedModel.exam_avg_percent ===
						null
							? ''
							: '%'}
					</p>
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
