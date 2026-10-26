<script lang="ts">
	import { onMount } from 'svelte';

	import {
		AdminError,
		formatTime,
		getLearningSummary,
		getStudentTimeline,
		MODE_LABELS,
		timeAgo,
		type StudentSummary,
		type StudentTimeline
	} from '$lib/apis/admin';

	const FINISH_LABELS: Record<string, string> = {
		stop: '答完',
		length: '到长度上限',
		interrupted: '中途停止',
		error: '出错'
	};

	let users = $state<StudentSummary[]>([]);
	let loading = $state(true);
	let loadError = $state('');
	let query = $state('');
	let sortKey = $state<'name' | 'chat_turns' | 'last_seen_at' | 'first_seen_at'>('last_seen_at');
	let sortDirection = $state<'asc' | 'desc'>('desc');
	let detail = $state<StudentTimeline | null>(null);
	let detailError = $state('');
	let detailLoading = $state<string | null>(null);

	const nameOf = (user: { name: string }) => user.name.trim() || '未填昵称';

	let filteredUsers = $derived(
		users
			.filter((item) =>
				`${item.name} ${item.id}`.toLowerCase().includes(query.trim().toLowerCase())
			)
			.sort((a, b) => {
				const result =
					sortKey === 'name'
						? nameOf(a).localeCompare(nameOf(b))
						: Number(a[sortKey]) - Number(b[sortKey]);
				return sortDirection === 'asc' ? result : -result;
			})
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
		loading = true;
		try {
			users = (await getLearningSummary()).students;
			loadError = '';
		} catch (error) {
			loadError = failure(error);
		} finally {
			loading = false;
		}
	}

	async function openStudent(user: StudentSummary) {
		detailLoading = user.id;
		detailError = '';
		try {
			detail = await getStudentTimeline(user.id);
		} catch (error) {
			detailError = failure(error);
		} finally {
			detailLoading = null;
		}
	}

	onMount(refresh);
</script>

