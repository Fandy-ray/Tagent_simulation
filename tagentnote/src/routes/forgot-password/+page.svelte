<script lang="ts">
	import { resolve } from '$app/paths';
	import { requestPasswordReset } from '$lib/apis/auth';
	let email = $state('');
	let busy = $state(false);
	let message = $state('');
	let error = $state('');
	async function submit(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = '';
		try {
			message = (await requestPasswordReset(email)).message;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '发送失败。';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>找回密码 | TAgent</title></svelte:head>
<main class="flex min-h-screen items-center justify-center bg-slate-950 p-5 text-white">
	<form
		onsubmit={submit}
		class="w-full max-w-md rounded-2xl border border-white/15 bg-slate-900 p-8"
	>
		<a href={resolve('/login')} class="text-sm text-blue-300">← 返回登录</a>
		<h1 class="mt-5 text-2xl font-semibold">找回密码</h1>
		<p class="mt-2 text-sm text-slate-300">填写注册邮箱，我们会发送重置链接。</p>
		<label for="reset-email" class="mt-6 block text-sm">邮箱</label>
		<input
			id="reset-email"
			type="email"
			autocomplete="email"
			required
			bind:value={email}
			class="mt-2 w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2.5"
		/>
		{#if error}<p role="alert" class="mt-4 text-sm text-rose-300">{error}</p>{/if}
		{#if message}<p role="status" class="mt-4 text-sm text-emerald-300">{message}</p>{/if}
		<button
			type="submit"
			disabled={busy}
			class="mt-6 w-full rounded-lg bg-blue-500 px-4 py-3 disabled:opacity-50"
			>{busy ? '正在发送…' : '发送重置链接'}</button
		>
	</form>
</main>
