<script lang="ts">
	type Tag = { tag: string; count: number };
	type Model = { id: string; name: string; rating: number | null; won: number | null; lost: number | null; topTags: Tag[]; activity: { date: string; won: number; lost: number }[] };
	const seedModels: Model[] = [
		{ id: 'tagent-chat', name: 'TAgent Chat', rating: 1284, won: 186, lost: 91, topTags: [{ tag: '代码', count: 48 }, { tag: '推理', count: 36 }, { tag: '写作', count: 22 }], activity: [] },
		{ id: 'qwen-2.5', name: 'Qwen 2.5', rating: 1258, won: 164, lost: 112, topTags: [{ tag: '中文', count: 53 }, { tag: '知识问答', count: 31 }], activity: [] },
		{ id: 'deepseek-v3', name: 'DeepSeek V3', rating: 1231, won: 151, lost: 127, topTags: [{ tag: '推理', count: 47 }, { tag: '数学', count: 28 }], activity: [] },
		{ id: 'gpt-4o', name: 'GPT-4o', rating: 1217, won: 139, lost: 132, topTags: [{ tag: '多模态', count: 29 }, { tag: '写作', count: 26 }], activity: [] },
		{ id: 'arena-model', name: 'Arena Model', rating: 1195, won: 103, lost: 118, topTags: [{ tag: '对话', count: 21 }], activity: [] },
		{ id: 'local-qwen', name: 'Local Qwen', rating: null, won: null, lost: null, topTags: [], activity: [] }
	];
	const makeActivity = (modelIndex: number) => Array.from({ length: 42 }, (_, index) => {
		const date = new Date();
		date.setDate(date.getDate() - (41 - index));
		const won = Math.max(0, Math.round(2 + 2.5 * Math.sin(index * 0.73 + modelIndex) + ((index + modelIndex * 3) % 4)));
		const lost = Math.max(0, Math.round(1.4 + 1.8 * Math.cos(index * 0.51 + modelIndex * 0.8) + ((index + modelIndex) % 3)));
		return { date: date.toISOString().slice(0, 10), won, lost };
	});
	const models = $state<Model[]>(seedModels.map((model, index) => ({ ...model, activity: makeActivity(index) })));

	let query = $state('');
	let sortKey = $state<'rank' | 'name' | 'rating' | 'won' | 'lost'>('rating');
	let sortDirection = $state<'asc' | 'desc'>('desc');
	let selectedModel = $state<Model | null>(null);
	let selectedRange = $state<'30d' | '1y' | 'all'>('30d');

	const filteredModels = $derived(models.filter((model) => `${model.name} ${model.id}`.toLowerCase().includes(query.trim().toLowerCase())));
	const sortedModels = $derived([...filteredModels].sort((a, b) => {
		if (sortKey === 'name') return sortDirection === 'asc' ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name);
		const rankOf = (model: Model) => sortKey === 'won' ? (model.won ?? -1) : sortKey === 'lost' ? (model.lost ?? -1) : (model.rating ?? -1);
		return sortDirection === 'asc' ? rankOf(a) - rankOf(b) : rankOf(b) - rankOf(a);
	}));
	const visibleActivity = $derived(selectedModel ? selectedModel.activity.filter((item) => selectedRange === '30d' || selectedRange === 'all' || item.date >= new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10)) : []);
	const chartScale = $derived(Math.max(1, ...visibleActivity.flatMap((item) => [item.won, item.lost])));
	const sortedActivity = $derived([...visibleActivity].map((item) => ({ ...item, total: item.won + item.lost })).sort((a, b) => a.date.localeCompare(b.date)));
	const aggregateActivity = $derived(selectedRange === '30d' ? sortedActivity.slice(-30) : selectedRange === '1y' ? sortedActivity : sortedActivity);

	function sortBy(key: typeof sortKey) {
		if (sortKey === key) sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
		else { sortKey = key; sortDirection = key === 'name' ? 'asc' : 'desc'; }
	}

	function openModel(model: Model) {
		selectedRange = '30d';
		selectedModel = model;
	}

	function winRate(value: number | null, total: number) {
		return value === null || total === 0 ? '-' : `${((value / total) * 100).toFixed(1)}%`;
	}
