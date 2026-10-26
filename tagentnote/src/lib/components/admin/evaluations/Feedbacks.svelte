<script lang="ts">
	import { onMount } from 'svelte';

	import {
		AdminError,
		deleteFeedback as removeFeedback,
		FEEDBACK_LIMIT,
		formatTime,
		getFeedback,
		MODE_LABELS,
		timeAgo,
		type FeedbackEntry
	} from '$lib/apis/admin';
	import { fileSaver } from '$lib/utils/fileSaver';

	let items = $state<FeedbackEntry[]>([]);
	let loading = $state(true);
	let loadError = $state('');
	let page = $state(1);
	const pageSize = 20;
	let sortKey = $state<'userName' | 'modelId' | 'rating' | 'updatedAt'>('updatedAt');
	let sortDirection = $state<'asc' | 'desc'>('desc');
	let selectedFeedback = $state<FeedbackEntry | null>(null);
	let menuFor = $state<number | null>(null);
	let exportNotice = $state('');

	const userName = (item: FeedbackEntry) => item.student_name?.trim() || '未填昵称';

	const sortedItems = $derived(
		[...items].sort((a, b) => {
			const result =
				sortKey === 'updatedAt'
					? a.updated_at - b.updated_at
					: sortKey === 'rating'
						? a.rating - b.rating
						: sortKey === 'modelId'
							? a.model.localeCompare(b.model)
							: userName(a).localeCompare(userName(b));
			return sortDirection === 'asc' ? result : -result;
		})
	);
	const totalPages = $derived(Math.max(1, Math.ceil(items.length / pageSize)));
	const pageItems = $derived(sortedItems.slice((page - 1) * pageSize, page * pageSize));

	function sortBy(key: typeof sortKey) {
		if (sortKey === key) sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
		else {
			sortKey = key;
			sortDirection = 'asc';
		}
		page = 1;
	}

	const failure = (error: unknown) =>
		error instanceof AdminError ? error.message : '操作没有成功，再试一次。';

	async function refresh() {
		try {
			items = await getFeedback();
			loadError = '';
		} catch (error) {
			loadError = failure(error);
		} finally {
			loading = false;
		}
	}

	function exportFeedback() {
		// 现成的下载工具：链接先挂进页面、过一会儿再收回地址，Safari 上也能下下来
		fileSaver.saveAs(
			JSON.stringify(items, null, 2),
			`feedback-${Date.now()}.json`,
			'application/json'
		);
		exportNotice = `已导出 ${items.length} 条反馈`;
		setTimeout(() => (exportNotice = ''), 2500);
	}

	async function deleteFeedback(id: number) {
		menuFor = null;
		try {
			await removeFeedback(id);
		} catch (error) {
			// 已经被删了（404）也当作删掉了，刷新列表即可
			if (!(error instanceof AdminError && error.status === 404)) {
				exportNotice = failure(error);
				setTimeout(() => (exportNotice = ''), 4000);
				return;
			}
		}
		items = items.filter((item) => item.id !== id);
		if (selectedFeedback?.id === id) selectedFeedback = null;
		page = Math.min(page, totalPages);
	}

	onMount(refresh);
</script>

