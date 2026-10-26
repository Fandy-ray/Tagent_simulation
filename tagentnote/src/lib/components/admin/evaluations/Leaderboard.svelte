<script lang="ts">
	import { onMount } from 'svelte';

	import {
		AdminError,
		getModelActivity,
		getModelStats,
		MODE_LABELS,
		percent,
		type ModelActivity,
		type ModelStat
	} from '$lib/apis/admin';

	type Range = '30d' | '90d' | '1y';
	const RANGE_DAYS: Record<Range, number> = { '30d': 30, '90d': 90, '1y': 365 };

	let models = $state<ModelStat[]>([]);
	let loading = $state(true);
	let loadError = $state('');
	let query = $state('');
	let sortKey = $state<'rank' | 'name' | 'rating' | 'won' | 'lost' | 'turns' | 'completion'>(
		'rating'
	);
	let sortDirection = $state<'asc' | 'desc'>('desc');
	let selectedModel = $state<ModelStat | null>(null);
	let selectedRange = $state<Range>('30d');
	let activity = $state<ModelActivity | null>(null);
	let activityError = $state('');

	const votes = (model: ModelStat) => model.thumbs_up + model.thumbs_down;
	// 名次只看有人评价过的：好评率高的在前，一样时评价多的在前
	const ranks = $derived(
		new Map(
			models
				.filter((model) => votes(model) > 0)
				.sort((a, b) => (b.thumbs_up_rate ?? 0) - (a.thumbs_up_rate ?? 0) || votes(b) - votes(a))
				.map((model, index) => [model.model, index + 1])
		)
	);

	const filteredModels = $derived(
		models.filter((model) => model.model.toLowerCase().includes(query.trim().toLowerCase()))
	);
	const sortedModels = $derived(
		[...filteredModels].sort((a, b) => {
			if (sortKey === 'name')
				return sortDirection === 'asc'
					? a.model.localeCompare(b.model)
					: b.model.localeCompare(a.model);
			const valueOf = (model: ModelStat) =>
				sortKey === 'won'
					? model.thumbs_up
					: sortKey === 'lost'
						? model.thumbs_down
						: sortKey === 'turns'
							? model.chat_turns
							: sortKey === 'completion'
								? (model.completion_rate ?? -1)
								: // 「排名」「好评率」都按名次：没名次的排最后
									-(ranks.get(model.model) ?? Number.MAX_SAFE_INTEGER);
			return sortDirection === 'asc' ? valueOf(a) - valueOf(b) : valueOf(b) - valueOf(a);
		})
	);
	const chartScale = $derived(
		Math.max(1, ...(activity?.daily ?? []).flatMap((item) => [item.thumbs_up, item.thumbs_down]))
	);

	function sortBy(key: typeof sortKey) {
		if (sortKey === key) sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
		else {
			sortKey = key;
			sortDirection = key === 'name' ? 'asc' : 'desc';
		}
	}

	const failure = (error: unknown) =>
		error instanceof AdminError ? error.message : '读取失败，再试一次。';

	async function refresh() {
		try {
			models = await getModelStats();
			loadError = '';
		} catch (error) {
			loadError = failure(error);
		} finally {
			loading = false;
		}
	}

	// 快速来回切模型、切 30D / 90D 时，先发的请求可能后回来：只认最后发出的那一个
	let activityRequest = 0;

	async function loadActivity() {
		if (!selectedModel) return;
		const request = ++activityRequest;
		activity = null;
		activityError = '';
		try {
			const result = await getModelActivity(selectedModel.model, RANGE_DAYS[selectedRange]);
			if (request === activityRequest) activity = result;
		} catch (error) {
			if (request === activityRequest) activityError = failure(error);
		}
	}

	function openModel(model: ModelStat) {
		selectedRange = '30d';
		selectedModel = model;
		void loadActivity();
	}

	function chooseRange(range: Range) {
		selectedRange = range;
		void loadActivity();
	}

	function winRate(value: number, total: number) {
		return total === 0 ? '-' : `${((value / total) * 100).toFixed(1)}%`;
	}

	onMount(refresh);
</script>

