<script lang="ts">
	import { AdminError, adminLockReason, verifyAdminToken } from '$lib/apis/admin';

	let token = $state('');
	let busy = $state(false);
	let error = $state('');

	async function unlock(event: SubmitEvent) {
		event.preventDefault();
		if (!token.trim() || busy) return;
		busy = true;
		error = '';
		try {
			await verifyAdminToken(token);
		} catch (cause) {
			error = cause instanceof AdminError ? cause.message : '验证口令时出错了，再试一次。';
		} finally {
			busy = false;
		}
	}
</script>

<section
	class="flex min-h-full items-center justify-center px-4 py-12 text-gray-900 dark:text-gray-100"
>
	<form class="w-full max-w-md" onsubmit={unlock}>
		<h1 class="text-lg font-medium">管理员面板</h1>
		<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
			这里能看到全班学生的提问、论文和成绩，也能改模型和知识库，要先输入管理口令。
		</p>
		<label for="admin-gate-token" class="mt-5 block text-xs text-gray-600 dark:text-gray-300"
			>管理口令</label
		>
		<div class="mt-1 flex gap-2">
			<input
				id="admin-gate-token"
				type="password"
				autocomplete="off"
				class="min-w-0 flex-1 rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none placeholder:text-gray-400 focus:border-gray-400 dark:border-gray-700"
				placeholder="粘贴管理口令"
				bind:value={token}
			/>
			<button
				type="submit"
				class="shrink-0 rounded-lg bg-gray-900 px-4 text-sm text-white hover:bg-gray-800 disabled:opacity-50 dark:bg-white dark:text-gray-900"
				disabled={busy || !token.trim()}>{busy ? '验证中…' : '进入'}</button
			>
		</div>
		<p class="mt-2 text-xs leading-5 text-gray-500">
			在 <code class="text-gray-700 dark:text-gray-300">TAgent重写版/.env.runtime</code> 里，<code
				class="text-gray-700 dark:text-gray-300">AGENT_ADMIN_TOKEN=</code
			> 后面那一串（启动脚本会自动生成）。只留在这个标签页的内存里，刷新或关掉页面后要重新输入。
		</p>
		{#if !error && $adminLockReason}<p
				class="mt-3 border-l-2 border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/30 dark:text-amber-200"
				role="status"
			>
				刚才的口令被后端拒了：{$adminLockReason}
			</p>{/if}
		{#if error}<p
				class="mt-3 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200"
				role="alert"
			>
				{error}
			</p>{/if}
	</form>
</section>
