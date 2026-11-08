<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/stores';

	import '../app.css';
	import { initI18n, setI18nContext } from '$lib/i18n';
	import { loadUserSettings } from '$lib/data/userSettings';
	import {
		authMode,
		authReady,
		currentAccount,
		flushPersonalWrites,
		hasPendingPersonalWrites,
		initializeAuth,
		syncError
	} from '$lib/apis/auth';

	// 初始化 i18n 并设置 context（在组件初始化时同步执行）。
	// 默认语言取设置里的（默认简体中文），不按浏览器语言猜：页面上大量文字本来就是写死的中文，
	// 英文系统的电脑上按浏览器猜成英文，就会一半中文一半英文。学生在设置里改了语言照样生效。
	initI18n(loadUserSettings().language || 'zh-CN');
	setI18nContext();

	let { children } = $props();

	// 断网时顶部一条提示：学生知道是网的问题，也知道已经写的东西没丢（压测 F4）
	let online = $state(true);
	const publicRoute = $derived(
		$page.url.pathname === '/' ||
			[
				'/welcome',
				'/login',
				'/register',
				'/verify-email',
				'/forgot-password',
				'/reset-password'
			].includes($page.url.pathname)
	);
	const allowed = $derived(
		$authMode === 'disabled' ||
			($authMode === 'enabled' && (publicRoute || ($authReady && Boolean($currentAccount))))
	);

	$effect(() => {
		if ($authMode !== 'enabled' || !$authReady) return;
		const path = $page.url.pathname;
		if (!publicRoute && !$currentAccount) {
			void goto(resolve(`/login?next=${encodeURIComponent(path + $page.url.search)}`));
		} else if (path.startsWith('/admin') && $currentAccount?.role !== 'admin') {
			void goto(resolve('/agent-select'));
		}
	});

	onMount(() => {
		void initializeAuth();
		const update = () => (online = navigator.onLine);
		const warnUnsaved = (event: BeforeUnloadEvent) => {
			if (!hasPendingPersonalWrites()) return;
			event.preventDefault();
			event.returnValue = '';
		};
		update();
		window.addEventListener('online', update);
		window.addEventListener('offline', update);
		window.addEventListener('beforeunload', warnUnsaved);
		return () => {
			window.removeEventListener('online', update);
			window.removeEventListener('offline', update);
			window.removeEventListener('beforeunload', warnUnsaved);
		};
	});
</script>

<svelte:head>
	<meta name="description" content="TAgent 系统建模与仿真智能教学平台" />
</svelte:head>

{#if !online}
	<div
		role="status"
		class="fixed inset-x-0 top-0 z-[100] bg-amber-400 px-4 py-1.5 text-center text-xs font-medium text-gray-950 shadow"
	>
		{$authMode === 'enabled'
			? '网络已断开：账号数据暂不能编辑，请恢复连接。'
			: '网络已断开：已经写的内容都还在，恢复连接后再继续。'}
	</div>
{/if}
{#if $syncError}
	<div
		role="alert"
		class="fixed inset-x-0 top-0 z-[101] bg-rose-600 px-4 py-2 text-center text-sm text-white"
	>
		{$syncError} 请保留本页；可重试同步，发生冲突时先到“我的账号”导出本机草稿。
		<button
			type="button"
			class="ml-3 underline"
			onclick={() => void flushPersonalWrites().catch(() => {})}>重试同步</button
		>
	</div>
{/if}
{#if !online && $authMode === 'enabled'}
	<div class="fixed inset-0 z-[99] bg-slate-950/65" aria-hidden="true"></div>
{/if}

{#if allowed}
	{@render children()}
{:else if $authMode === 'unavailable'}
	<main class="flex min-h-screen items-center justify-center bg-slate-950 p-6 text-white">
		<div class="max-w-md rounded-2xl border border-white/15 p-8 text-center">
			<h1 class="text-xl font-semibold">暂时无法连接账号服务</h1>
			<p class="mt-3 text-sm text-slate-300">
				请检查网络或稍后刷新页面。为保护账号数据，当前不会打开本机缓存的内容。
			</p>
			<button class="mt-6 rounded-lg bg-blue-500 px-4 py-2" onclick={() => location.reload()}
				>重新连接</button
			>
		</div>
	</main>
{:else}
	<div class="flex min-h-screen items-center justify-center bg-slate-950 text-sm text-slate-300">
		正在检查登录状态…
	</div>
{/if}
