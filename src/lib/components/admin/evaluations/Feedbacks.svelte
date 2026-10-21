<script lang="ts">
	type Feedback = { id: number; userName: string; userEmail: string; modelId: string; siblingModels: string[]; rating: 1 | 0 | -1; reason: string; comment: string; tags: string[]; updatedAt: number; chatId: string; prompt: string; response: string };
	let items = $state<Feedback[]>([
		{ id: 1, userName: '林知夏', userEmail: 'lin.zx@example.com', modelId: 'TAgent Chat', siblingModels: ['Qwen 2.5', 'DeepSeek V3'], rating: 1, reason: '回答准确', comment: '步骤清晰，结果符合预期。', tags: ['准确', '代码'], updatedAt: Date.now() - 1000 * 60 * 12, chatId: 'chat-8f23a1', prompt: '请解释快速排序的平均时间复杂度。', response: '快速排序的平均时间复杂度为 O(n log n)，最坏情况下为 O(n²)。' },
		{ id: 2, userName: '陈嘉木', userEmail: 'chen.jm@example.com', modelId: 'Qwen 2.5', siblingModels: [], rating: -1, reason: '内容不准确', comment: '回答中的版本号有误。', tags: ['事实错误'], updatedAt: Date.now() - 1000 * 60 * 60 * 3, chatId: 'chat-4a118c', prompt: 'TypeScript 5.7 于哪年发布？', response: 'TypeScript 5.7 发布于 2023 年。' },
		{ id: 3, userName: '周予安', userEmail: 'zhou.ya@example.com', modelId: 'DeepSeek V3', siblingModels: ['TAgent Chat'], rating: 0, reason: '', comment: '两个回答都可以。', tags: ['对比'], updatedAt: Date.now() - 1000 * 60 * 60 * 25, chatId: 'chat-c17b03', prompt: '给出一个归纳法证明的例子。', response: '一个经典例子是证明前 n 个正整数之和等于 n(n+1)/2。' },
		{ id: 4, userName: '许清禾', userEmail: 'xu.qh@example.com', modelId: 'GPT-4o', siblingModels: [], rating: 1, reason: '表达更清晰', comment: '整体解释容易理解。', tags: ['解释', '写作'], updatedAt: Date.now() - 1000 * 60 * 60 * 49, chatId: 'chat-0bb903', prompt: '什么是向量数据库？', response: '向量数据库用于存储和检索向量嵌入，常用于语义搜索与 RAG。' },
		{ id: 5, userName: '沈星野', userEmail: 'shen.xy@example.com', modelId: 'TAgent Chat', siblingModels: [], rating: -1, reason: '没有遵循要求', comment: '', tags: ['格式'], updatedAt: Date.now() - 1000 * 60 * 60 * 90, chatId: 'chat-b76511', prompt: '请只返回 JSON。', response: '当然可以！下面是 JSON：...' },
		{ id: 6, userName: '顾言之', userEmail: 'gu.yz@example.com', modelId: 'Qwen 2.5', siblingModels: ['GPT-4o', 'TAgent Chat'], rating: 1, reason: '推理更完整', comment: '分析过程有帮助。', tags: ['推理'], updatedAt: Date.now() - 1000 * 60 * 60 * 130, chatId: 'chat-44ef88', prompt: '解释贝叶斯定理的直觉。', response: '贝叶斯定理描述了在获得新证据后如何更新一个假设的概率。' },
		{ id: 7, userName: '林知夏', userEmail: 'lin.zx@example.com', modelId: 'DeepSeek V3', siblingModels: [], rating: 0, reason: '', comment: '', tags: [], updatedAt: Date.now() - 1000 * 60 * 60 * 180, chatId: 'chat-1e10d2', prompt: '什么是哈希表？', response: '哈希表是一种通过哈希函数将键映射到数组索引的数据结构。' }
	]);
	let page = $state(1);
	let pageSize = 5;
	let sortKey = $state<'userName' | 'modelId' | 'rating' | 'updatedAt'>('updatedAt');
	let sortDirection = $state<'asc' | 'desc'>('desc');
	let selectedFeedback = $state<Feedback | null>(null);
	let menuFor = $state<number | null>(null);
	let exportNotice = $state('');

	const sortedItems = $derived([...items].sort((a, b) => {
		const result = sortKey === 'updatedAt' || sortKey === 'rating' ? a[sortKey] - b[sortKey] : a[sortKey].localeCompare(b[sortKey]);
		return sortDirection === 'asc' ? result : -result;
	}));
	const totalPages = $derived(Math.max(1, Math.ceil(items.length / pageSize)));
	const pageItems = $derived(sortedItems.slice((page - 1) * pageSize, page * pageSize));

	function sortBy(key: typeof sortKey) {
		if (sortKey === key) sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
		else { sortKey = key; sortDirection = 'asc'; }
		page = 1;
	}

	function timeAgo(timestamp: number) {
		const minutes = Math.max(1, Math.floor((Date.now() - timestamp) / 60000));
		if (minutes < 60) return `${minutes} 分钟前`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours} 小时前`;
		const days = Math.floor(hours / 24);
		return `${days} 天前`;
	}

	function exportFeedback() {
		const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const anchor = document.createElement('a');
		anchor.href = url;
		anchor.download = `feedback-history-mock-${Date.now()}.json`;
		anchor.click();
		URL.revokeObjectURL(url);
		exportNotice = '已导出当前 mock 反馈记录';
		setTimeout(() => exportNotice = '', 2500);
	}

	function deleteFeedback(id: number) {
		items = items.filter((item) => item.id !== id);
		if (selectedFeedback?.id === id) selectedFeedback = null;
		page = Math.min(page, totalPages);
		menuFor = null;
	}
</script>

<section class="min-h-full text-gray-900 dark:text-gray-100">
	<header class="mb-1 flex items-center justify-between gap-3">
		<h1 class="flex shrink-0 items-center gap-2 px-0.5 text-lg font-medium">反馈历史 <span class="text-sm text-gray-500">{items.length}</span></h1>
		{#if items.length}<button class="rounded-lg p-2 text-gray-500 transition hover:bg-gray-100 dark:hover:bg-gray-850" onclick={exportFeedback} aria-label="导出反馈" title="导出"><svg viewBox="0 0 20 20" fill="currentColor" class="size-4"><path fill-rule="evenodd" d="M10 2a.75.75 0 0 1 .75.75v7.69l2.72-2.72a.75.75 0 1 1 1.06 1.06l-4 4a.75.75 0 0 1-1.06 0l-4-4a.75.75 0 1 1 1.06-1.06l2.72 2.72V2.75A.75.75 0 0 1 10 2ZM3.5 13.5a.75.75 0 0 1 .75.75v1.25c0 .41.34.75.75.75h10c.41 0 .75-.34.75-.75v-1.25a.75.75 0 0 1 1.5 0v1.25A2.25 2.25 0 0 1 15 17.75H5a2.25 2.25 0 0 1-2.25-2.25v-1.25a.75.75 0 0 1 .75-.75Z" clip-rule="evenodd" /></svg></button>{/if}
	</header>
	{#if exportNotice}<p class="mb-2 text-right text-xs text-emerald-600" role="status">{exportNotice}</p>{/if}

	{#if items.length === 0}
		<div class="py-12 text-center text-sm text-gray-500">没有找到反馈</div>
	{:else}
		<div class="overflow-x-auto whitespace-nowrap">
			<table class="w-full min-w-[680px] border-collapse text-left text-xs text-gray-500 dark:text-gray-400">
				<thead class="text-[10px] uppercase text-gray-800 dark:text-gray-200"><tr class="border-b border-gray-100 dark:border-gray-850/40">
					<th class="w-14 px-2.5 py-2 text-center"><button onclick={() => sortBy('userName')}>用户{#if sortKey === 'userName'} {sortDirection === 'asc' ? '↑' : '↓'}{/if}</button></th>
					<th class="px-2.5 py-2"><button onclick={() => sortBy('modelId')}>模型{#if sortKey === 'modelId'} {sortDirection === 'asc' ? '↑' : '↓'}{/if}</button></th>
					<th class="w-24 px-2.5 py-2 text-right"><button onclick={() => sortBy('rating')}>结果{#if sortKey === 'rating'} {sortDirection === 'asc' ? '↑' : '↓'}{/if}</button></th>
					<th class="w-32 px-2.5 py-2 text-right"><button onclick={() => sortBy('updatedAt')}>更新时间{#if sortKey === 'updatedAt'} {sortDirection === 'asc' ? '↑' : '↓'}{/if}</button></th>
					<th class="w-10 px-2.5 py-2"></th>
				</tr></thead>
				<tbody>
					{#each pageItems as feedback (feedback.id)}
						<tr class="cursor-pointer border-b border-gray-50 text-gray-700 transition hover:bg-gray-50 dark:border-gray-850/30 dark:text-gray-300 dark:hover:bg-gray-850/50" onclick={() => selectedFeedback = feedback} onkeydown={(event) => { if (event.key === 'Enter') selectedFeedback = feedback; }} role="button" tabindex="0" aria-label={`查看 ${feedback.userName} 的反馈`}>
							<td class="px-2.5 py-1.5 text-center"><span class="inline-flex size-6 items-center justify-center rounded-full bg-blue-100 text-[10px] font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300" title={feedback.userName}>{feedback.userName.slice(0, 1)}</span></td>
							<td class="min-w-0 px-2.5 py-1.5"><span class="block max-w-[320px] truncate font-medium text-gray-700 dark:text-gray-300" title={feedback.siblingModels.length ? `${feedback.modelId} · ${feedback.siblingModels.join(', ')}` : feedback.modelId}>{feedback.modelId}</span>{#if feedback.siblingModels.length}<span class="block max-w-[320px] truncate text-[10px] text-gray-500" title={feedback.siblingModels.join(', ')}>{feedback.siblingModels.slice(0, 2).join(', ')}{#if feedback.siblingModels.length > 2}，以及另外 {feedback.siblingModels.length - 2} 个{/if}</span>{/if}</td>
							<td class="px-2.5 py-1.5 text-right"><span class="rounded-full px-2 py-0.5 text-[10px] font-medium {feedback.rating === 1 ? 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300' : feedback.rating === 0 ? 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300' : 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300'}">{feedback.rating === 1 ? '胜出' : feedback.rating === 0 ? '平局' : '落败'}</span></td>
							<td class="px-2.5 py-1.5 text-right">{timeAgo(feedback.updatedAt)}</td>
							<td class="relative px-2.5 py-1.5 text-right" onclick={(event) => event.stopPropagation()} onkeydown={(event) => event.stopPropagation()}>
								<button class="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" onclick={() => menuFor = menuFor === feedback.id ? null : feedback.id} aria-label="反馈操作菜单" aria-expanded={menuFor === feedback.id}>···</button>
								{#if menuFor === feedback.id}<div class="absolute right-2 top-9 z-10 w-28 rounded-lg border border-gray-200 bg-white p-1 shadow-lg dark:border-gray-700 dark:bg-gray-900"><button class="w-full rounded-md px-2 py-1.5 text-left text-xs text-red-600 hover:bg-gray-100 dark:hover:bg-gray-800" onclick={() => deleteFeedback(feedback.id)}>删除反馈</button></div>{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		{#if items.length > pageSize}<nav class="mt-3 flex items-center justify-center gap-3 text-xs text-gray-500" aria-label="反馈分页"><button class="rounded-lg px-2 py-1 hover:bg-gray-100 disabled:opacity-40 dark:hover:bg-gray-850" disabled={page <= 1} onclick={() => page--}>上一页</button><span>{page} / {totalPages}</span><button class="rounded-lg px-2 py-1 hover:bg-gray-100 disabled:opacity-40 dark:hover:bg-gray-850" disabled={page >= totalPages} onclick={() => page++}>下一页</button></nav>{/if}
	{/if}
</section>

{#if selectedFeedback}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="presentation" onclick={(event) => { if (event.target === event.currentTarget) selectedFeedback = null; }}>
		<div class="w-full max-w-md rounded-2xl border border-gray-200 bg-white text-gray-900 shadow-2xl dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100" role="dialog" aria-modal="true" aria-labelledby="feedback-detail-title" tabindex="-1">
			<header class="flex items-center justify-between px-5 pb-2 pt-4"><h2 id="feedback-detail-title" class="text-lg font-medium">反馈详情</h2><button class="rounded-md p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" onclick={() => selectedFeedback = null} aria-label="关闭"><svg viewBox="0 0 20 20" fill="currentColor" class="size-5"><path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" /></svg></button></header>
			<div class="space-y-3 px-5 pb-5">
				<div><p class="mb-1 text-xs text-gray-500">对话 ID</p><p class="break-all text-xs">{selectedFeedback.chatId}</p></div>
				<div><p class="mb-1 text-xs text-gray-500">模型</p><p class="text-xs">{selectedFeedback.modelId}{#if selectedFeedback.siblingModels.length}<span class="text-gray-500"> · {selectedFeedback.siblingModels.join(', ')}</span>{/if}</p></div>
				<div><p class="mb-1 text-xs text-gray-500">提示</p><p class="whitespace-pre-line break-words text-xs">{selectedFeedback.prompt || '-'}</p></div>
				<div><p class="mb-1 text-xs text-gray-500">回答</p><p class="max-h-32 overflow-y-auto whitespace-pre-line break-words text-xs">{selectedFeedback.response || '-'}</p></div>
				<div><p class="mb-1 text-xs text-gray-500">结果</p><p class="text-xs">{selectedFeedback.rating === 1 ? '胜出' : selectedFeedback.rating === 0 ? '平局' : '落败'}</p></div>
				<div><p class="mb-1 text-xs text-gray-500">原因</p><p class="text-xs">{selectedFeedback.reason || '-'}</p></div>
				<div><p class="mb-1 text-xs text-gray-500">评论</p><p class="text-xs">{selectedFeedback.comment || '-'}</p></div>
				{#if selectedFeedback.tags.length}<div class="flex flex-wrap gap-1">{#each selectedFeedback.tags as tag (tag)}<span class="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] dark:bg-gray-850">{tag}</span>{/each}</div>{/if}
				<div class="flex justify-end pt-1"><button class="rounded-full bg-gray-900 px-4 py-1.5 text-sm font-medium text-white dark:bg-white dark:text-gray-900" onclick={() => selectedFeedback = null}>关闭</button></div>
			</div>
		</div>
	</div>
{/if}
