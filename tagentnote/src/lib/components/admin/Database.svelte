<script lang="ts">
	import { onMount } from 'svelte';

	import {
		AdminError,
		backupDb,
		formatBytes,
		formatTime,
		getDbInfo,
		type DbInfo
	} from '$lib/apis/admin';

	const TABLES: [string, string][] = [
		['students', '学生（设备）'],
		['chat_turns', '答疑记录'],
		['essay_reviews', '论文批改'],
		['exam_attempts', '整卷'],
		['feedback', '赞 / 踩'],
		['exam_cache', '还没过期的试卷']
	];

	let info = $state<DbInfo | null>(null);
	let loadError = $state('');
	let backingUp = $state(false);
	let notice = $state('');

	const failure = (error: unknown) =>
		error instanceof AdminError ? error.message : '读取失败，再试一次。';

	async function refresh() {
		try {
			info = await getDbInfo();
			loadError = '';
		} catch (error) {
			loadError = failure(error);
		}
	}

	async function backup() {
		backingUp = true;
		try {
			const result = await backupDb();
			notice = `已备份：${result.file}（${formatBytes(result.bytes)}）`;
			await refresh();
		} catch (error) {
			notice = failure(error);
		} finally {
			backingUp = false;
			setTimeout(() => (notice = ''), 4000);
		}
	}

	onMount(refresh);
</script>

<div class="flex min-h-full flex-col">
	<header
		class="flex items-center justify-between gap-3 border-b border-gray-100 pb-3 dark:border-gray-800"
	>
		<div class="min-w-0">
			<h2 class="text-base font-medium text-gray-900 dark:text-gray-100">数据库</h2>
			<p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
				学习记录库（SQLite）：答疑、论文批改、整卷和赞踩都记在这里
			</p>
		</div>
		<button
			type="button"
			class="rounded-lg bg-gray-900 px-3 py-1.5 text-sm text-white hover:bg-gray-800 disabled:opacity-50 dark:bg-white dark:text-gray-900"
			onclick={backup}
			disabled={backingUp || !info}>{backingUp ? '备份中…' : '立即备份'}</button
		>
	</header>

	{#if loadError}<div
			class="mt-3 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200"
			role="alert"
		>
			{loadError}
		</div>{/if}

	{#if info}
		<section class="mt-4 space-y-1 text-sm">
			<div class="flex justify-between gap-4 py-1.5">
				<span class="shrink-0 text-gray-500">文件</span><span
					class="min-w-0 truncate font-mono text-xs text-gray-700 dark:text-gray-300"
					title={info.path}>{info.path}</span
				>
			</div>
			<div class="flex justify-between gap-4 py-1.5">
				<span class="shrink-0 text-gray-500">大小</span><span>{formatBytes(info.bytes)}</span>
			</div>
			<div class="flex justify-between gap-4 py-1.5">
				<span class="shrink-0 text-gray-500">表结构版本</span><span
					>第 {info.schema_version} 版</span
				>
			</div>
			<div class="flex justify-between gap-4 py-1.5">
				<span class="shrink-0 text-gray-500">自动备份</span><span
					>每天一份（不停服务），保留最近 {info.backup_keep} 份</span
				>
			</div>
		</section>

		<h3 class="mt-6 mb-1 text-xs font-medium text-gray-700 dark:text-gray-300">各表条数</h3>
		<div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
			{#each TABLES as [table, label] (table)}
				<div class="rounded-xl border border-gray-100 px-3 py-2 dark:border-gray-800">
					<p class="text-xs text-gray-500">{label}</p>
					<p class="mt-0.5 text-lg font-medium tabular-nums">
						{(info.tables[table] ?? 0).toLocaleString()}
					</p>
				</div>
			{/each}
		</div>

		<h3 class="mt-6 mb-1 text-xs font-medium text-gray-700 dark:text-gray-300">
			备份 <span class="font-normal text-gray-400">{info.backups.length}</span>
		</h3>
		{#if info.backups.length === 0}
			<p
				class="border-y border-gray-100 py-6 text-center text-sm text-gray-500 dark:border-gray-800"
			>
				还没有备份
			</p>
		{:else}
			<table class="w-full text-left text-xs">
				<thead class="border-b border-gray-100 text-gray-500 dark:border-gray-800">
					<tr
						><th class="px-2 py-2 font-medium">文件</th><th class="px-2 py-2 text-right font-medium"
							>大小</th
						><th class="px-2 py-2 text-right font-medium">时间</th></tr
					>
				</thead>
				<tbody class="divide-y divide-gray-100 dark:divide-gray-800">
					{#each info.backups as item (item.file)}
						<tr>
							<td class="truncate px-2 py-2 font-mono">{item.file}</td>
							<td class="px-2 py-2 text-right">{formatBytes(item.bytes)}</td>
							<td class="px-2 py-2 text-right">{formatTime(item.modified_at)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
			<p class="mt-2 text-[11px] text-gray-500">
				备份在库文件旁边的 backups 文件夹里。要恢复时先停掉后端，删掉库文件旁的 -wal、-shm
				两个文件，再用备份文件替换库文件，然后启动。
			</p>
		{/if}
	{:else if !loadError}
		<p class="py-10 text-center text-sm text-gray-500">正在读取…</p>
	{/if}
</div>

{#if notice}<div
		class="fixed right-5 bottom-5 z-[110] max-w-sm rounded-xl bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg dark:bg-white dark:text-gray-900"
		role="status"
	>
		{notice}
	</div>{/if}
