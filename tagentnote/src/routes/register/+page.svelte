<script lang="ts">
	import { resolve } from '$app/paths';
	import { register, registrationOpen, emailVerificationRequired } from '$lib/apis/auth';
	let identifier = $state('');
	let name = $state('');
	let password = $state('');
	let busy = $state(false);
	let message = $state('');
	let error = $state('');
	async function submit(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = '';
		try {
			message = (await register(identifier, password, name)).message;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '注册失败，请稍后重试。';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>注册 | TAgent</title></svelte:head>
<main class="flex min-h-screen items-center justify-center bg-slate-950 px-5 py-12 text-white">
	<form
		onsubmit={submit}
		class="w-full max-w-md rounded-2xl border border-white/15 bg-slate-900 p-8"
	>
		<a href={resolve('/login')} class="text-sm text-blue-300">← 返回登录</a>
		<h1 class="mt-5 text-2xl font-semibold">注册学生账号</h1>
		<p class="mt-2 text-sm text-slate-300">
			{$emailVerificationRequired
				? '提交后请打开邮箱中的验证链接。'
				: '邮箱仅作为登录标识，不验证邮箱归属。创建后即可登录；忘记密码需联系管理员核验后重置。'}管理员账号单独创建。
		</p>
		<label for="name" class="mt-6 block text-sm">姓名或昵称</label>
		<input
			id="name"
			autocomplete="name"
			maxlength="40"
			bind:value={name}
			class="mt-2 w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2.5"
		/>
		<label for="identifier" class="mt-5 block text-sm">邮箱</label>
		<input
			id="identifier"
			type="email"
			autocomplete="username"
			maxlength="254"
			required
			bind:value={identifier}
			class="mt-2 w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2.5"
		/>
		<label for="password" class="mt-5 block text-sm">密码（至少 12 个字符）</label>
		<input
			id="password"
			type="password"
			autocomplete="new-password"
			minlength="12"
			required
			bind:value={password}
			class="mt-2 w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2.5"
		/>
		{#if error}<p role="alert" class="mt-4 text-sm text-rose-300">{error}</p>{/if}
		{#if message}<p role="status" class="mt-4 text-sm text-emerald-300">{message}</p>{/if}
		<button
			type="submit"
			disabled={busy || !$registrationOpen}
			class="mt-6 w-full rounded-lg bg-blue-500 px-4 py-3 font-medium disabled:opacity-50"
		>
			{busy ? '正在提交…' : '注册'}
		</button>
		{#if !$registrationOpen}<p class="mt-3 text-sm text-slate-400">当前暂未开放注册。</p>{/if}
	</form>
</main>