<section class="min-h-full text-gray-900 dark:text-gray-100">
	<header class="mb-1 flex items-center justify-between gap-3">
		<h1 class="flex shrink-0 items-center gap-2 px-0.5 text-lg font-medium">
			反馈历史 <span class="text-sm text-gray-500"
				>{items.length >= FEEDBACK_LIMIT ? `最近 ${FEEDBACK_LIMIT} 条` : items.length}</span
			>
		</h1>
		{#if items.length}<button
				class="dark:hover:bg-gray-850 rounded-lg p-2 text-gray-500 transition hover:bg-gray-100"
				onclick={exportFeedback}
				aria-label="导出反馈"
				title="导出"
				><svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
					><path
						fill-rule="evenodd"
						d="M10 2a.75.75 0 0 1 .75.75v7.69l2.72-2.72a.75.75 0 1 1 1.06 1.06l-4 4a.75.75 0 0 1-1.06 0l-4-4a.75.75 0 1 1 1.06-1.06l2.72 2.72V2.75A.75.75 0 0 1 10 2ZM3.5 13.5a.75.75 0 0 1 .75.75v1.25c0 .41.34.75.75.75h10c.41 0 .75-.34.75-.75v-1.25a.75.75 0 0 1 1.5 0v1.25A2.25 2.25 0 0 1 15 17.75H5a2.25 2.25 0 0 1-2.25-2.25v-1.25a.75.75 0 0 1 .75-.75Z"
						clip-rule="evenodd"
					/></svg
				></button
			>{/if}
	</header>
	{#if exportNotice}<p class="mb-2 text-right text-xs text-emerald-600" role="status">
			{exportNotice}
		</p>{/if}

	{#if loadError}<div
			class="mb-2 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200"
			role="alert"
		>
			{loadError}
		</div>{/if}

	{#if items.length === 0}
		<div class="py-12 text-center text-sm text-gray-500">
			{loading ? '正在读取…' : '还没有反馈：学生在答疑里点「有帮助 / 没有帮助」后会出现在这里'}
		</div>
	{:else}
		<div class="overflow-x-auto whitespace-nowrap">
			<table
				class="w-full min-w-[680px] border-collapse text-left text-xs text-gray-500 dark:text-gray-400"
			>
				<thead class="text-[10px] text-gray-800 uppercase dark:text-gray-200"
					><tr class="dark:border-gray-850/40 border-b border-gray-100">
						<th class="w-14 px-2.5 py-2 text-center"
							><button onclick={() => sortBy('userName')}
								>用户{#if sortKey === 'userName'}
									{sortDirection === 'asc' ? '↑' : '↓'}{/if}</button
							></th
						>
						<th class="px-2.5 py-2"
							><button onclick={() => sortBy('modelId')}
								>模型{#if sortKey === 'modelId'}
									{sortDirection === 'asc' ? '↑' : '↓'}{/if}</button
							></th
						>
						<th class="w-24 px-2.5 py-2 text-right"
							><button onclick={() => sortBy('rating')}
								>结果{#if sortKey === 'rating'}
									{sortDirection === 'asc' ? '↑' : '↓'}{/if}</button
							></th
						>
						<th class="w-32 px-2.5 py-2 text-right"
							><button onclick={() => sortBy('updatedAt')}
								>更新时间{#if sortKey === 'updatedAt'}
									{sortDirection === 'asc' ? '↑' : '↓'}{/if}</button
							></th
						>
						<th class="w-10 px-2.5 py-2"></th>
					</tr></thead
				>
				<tbody>
					{#each pageItems as feedback (feedback.id)}
						<tr
							class="dark:border-gray-850/30 dark:hover:bg-gray-850/50 cursor-pointer border-b border-gray-50 text-gray-700 transition hover:bg-gray-50 dark:text-gray-300"
							onclick={() => (selectedFeedback = feedback)}
							onkeydown={(event) => {
								if (event.key === 'Enter') selectedFeedback = feedback;
							}}
							role="button"
							tabindex="0"
							aria-label={`查看 ${userName(feedback)} 的反馈`}
						>
							<td class="px-2.5 py-1.5 text-center"
								><span
									class="inline-flex size-6 items-center justify-center rounded-full bg-blue-100 text-[10px] font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300"
									title={userName(feedback)}>{userName(feedback).slice(0, 1)}</span
								></td
							>
							<td class="min-w-0 px-2.5 py-1.5"
								><span
									class="block max-w-[320px] truncate font-medium text-gray-700 dark:text-gray-300"
									title={feedback.model}>{feedback.model}</span
								><span
									class="block max-w-[320px] truncate text-[10px] text-gray-500"
									title={feedback.question}
									>{MODE_LABELS[feedback.mode] ?? feedback.mode} · {feedback.question}</span
								></td
							>
							<td class="px-2.5 py-1.5 text-right"
								><span
									class="rounded-full px-2 py-0.5 text-[10px] font-medium {feedback.rating === 1
										? 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300'
										: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300'}"
									>{feedback.rating === 1 ? '有帮助' : '没帮助'}</span
								></td
							>
							<td class="px-2.5 py-1.5 text-right" title={formatTime(feedback.updated_at)}
								>{timeAgo(feedback.updated_at)}</td
							>
							<td
								class="relative px-2.5 py-1.5 text-right"
								onclick={(event) => event.stopPropagation()}
								onkeydown={(event) => event.stopPropagation()}
							>
								<button
									class="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
									onclick={() => (menuFor = menuFor === feedback.id ? null : feedback.id)}
									aria-label="反馈操作菜单"
									aria-expanded={menuFor === feedback.id}>···</button
								>
								{#if menuFor === feedback.id}<div
										class="absolute top-9 right-2 z-10 w-28 rounded-lg border border-gray-200 bg-white p-1 shadow-lg dark:border-gray-700 dark:bg-gray-900"
									>
										<button
											class="w-full rounded-md px-2 py-1.5 text-left text-xs text-red-600 hover:bg-gray-100 dark:hover:bg-gray-800"
											onclick={() => deleteFeedback(feedback.id)}>删除反馈</button
										>
									</div>{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		{#if items.length > pageSize}<nav
				class="mt-3 flex items-center justify-center gap-3 text-xs text-gray-500"
				aria-label="反馈分页"
			>
				<button
					class="dark:hover:bg-gray-850 rounded-lg px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
					disabled={page <= 1}
					onclick={() => page--}>上一页</button
				><span>{page} / {totalPages}</span><button
					class="dark:hover:bg-gray-850 rounded-lg px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
					disabled={page >= totalPages}
					onclick={() => page++}>下一页</button
				>
			</nav>{/if}
	{/if}
</section>

{#if selectedFeedback}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget) selectedFeedback = null;
		}}
	>
		<div
			class="w-full max-w-md rounded-2xl border border-gray-200 bg-white text-gray-900 shadow-2xl dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
			role="dialog"
			aria-modal="true"
			aria-labelledby="feedback-detail-title"
			tabindex="-1"
		>
			<header class="flex items-center justify-between px-5 pt-4 pb-2">
				<h2 id="feedback-detail-title" class="text-lg font-medium">反馈详情</h2>
				<button
					class="rounded-md p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
					onclick={() => (selectedFeedback = null)}
					aria-label="关闭"
					><svg viewBox="0 0 20 20" fill="currentColor" class="size-5"
						><path
							d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z"
						/></svg
					></button
				>
			</header>
			<div class="space-y-3 px-5 pb-5">
				<div>
					<p class="mb-1 text-xs text-gray-500">学生</p>
					<p class="text-xs">
						{userName(selectedFeedback)}
						<span class="font-mono text-gray-400">{selectedFeedback.student_id}</span>
					</p>
				</div>
				<div>
					<p class="mb-1 text-xs text-gray-500">模型 · 场景</p>
					<p class="text-xs">
						{selectedFeedback.model} · {MODE_LABELS[selectedFeedback.mode] ?? selectedFeedback.mode}
					</p>
				</div>
				<div>
					<p class="mb-1 text-xs text-gray-500">提问</p>
					<p class="max-h-32 overflow-y-auto text-xs break-words whitespace-pre-line">
						{selectedFeedback.question || '-'}
					</p>
				</div>
				<div>
					<p class="mb-1 text-xs text-gray-500">回答</p>
					<p class="max-h-48 overflow-y-auto text-xs break-words whitespace-pre-line">
						{selectedFeedback.answer || '-'}
					</p>
				</div>
				<div>
					<p class="mb-1 text-xs text-gray-500">评价</p>
					<p class="text-xs">
						{selectedFeedback.rating === 1 ? '有帮助' : '没帮助'} · {formatTime(
							selectedFeedback.updated_at
						)}
					</p>
				</div>
				<div class="flex justify-end pt-1">
					<button
						class="rounded-full bg-gray-900 px-4 py-1.5 text-sm font-medium text-white dark:bg-white dark:text-gray-900"
						onclick={() => (selectedFeedback = null)}>关闭</button
					>
				</div>
			</div>
		</div>
	</div>
{/if}