<section class="min-h-full text-gray-900 dark:text-gray-100">
	<header
		class="flex items-center justify-between border-b border-gray-200 pb-3 dark:border-gray-800"
	>
		<h1 class="text-lg font-semibold">
			用户 <span class="ml-1 text-sm font-normal text-gray-500 dark:text-gray-400"
				>{users.length}</span
			>
		</h1>
		<div class="flex items-center gap-2">
			<label
				class="dark:focus-within:bg-gray-850 flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-gray-500 transition focus-within:bg-gray-100"
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
					><path
						fill-rule="evenodd"
						d="M9 3.5a5.5 5.5 0 1 0 3.445 9.788l3.328 3.328a.75.75 0 1 0 1.06-1.06l-3.328-3.329A5.5 5.5 0 0 0 9 3.5ZM5 9a4 4 0 1 1 8 0 4 4 0 0 1-8 0Z"
						clip-rule="evenodd"
					/></svg
				>
				<input
					class="w-24 bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-500 focus:w-40 dark:text-gray-100"
					bind:value={query}
					placeholder="搜索"
					aria-label="搜索用户"
				/>
			</label>
			<button
				class="dark:hover:bg-gray-850 flex size-7 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 disabled:opacity-40 dark:hover:text-white"
				onclick={refresh}
				disabled={loading}
				aria-label="刷新"
				title="刷新"
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
					><path
						fill-rule="evenodd"
						d="M15.312 11.424a5.5 5.5 0 0 1-9.201 2.466l-.312-.311h2.433a.75.75 0 0 0 0-1.5H3.989a.75.75 0 0 0-.75.75v4.242a.75.75 0 0 0 1.5 0v-2.43l.31.31a7 7 0 0 0 11.712-3.138.75.75 0 0 0-1.449-.39Zm1.23-3.723a.75.75 0 0 0 .219-.53V2.929a.75.75 0 0 0-1.5 0V5.36l-.31-.31A7 7 0 0 0 3.239 8.188a.75.75 0 1 0 1.448.389A5.5 5.5 0 0 1 13.89 6.11l.311.31h-2.432a.75.75 0 0 0 0 1.5h4.243a.75.75 0 0 0 .53-.219Z"
						clip-rule="evenodd"
					/></svg
				>
			</button>
		</div>
	</header>

	{#if loadError}<div
			class="mt-3 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200"
			role="alert"
		>
			{loadError}
		</div>{/if}

	<div class="overflow-x-auto">
		<table
			class="w-full min-w-[1000px] table-fixed border-collapse text-left text-xs whitespace-nowrap"
		>
			<colgroup>
				<col class="w-[80px]" />
				<col class="w-[180px]" />
				<col class="w-[200px]" />
				<col class="w-[80px]" />
				<col class="w-[110px]" />
				<col class="w-[110px]" />
				<col class="w-[120px]" />
				<col class="w-[150px]" />
				<col class="w-[48px]" />
			</colgroup>
			<thead class="border-b border-gray-200 text-gray-500 dark:border-gray-800 dark:text-gray-400">
				<tr>
					<th class="px-2 py-2 font-medium">角色</th>
					<th class="px-2 py-2 font-medium"><button onclick={() => sortBy('name')}>名称</button></th
					>
					<th class="px-3 py-3 font-medium">设备编号</th>
					<th class="px-3 py-3 font-medium"
						><button onclick={() => sortBy('chat_turns')}>答疑</button></th
					>
					<th class="px-3 py-3 font-medium">论文批改（均分）</th>
					<th class="px-3 py-3 font-medium">整卷（得分率）</th>
					<th class="px-3 py-3 font-medium"
						><button onclick={() => sortBy('last_seen_at')}>最后在线时间</button></th
					>
					<th class="px-3 py-3 font-medium"
						><button onclick={() => sortBy('first_seen_at')}>第一次出现</button></th
					>
					<th class="px-2 py-2"></th>
				</tr>
			</thead>
			<tbody>
				{#each filteredUsers as user (user.id)}
					<tr
						class="border-b border-gray-100 text-gray-700 dark:border-gray-800/80 dark:text-gray-300"
					>
						<td class="px-2 py-3 whitespace-nowrap"
							><span
								class="rounded-md bg-blue-100 px-2 py-1 text-[10px] font-medium whitespace-nowrap text-blue-700 dark:bg-blue-950/70 dark:text-blue-300"
								>学生</span
							></td
						>
						<td class="px-3 py-3 whitespace-nowrap"
							><span class="inline-flex items-center gap-2"
								><span
									class="flex size-6 items-center justify-center rounded-full bg-amber-500 text-[10px] font-semibold text-white"
									>{nameOf(user).slice(0, 1)}</span
								><span class={user.name.trim() ? '' : 'text-gray-400'}>{nameOf(user)}</span
								>{#if Date.now() - user.last_seen_at < 5 * 60_000}<span
										class="size-1.5 rounded-full bg-emerald-500"
										title="5 分钟内有活动"
										aria-label="在线"
									></span>{/if}</span
							></td
						>
						<td class="truncate px-3 py-3 font-mono text-[11px] text-gray-500" title={user.id}
							>{user.id}</td
						>
						<td class="px-3 py-3 tabular-nums">{user.chat_turns}</td>
						<td class="px-3 py-3 tabular-nums"
							>{user.essay_reviews}{#if user.essay_avg !== null}<span class="text-gray-400">
									（{user.essay_avg}）</span
								>{/if}</td
						>
						<td class="px-3 py-3 tabular-nums"
							>{user.exams_reviewed}{#if user.exam_avg_percent !== null}<span class="text-gray-400">
									（{user.exam_avg_percent}%）</span
								>{/if}</td
						>
						<td class="px-3 py-3" title={formatTime(user.last_seen_at)}
							>{timeAgo(user.last_seen_at)}</td
						>
						<td class="px-3 py-3">{formatTime(user.first_seen_at)}</td>
						<td class="px-3 py-3 text-right"
							><button
								class="rounded-md p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-900 disabled:opacity-40 dark:hover:bg-gray-800 dark:hover:text-white"
								onclick={() => openStudent(user)}
								disabled={detailLoading !== null}
								aria-label="查看学习记录"
								title="查看学习记录"
								><svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
									><path d="M10 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" /><path
										fill-rule="evenodd"
										d="M.664 10.59a1.651 1.651 0 0 1 0-1.186A10.004 10.004 0 0 1 10 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0 1 10 17c-4.257 0-7.893-2.66-9.336-6.41ZM14 10a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z"
										clip-rule="evenodd"
									/></svg
								></button
							></td
						>
					</tr>
				{:else}
					<tr
						><td colspan="9" class="px-3 py-12 text-center text-sm text-gray-500"
							>{loading
								? '正在读取…'
								: users.length
									? '没有找到用户'
									: '还没有学生用过：学生在答疑、论文批改、测评里的记录会出现在这里'}</td
						></tr
					>
				{/each}
			</tbody>
		</table>
	</div>
	{#if detailError}<p class="mt-2 text-sm text-red-600" role="alert">{detailError}</p>{/if}
	<p class="mt-2 text-right text-[10px] text-gray-400">
		ⓘ 学生不用注册：一台设备（一个浏览器）算一个人，名称取学生在设置里填的显示名称。
	</p>
</section>

{#if detail}
	{@const student = detail.student}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget) detail = null;
		}}
	>
		<div
			class="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900"
			role="dialog"
			aria-modal="true"
			aria-labelledby="user-modal-title"
			tabindex="-1"
		>
			<header class="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
				<div class="min-w-0">
					<h2 id="user-modal-title" class="text-lg font-semibold">{nameOf(student)}</h2>
					<p class="mt-1 truncate text-xs text-gray-500 dark:text-gray-400">
						<span class="font-mono">{student.id}</span> · 第一次出现 {formatTime(
							student.first_seen_at
						)} · 最后在线 {formatTime(student.last_seen_at)}
					</p>
				</div>
				<button
					class="rounded-md p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
					onclick={() => (detail = null)}
					aria-label="关闭">×</button
				>
			</header>
			<div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 pb-5 text-sm">
				<section>
					<h3 class="mb-1.5 text-xs font-medium text-gray-500">
						最近答疑 <span class="font-normal">{detail.chat_turns.length}</span>
					</h3>
					{#each detail.chat_turns as turn (turn.id)}
						<details class="border-b border-gray-100 py-2 dark:border-gray-800">
							<summary class="cursor-pointer list-none">
								<span class="line-clamp-2">{turn.question}</span>
								<span class="mt-0.5 block text-[11px] text-gray-400"
									>{MODE_LABELS[turn.mode] ?? turn.mode} · {turn.model} · {FINISH_LABELS[
										turn.finish_reason ?? ''
									] ?? '—'}{turn.duration_ms ? ` · ${(turn.duration_ms / 1000).toFixed(1)} 秒` : ''} ·
									{formatTime(turn.created_at)}</span
								>
							</summary>
							<p
								class="mt-2 max-h-48 overflow-y-auto text-xs break-words whitespace-pre-line text-gray-600 dark:text-gray-300"
							>
								{turn.answer || '（没有回答内容）'}
							</p>
						</details>
					{:else}
						<p class="text-xs text-gray-400">没有</p>
					{/each}
				</section>
				<section>
					<h3 class="mb-1.5 text-xs font-medium text-gray-500">
						论文批改 <span class="font-normal">{detail.essay_reviews.length}</span>
					</h3>
					{#each detail.essay_reviews as essay (essay.id)}
						<div
							class="flex items-baseline justify-between gap-3 border-b border-gray-100 py-2 dark:border-gray-800"
						>
							<span class="min-w-0 truncate">{essay.topic || '（没有题目）'}</span>
							<span class="shrink-0 text-xs text-gray-500"
								>{essay.score ?? '—'} 分 · {essay.model} · {formatTime(essay.created_at)}</span
							>
						</div>
					{:else}
						<p class="text-xs text-gray-400">没有</p>
					{/each}
				</section>
				<section>
					<h3 class="mb-1.5 text-xs font-medium text-gray-500">
						整卷 <span class="font-normal">{detail.exam_attempts.length}</span>
					</h3>
					{#each detail.exam_attempts as exam (exam.exam_id)}
						<div
							class="flex items-baseline justify-between gap-3 border-b border-gray-100 py-2 dark:border-gray-800"
						>
							<span class="min-w-0 truncate">{exam.title || exam.topic || '（没有标题）'}</span>
							<span class="shrink-0 text-xs text-gray-500"
								>{exam.score === null ? '没交卷' : `${exam.score} / ${exam.total_points}`} · {exam.model}
								· {formatTime(exam.reviewed_at ?? exam.created_at)}</span
							>
						</div>
					{:else}
						<p class="text-xs text-gray-400">没有</p>
					{/each}
				</section>
			</div>
		</div>
	</div>
{/if}