<section class="min-h-full text-gray-900 dark:text-gray-100">
	<header
		class="sticky top-0 z-10 flex flex-col justify-between gap-1 bg-white py-1 md:flex-row md:items-center dark:bg-gray-900"
	>
		<h1 class="flex shrink-0 items-center gap-2 px-0.5 text-lg font-medium">
			排行榜 <span class="text-sm text-gray-500">{models.length}</span>
		</h1>
		<label
			class="dark:focus-within:bg-gray-850 flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-gray-500 transition focus-within:bg-gray-100 md:max-w-sm"
		>
			<svg viewBox="0 0 20 20" fill="currentColor" class="size-4 shrink-0" aria-hidden="true"
				><path
					fill-rule="evenodd"
					d="M9 3.5a5.5 5.5 0 1 0 3.445 9.788l3.328 3.328a.75.75 0 1 0 1.06-1.06l-3.328-3.329A5.5 5.5 0 0 0 9 3.5ZM5 9a4 4 0 1 1 8 0 4 4 0 0 1-8 0Z"
					clip-rule="evenodd"
				/></svg
			>
			<input
				class="w-full bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-500 dark:text-gray-100"
				bind:value={query}
				placeholder="搜索模型"
				aria-label="搜索模型"
			/>
		</label>
	</header>

	{#if loadError}<div
			class="mb-2 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200"
			role="alert"
		>
			{loadError}
		</div>{/if}

	<div class="overflow-x-auto whitespace-nowrap">
		{#if sortedModels.length === 0}
			<div class="py-10 text-center text-sm text-gray-500">
				{loading
					? '正在读取…'
					: models.length
						? '未找到模型'
						: '还没有记录：学生用过之后，这里按模型统计好评率和答完率'}
			</div>
		{:else}
			<table
				class="w-full min-w-[660px] border-collapse text-left text-xs text-gray-500 dark:text-gray-400"
			>
				<thead class="text-[10px] text-gray-800 uppercase dark:text-gray-200">
					<tr class="dark:border-gray-850/40 border-b border-gray-100">
						{#each [{ key: 'rank', label: '排名' }, { key: 'name', label: '模型' }, { key: 'rating', label: '好评率' }, { key: 'won', label: '有帮助' }, { key: 'lost', label: '没帮助' }, { key: 'turns', label: '答疑' }, { key: 'completion', label: '答完率' }] as column (column.key)}
							<th
								class="cursor-pointer px-2.5 py-2 select-none {column.key === 'rank' ||
								column.key === 'name'
									? ''
									: 'text-right'}"
							>
								<button
									class="inline-flex items-center gap-1"
									onclick={() => sortBy(column.key as typeof sortKey)}
									>{column.label}{#if sortKey === column.key}<span class="font-normal"
											>{sortDirection === 'asc' ? '↑' : '↓'}</span
										>{/if}</button
								>
							</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each sortedModels as model (model.model)}
						{@const total = votes(model)}
						<tr
							class="group dark:hover:bg-gray-850/50 cursor-pointer text-gray-700 transition hover:bg-gray-50 dark:text-gray-300"
							onclick={() => openModel(model)}
							onkeydown={(event) => {
								if (event.key === 'Enter') openModel(model);
							}}
							role="button"
							tabindex="0"
							aria-label={`查看 ${model.model} 评估详情`}
						>
							<td class="px-3 py-2 font-medium text-gray-900 dark:text-white"
								>{ranks.get(model.model) ?? '-'}</td
							>
							<td class="px-3 py-2"
								><span class="inline-flex items-center gap-2"
									><span
										class="flex size-5 shrink-0 items-center justify-center rounded-full bg-blue-100 text-[9px] font-semibold text-blue-700 dark:bg-blue-950 dark:text-blue-300"
										>{model.model.slice(0, 1).toUpperCase()}</span
									><span class="font-medium text-gray-800 dark:text-gray-200">{model.model}</span
									></span
								></td
							>
							<td class="px-3 py-2 text-right font-medium text-gray-900 dark:text-white"
								>{percent(model.thumbs_up_rate)}</td
							>
							<td class="w-20 px-3 py-2 text-right font-medium text-emerald-600 dark:text-green-500"
								>{#if total === 0}-{:else}<span class="group-hover:hidden">{model.thumbs_up}</span
									><span class="hidden group-hover:inline">{winRate(model.thumbs_up, total)}</span
									>{/if}</td
							>
							<td class="w-20 px-3 py-2 text-right font-medium text-red-600 dark:text-red-500"
								>{#if total === 0}-{:else}<span class="group-hover:hidden">{model.thumbs_down}</span
									><span class="hidden group-hover:inline">{winRate(model.thumbs_down, total)}</span
									>{/if}</td
							>
							<td class="w-20 px-3 py-2 text-right">{model.chat_turns.toLocaleString()}</td>
							<td class="w-20 px-3 py-2 text-right">{percent(model.completion_rate)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>

	<div class="mt-2 text-right text-[10px] text-gray-500">
		ⓘ 好评率 = 学生点「有帮助」的次数 / 点过评价的次数，没人评价过的模型不排名；答完率 =
		正常答完的次数 / 全部答疑次数（中途停止、出错都不算）。
	</div>
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
			class="w-full max-w-lg rounded-2xl border border-gray-200 bg-white text-gray-900 shadow-2xl dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
			role="dialog"
			aria-modal="true"
			aria-labelledby="evaluation-model-title"
			tabindex="-1"
		>
			<header class="flex items-center justify-between px-5 pt-4 pb-2">
				<h2
					id="evaluation-model-title"
					class="truncate text-lg font-medium"
					title={selectedModel.model}
				>
					{selectedModel.model}
				</h2>
				<button
					class="rounded-md p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
					onclick={() => (selectedModel = null)}
					aria-label="关闭"
					><svg viewBox="0 0 20 20" fill="currentColor" class="size-5"
						><path
							d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z"
						/></svg
					></button
				>
			</header>
			<div class="px-5 pb-5">
				<div class="mb-2 flex items-center justify-between">
					<h3 class="text-xs font-medium tracking-wide text-gray-500 uppercase">活动</h3>
					<div class="inline-flex rounded-full bg-gray-100 p-0.5 dark:bg-gray-800">
						{#each [{ key: '30d', label: '30D' }, { key: '90d', label: '90D' }, { key: '1y', label: '1Y' }] as range (range.key)}<button
								class="rounded-full px-2.5 py-0.5 text-xs transition {selectedRange === range.key
									? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white'
									: 'text-gray-500 hover:text-gray-800 dark:hover:text-gray-200'}"
								onclick={() => chooseRange(range.key as Range)}>{range.label}</button
							>{/each}
					</div>
				</div>
				{#if activityError}
					<div class="flex h-40 items-center justify-center text-sm text-red-600">
						{activityError}
					</div>
				{:else if !activity}
					<div class="flex h-40 items-center justify-center text-sm text-gray-500">正在读取…</div>
				{:else if activity.daily.every((item) => item.thumbs_up === 0 && item.thumbs_down === 0)}
					<div class="flex h-40 items-center justify-center text-sm text-gray-500">
						这段时间没有人评价过
					</div>
				{:else}
					<div class="relative mt-2 h-48 border-b border-gray-200 dark:border-gray-700">
						<div class="absolute inset-0 flex flex-col justify-between pb-4" aria-hidden="true">
							<div class="border-t border-gray-100 dark:border-gray-800"></div>
							<div class="border-t border-gray-100 dark:border-gray-800"></div>
							<div class="border-t border-gray-100 dark:border-gray-800"></div>
						</div>
						<div class="absolute inset-0 flex items-end gap-px px-1 pb-4">
							{#each activity.daily as item (item.day)}<div
									class="group relative flex h-full min-w-0 flex-1 items-end justify-center gap-px"
									title={`${item.day} · 有帮助 ${item.thumbs_up} / 没帮助 ${item.thumbs_down} · 答疑 ${item.chat_turns}`}
								>
									<div
										class="w-1/2 rounded-t-sm bg-sky-500/80"
										style={`height:${(item.thumbs_up / chartScale) * 48}%`}
									></div>
									<div class="flex h-full w-1/2 flex-col justify-end">
										<div
											class="rounded-t-sm bg-orange-500/80"
											style={`height:${(item.thumbs_down / chartScale) * 48}%`}
										></div>
									</div>
									<span
										class="pointer-events-none absolute bottom-full z-10 hidden rounded bg-gray-900 px-2 py-1 text-[10px] whitespace-nowrap text-white group-hover:block"
										>{item.day} · 👍 {item.thumbs_up} · 👎 {item.thumbs_down}</span
									>
								</div>{/each}
						</div>
					</div>
				{/if}
				<div class="mt-4 mb-2 text-xs font-medium tracking-wide text-gray-500 uppercase">
					用在哪里
				</div>
				{#if activity && Object.keys(activity.chat_modes).length}<div
						class="-mx-1 flex flex-wrap gap-1"
					>
						{#each Object.entries(activity.chat_modes) as [mode, count] (mode)}<span
								class="dark:bg-gray-850 rounded-full bg-gray-100 px-2 py-0.5 text-xs"
								>{MODE_LABELS[mode] ?? mode}
								<span class="font-medium text-gray-500">{count}</span></span
							>{/each}
					</div>{:else}<span class="text-sm text-gray-500">-</span>{/if}
				<div class="mt-5 flex justify-end">
					<button
						class="rounded-full bg-gray-900 px-4 py-1.5 text-sm font-medium text-white dark:bg-white dark:text-gray-900"
						onclick={() => (selectedModel = null)}>关闭</button
					>
				</div>
			</div>
		</div>
	</div>
{/if}
