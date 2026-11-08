<script lang="ts">
	import { onMount } from 'svelte';
	import { identityRequest, type Account, type Course } from '$lib/apis/auth';
	let courses = $state<Course[]>([]);
	let selected = $state('');
	let members = $state<Account[]>([]);
	let summary = $state<{
		totals: { students: number; chat_turns: number; essay_reviews: number; exams_reviewed: number };
		students: {
			id: string;
			name: string;
			chat_turns: number;
			essay_reviews: number;
			exams_reviewed: number;
			exam_avg_percent: number | null;
		}[];
	} | null>(null);
	let name = $state('');
	let description = $state('');
	let models = $state('');
	let notebooks = $state('');
	let memberEmail = $state('');
	let busy = $state(false);
	let error = $state('');
	let message = $state('');
	const splitIds = (value: string) =>
		value
			.split(/[\n,，]/)
			.map((item) => item.trim())
			.filter(Boolean);

	async function load() {
		try {
			courses = (await identityRequest<{ courses: Course[] }>('/admin/courses')).courses;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '读取课程失败。';
		}
	}
	onMount(() => {
		void load();
	});

	async function selectCourse(id: string) {
		selected = id;
		error = '';
		message = '';
		const course = courses.find((item) => item.id === id);
		name = course?.name || '';
		description = course?.description || '';
		models = course?.model_ids.join(', ') || '';
		notebooks = course?.notebook_ids.join(', ') || '';
		if (id) {
			const [membership, stats] = await Promise.all([
				identityRequest<{ members: Account[] }>(`/admin/courses/${encodeURIComponent(id)}/members`),
				identityRequest<typeof summary>(`/admin/courses/${encodeURIComponent(id)}/summary`)
			]);
			members = membership.members;
			summary = stats;
		} else {
			members = [];
			summary = null;
		}
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = '';
		message = '';
		try {
			const payload = {
				name,
				description,
				model_ids: splitIds(models),
				notebook_ids: splitIds(notebooks)
			};
			const result = selected
				? await identityRequest<{ course: Course }>(
						`/admin/courses/${encodeURIComponent(selected)}`,
						'PUT',
						payload
					)
				: await identityRequest<{ course: Course }>('/admin/courses', 'POST', payload);
			await load();
			await selectCourse(result.course.id);
			message = '课程已保存。';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '保存失败。';
		} finally {
			busy = false;
		}
	}

	async function addMember(event: SubmitEvent) {
		event.preventDefault();
		if (!selected) return;
		busy = true;
		error = '';
		message = '';
		try {
			await identityRequest(`/admin/courses/${encodeURIComponent(selected)}/members`, 'POST', {
				email: memberEmail
			});
			memberEmail = '';
			await selectCourse(selected);
			message = '学生已加入课程。';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '添加失败。';
		} finally {
			busy = false;
		}
	}

	async function removeMember(account: Account) {
		if (!selected) return;
		busy = true;
		error = '';
		try {
			await identityRequest(
				`/admin/courses/${encodeURIComponent(selected)}/members/${encodeURIComponent(account.id)}`,
				'DELETE'
			);
			members = members.filter((item) => item.id !== account.id);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '移除失败。';
		} finally {
			busy = false;
		}
	}
	async function toggleCourse(course: Course) {
		busy = true;
		error = '';
		message = '';
		try {
			await identityRequest(`/admin/courses/${encodeURIComponent(course.id)}/state`, 'PATCH', {
				active: !course.active
			});
			await load();
			if (selected === course.id) await selectCourse('');
			message = course.active ? '课程已停用，学生暂时不能进入。' : '课程已重新启用。';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '修改失败。';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>课程管理 | TAgent</title></svelte:head>
<div class="grid gap-6 p-6 lg:grid-cols-[15rem_1fr]">
	<aside>
		<h1 class="text-2xl font-semibold">课程</h1>
		<button
			type="button"
			onclick={() => selectCourse('')}
			class="mt-5 w-full rounded-lg bg-blue-600 px-3 py-2 text-left text-sm text-white"
			>新建课程</button
		>
		{#each courses as course (course.id)}<div class="mt-2 flex items-center gap-2">
				<button
					type="button"
					disabled={!course.active}
					onclick={() => selectCourse(course.id)}
					class="min-w-0 flex-1 rounded-lg border px-3 py-2 text-left text-sm disabled:opacity-50 {selected ===
					course.id
						? 'border-blue-500'
						: 'border-gray-300 dark:border-white/15'}"
					>{course.name}{course.active ? '' : '（已停用）'}</button
				><button
					type="button"
					disabled={busy}
					onclick={() => toggleCourse(course)}
					class="text-xs text-blue-600 disabled:opacity-50"
					>{course.active ? '停用' : '启用'}</button
				>
			</div>{/each}
	</aside>
	<div>
		<form onsubmit={save} class="rounded-xl border border-gray-200 p-5 dark:border-white/15">
			<h2 class="text-lg font-medium">{selected ? '编辑课程' : '新建课程'}</h2>
			<label for="course-name" class="mt-4 block text-sm">课程名称</label>
			<input
				id="course-name"
				required
				maxlength="120"
				bind:value={name}
				class="mt-1 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-white/20"
			/>
			<label for="course-description" class="mt-4 block text-sm">说明</label>
			<textarea
				id="course-description"
				maxlength="500"
				bind:value={description}
				class="mt-1 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-white/20"
			></textarea>
			<label for="course-models" class="mt-4 block text-sm">可用模型 ID（逗号分隔）</label>
			<input
				id="course-models"
				bind:value={models}
				class="mt-1 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-white/20"
			/>
			<label for="course-notebooks" class="mt-4 block text-sm">关联笔记本 ID（逗号分隔）</label>
			<input
				id="course-notebooks"
				bind:value={notebooks}
				class="mt-1 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-white/20"
			/>
			<p class="mt-2 text-xs text-gray-500">
				笔记本仍由 OpenNotebook 单独登录管理；这里仅指定 TAgent 检索时使用的笔记本。
			</p>
			<button
				type="submit"
				disabled={busy}
				class="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
				>保存课程</button
			>
		</form>
		{#if selected}
			{#if summary}
				<section class="mt-5 rounded-xl border border-gray-200 p-5 dark:border-white/15">
					<h2 class="text-lg font-medium">本课程学习记录</h2>
					<p class="mt-2 text-sm text-gray-500">
						{summary.totals.students} 名学生 · {summary.totals.chat_turns} 次答疑 · {summary.totals
							.essay_reviews} 次论文批改 · {summary.totals.exams_reviewed} 次整卷批改
					</p>
					<div class="mt-4 overflow-x-auto">
						<table class="w-full text-left text-sm">
							<thead
								><tr
									><th class="p-2">学生</th><th class="p-2">答疑</th><th class="p-2">论文批改</th
									><th class="p-2">整卷批改</th><th class="p-2">平均得分率</th></tr
								></thead
							>
							<tbody
								>{#each summary.students as student (student.id)}<tr
										class="border-t border-gray-200 dark:border-white/10"
										><td class="p-2"
											>{student.name ||
												members.find((item) => item.id === student.id)?.email ||
												student.id}</td
										><td class="p-2">{student.chat_turns}</td><td class="p-2"
											>{student.essay_reviews}</td
										><td class="p-2">{student.exams_reviewed}</td><td class="p-2"
											>{student.exam_avg_percent === null
												? '—'
												: `${student.exam_avg_percent}%`}</td
										></tr
									>{/each}</tbody
							>
						</table>
					</div>
				</section>
			{/if}
			<section class="mt-5 rounded-xl border border-gray-200 p-5 dark:border-white/15">
				<h2 class="text-lg font-medium">课程学生</h2>
				<form onsubmit={addMember} class="mt-4 flex gap-2">
					<input
						type="email"
						aria-label="学生邮箱"
						placeholder="已验证的学生邮箱"
						required
						bind:value={memberEmail}
						class="min-w-0 flex-1 rounded-lg border border-gray-300 bg-transparent px-3 py-2 dark:border-white/20"
					/>
					<button
						type="submit"
						disabled={busy}
						class="rounded-lg bg-blue-600 px-3 py-2 text-white disabled:opacity-50">添加</button
					>
				</form>
				<ul class="mt-4 space-y-2">
					{#each members as account (account.id)}<li
							class="flex items-center justify-between gap-3 border-t border-gray-200 py-2 text-sm dark:border-white/10"
						>
							<span>{account.name || account.email} · {account.email}</span><button
								type="button"
								disabled={busy}
								onclick={() => removeMember(account)}
								class="text-rose-500">移除</button
							>
						</li>{/each}
				</ul>
			</section>
		{/if}
		{#if error}<p role="alert" class="mt-4 text-rose-600">{error}</p>{/if}
		{#if message}<p role="status" class="mt-4 text-emerald-600">{message}</p>{/if}
	</div>
</div>
