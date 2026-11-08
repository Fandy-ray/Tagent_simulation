<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/stores';
	import {
		authMode,
		currentAccount,
		login,
		registrationMethod,
		registrationOpen,
		passwordResetAvailable
	} from '$lib/apis/auth';

	let identifier = $state('');
	let password = $state('');
	let busy = $state(false);
	let error = $state('');

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = '';
		try {
			await login(identifier, password);
			const requested = $page.url.searchParams.get('next') || '/agent-select';
			const destination =
				requested.startsWith('/') && !requested.startsWith('//') ? requested : '/agent-select';
			await goto(resolve(destination));
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '登录失败，请稍后重试。';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>登录 | TAgent</title></svelte:head>

<main class="flex min-h-screen items-center justify-center bg-slate-950 px-5 py-12 text-white">
	<form
		onsubmit={submit}
		class="w-full max-w-md rounded-2xl border border-white/15 bg-slate-900 p-8 shadow-xl"
	>
		<a href={resolve('/welcome')} class="text-sm text-blue-300">← 返回首页</a>
		<h1 class="mt-5 text-2xl font-semibold">登录 TAgent</h1>
		<p class="mt-2 text-sm text-slate-300">用自己的账号保存课程学习记录，并在其他设备继续使用。</p>
		<label class="mt-7 block text-sm" for="login-identifier"
			>{$registrationMethod === 'username' ? '用户名（管理员可用邮箱）' : '邮箱'}</label
		>
		<input
			id="login-identifier"
			type={$registrationMethod === 'username' ? 'text' : 'email'}
			autocomplete="username"
			required
			bind:value={identifier}
			class="mt-2 w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2.5"
		/>
		<label class="mt-5 block text-sm" for="login-password">密码</label>
		<input
			id="login-password"
			type="password"
			autocomplete="current-password"
			required
			bind:value={password}
			class="mt-2 w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2.5"
		/>
		{#if error}<p role="alert" class="mt-4 text-sm text-rose-300">{error}</p>{/if}
		<button
			type="submit"
			disabled={busy}
			class="mt-6 w-full rounded-lg bg-blue-500 px-4 py-3 font-medium disabled:opacity-50"
		>
			{busy ? '正在登录…' : '登录'}
		</button>
		<div class="mt-5 flex justify-between text-sm text-blue-300">
			{#if $registrationOpen}<a href={resolve('/register')}>注册学生账号</a>{/if}
			{#if $passwordResetAvailable}<a href={resolve('/forgot-password')}>忘记密码？</a>{/if}
		</div>
		{#if !$passwordResetAvailable && $authMode === 'enabled'}
			<p class="mt-3 text-sm text-slate-400">忘记密码请联系管理员核验后重置。</p>
		{/if}
		{#if $authMode === 'disabled'}<p class="mt-5 text-sm text-slate-400">
				当前服务器尚未启用账号登录。
			</p>{/if}
		{#if $currentAccount}<p class="mt-5 text-sm text-slate-300">
				当前已登录：{$currentAccount.username || $currentAccount.email}
			</p>
			<a href={resolve('/account')} class="mt-2 inline-block text-sm text-blue-300"
				>前往账号页退出登录</a
			>
		{/if}
	</form>
</main>
