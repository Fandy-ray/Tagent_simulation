<script lang="ts">
	import { page } from '$app/stores';
	import { resolve } from '$app/paths';
	import { resetPassword } from '$lib/apis/auth';
	let password = $state('');
	let busy = $state(false);
	let done = $state(false);
	let error = $state('');
	async function submit(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = '';
		try {
			const token = $page.url.searchParams.get('token');
			if (!token) throw new Error('重置链接不完整。');
			await resetPassword(token, password);
			done = true;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '重置失败。';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head
	><title>重置密码 | TAgent</title><meta name="referrer" content="no-referrer" /></svelte:head
>
<main class="flex min-h-screen items-center justify-center bg-slate-950 p-5 text-white">
	<form
		onsubmit={submit}
		class="w-full max-w-md rounded-2xl border border-white/15 bg-slate-900 p-8"
	>
		<h1 class="text-2xl font-semibold">重置密码</h1>
		{#if done}
			<p role="status" class="mt-5 text-emerald-300">密码已更新，其他设备上的旧登录也已退出。</p>
			<a href={resolve('/login')} class="mt-6 inline-block rounded-lg bg-blue-500 px-4 py-2"
				>返回登录</a
			>
		{:else}
			<label for="new-password" class="mt-6 block text-sm">新密码（至少 12 个字符）</label>
			<input
				id="new-password"
				type="password"
				autocomplete="new-password"
				minlength="12"
				required
				bind:value={password}
				class="mt-2 w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2.5"
			/>
			{#if error}<p role="alert" class="mt-4 text-sm text-rose-300">{error}</p>{/if}
			<button
				type="submit"
				disabled={busy}
				class="mt-6 w-full rounded-lg bg-blue-500 px-4 py-3 disabled:opacity-50"
				>{busy ? '正在保存…' : '保存新密码'}</button
			>
		{/if}
	</form>
</main>