</script>

<section class="min-h-full text-gray-900 dark:text-gray-100">
	<header class="sticky top-0 z-10 flex flex-col justify-between gap-1 bg-white py-1 dark:bg-gray-900 md:flex-row md:items-center">
		<h1 class="flex shrink-0 items-center gap-2 px-0.5 text-lg font-medium">排行榜 <span class="text-sm text-gray-500">{models.length}</span></h1>
		<label class="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-gray-500 transition focus-within:bg-gray-100 dark:focus-within:bg-gray-850 md:max-w-sm">
			<svg viewBox="0 0 20 20" fill="currentColor" class="size-4 shrink-0" aria-hidden="true"><path fill-rule="evenodd" d="M9 3.5a5.5 5.5 0 1 0 3.445 9.788l3.328 3.328a.75.75 0 1 0 1.06-1.06l-3.328-3.329A5.5 5.5 0 0 0 9 3.5ZM5 9a4 4 0 1 1 8 0 4 4 0 0 1-8 0Z" clip-rule="evenodd" /></svg>
			<input class="w-full bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-500 dark:text-gray-100" bind:value={query} placeholder="搜索模型" aria-label="搜索模型" />
		</label>
	</header>

	<div class="overflow-x-auto whitespace-nowrap">
		{#if sortedModels.length === 0}
			<div class="py-10 text-center text-sm text-gray-500">未找到模型</div>
		{:else}
			<table class="w-full min-w-[660px] border-collapse text-left text-xs text-gray-500 dark:text-gray-400">
				<thead class="text-[10px] uppercase text-gray-800 dark:text-gray-200">
					<tr class="border-b border-gray-100 dark:border-gray-850/40">
						{#each [{ key: 'rank', label: '排名' }, { key: 'name', label: '模型' }, { key: 'rating', label: '评分' }, { key: 'won', label: '胜场' }, { key: 'lost', label: '负场' }] as column (column.key)}
							<th class="cursor-pointer select-none px-2.5 py-2 {column.key === 'rating' || column.key === 'won' || column.key === 'lost' ? 'text-right' : ''}">
								<button class="inline-flex items-center gap-1" onclick={() => sortBy(column.key as typeof sortKey)}>{column.label}{#if sortKey === column.key}<span class="font-normal">{sortDirection === 'asc' ? '↑' : '↓'}</span>{/if}</button>
							</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each sortedModels as model, index (model.id)}
						{@const total = (model.won ?? 0) + (model.lost ?? 0)}
						<tr class="group cursor-pointer text-gray-700 transition hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-850/50" onclick={() => openModel(model)} onkeydown={(event) => { if (event.key === 'Enter') openModel(model); }} role="button" tabindex="0" aria-label={`查看 ${model.name} 评估详情`}>
							<td class="px-3 py-2 font-medium text-gray-900 dark:text-white">{model.rating === null ? '-' : index + 1}</td>
							<td class="px-3 py-2"><span class="inline-flex items-center gap-2"><span class="flex size-5 shrink-0 items-center justify-center rounded-full bg-blue-100 text-[9px] font-semibold text-blue-700 dark:bg-blue-950 dark:text-blue-300">{model.name.slice(0, 1)}</span><span class="font-medium text-gray-800 dark:text-gray-200">{model.name}</span></span></td>
							<td class="px-3 py-2 text-right font-medium text-gray-900 dark:text-white">{model.rating ?? '-'}</td>
							<td class="w-20 px-3 py-2 text-right font-medium text-emerald-600 dark:text-green-500">{#if model.won === null}-{:else}<span class="group-hover:hidden">{model.won}</span><span class="hidden group-hover:inline">{winRate(model.won, total)}</span>{/if}</td>
							<td class="w-20 px-3 py-2 text-right font-medium text-red-600 dark:text-red-500">{#if model.lost === null}-{:else}<span class="group-hover:hidden">{model.lost}</span><span class="hidden group-hover:inline">{winRate(model.lost, total)}</span>{/if}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>

	<div class="mt-2 text-right text-[10px] text-gray-500">ⓘ 排行榜基于 Elo 评分系统，数据为 mock 模拟并非实时统计。排行榜处于测试阶段，评分算法可能调整。</div>
</section>

{#if selectedModel}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="presentation" onclick={(event) => { if (event.target === event.currentTarget) selectedModel = null; }}>
		<div class="w-full max-w-lg rounded-2xl border border-gray-200 bg-white text-gray-900 shadow-2xl dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100" role="dialog" aria-modal="true" aria-labelledby="evaluation-model-title" tabindex="-1">
			<header class="flex items-center justify-between px-5 pb-2 pt-4"><h2 id="evaluation-model-title" class="truncate text-lg font-medium" title={`${selectedModel.name} (${selectedModel.id})`}>{selectedModel.name}</h2><button class="rounded-md p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" onclick={() => selectedModel = null} aria-label="关闭"><svg viewBox="0 0 20 20" fill="currentColor" class="size-5"><path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" /></svg></button></header>
			<div class="px-5 pb-5">
				<div class="mb-2 flex items-center justify-between"><h3 class="text-xs font-medium uppercase tracking-wide text-gray-500">活动</h3><div class="inline-flex rounded-full bg-gray-100 p-0.5 dark:bg-gray-800">{#each [{ key: '30d', label: '30D' }, { key: '1y', label: '1Y' }, { key: 'all', label: '全部' }] as range (range.key)}<button class="rounded-full px-2.5 py-0.5 text-xs transition {selectedRange === range.key ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white' : 'text-gray-500 hover:text-gray-800 dark:hover:text-gray-200'}" onclick={() => selectedRange = range.key as typeof selectedRange}>{range.label}</button>{/each}</div></div>
				{#if aggregateActivity.every((item) => item.won === 0 && item.lost === 0)}
					<div class="flex h-40 items-center justify-center text-sm text-gray-500">暂无活动数据</div>
				{:else}
					<div class="relative mt-2 h-48 border-b border-gray-200 dark:border-gray-700"><div class="absolute inset-0 flex flex-col justify-between pb-4" aria-hidden="true"><div class="border-t border-gray-100 dark:border-gray-800"></div><div class="border-t border-gray-100 dark:border-gray-800"></div><div class="border-t border-gray-100 dark:border-gray-800"></div></div><div class="absolute inset-0 flex items-end gap-px px-1 pb-4">{#each aggregateActivity as item (item.date)}<div class="group relative flex h-full min-w-0 flex-1 items-end justify-center gap-px" title={`${item.date} · 胜 ${item.won} / 负 ${item.lost}`}><div class="w-1/2 rounded-t-sm bg-sky-500/80" style={`height:${(item.won / chartScale) * 48}%`}></div><div class="flex w-1/2 flex-col justify-end"><div class="rounded-b-sm bg-orange-500/80" style={`height:${(item.lost / chartScale) * 48}%`}></div></div><span class="pointer-events-none absolute bottom-full z-10 hidden whitespace-nowrap rounded bg-gray-900 px-2 py-1 text-[10px] text-white group-hover:block">胜 {item.won} · 负 {item.lost}</span></div>{/each}</div></div>
				{/if}
				<div class="mb-2 mt-4 text-xs font-medium uppercase tracking-wide text-gray-500">标签</div>
				{#if selectedModel.topTags.length}<div class="-mx-1 flex flex-wrap gap-1">{#each selectedModel.topTags as tag (tag.tag)}<span class="rounded-full bg-gray-100 px-2 py-0.5 text-xs dark:bg-gray-850">{tag.tag} <span class="font-medium text-gray-500">{tag.count}</span></span>{/each}</div>{:else}<span class="text-sm text-gray-500">-</span>{/if}
				<div class="mt-5 flex justify-end"><button class="rounded-full bg-gray-900 px-4 py-1.5 text-sm font-medium text-white dark:bg-white dark:text-gray-900" onclick={() => selectedModel = null}>关闭</button></div>
			</div>
		</div>
	</div>
{/if}
