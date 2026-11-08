<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import {
		currentAccount,
		deleteAccount,
		exportAccount,
		importLegacyData,
		legacyDataKinds,
		logout,
		type PersonalKind
	} from '$lib/apis/auth';

	let legacy = $state<PersonalKind[]>([]);
	let password = $state('');
	let busy = $state(false);
	let message = $state('');
	let error = $state('');
	onMount(() => {
		legacy = legacyDataKinds();
	});

	async function importOld() {
		if (!confirm('这台电脑的旧数据可能属于其他使用者。确认它属于你的账号并导入吗？')) return;
		busy = true;
		error = '';
		try {
			const result = await importLegacyData();
			message = `已导入 ${result.imported.length} 类数据；${result.skipped.length} 类已有服务端数据，未覆盖。`;
			legacy = legacyDataKinds();
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '导入失败。';
		} finally {
			busy = false;
		}
	}

	async function download() {
		busy = true;
		error = '';
		try {
			const blob = await exportAccount();
			const url = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = url;
			anchor.download = 'tagent-personal-data.json';
			anchor.click();
			URL.revokeObjectURL(url);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '导出失败。';
		} finally {
			busy = false;
		}
	}

	async function removeAccount() {
		if (!confirm('确认注销账号并删除账号数据和学习记录？此操作无法撤销。')) return;
		busy = true;
		error = '';
		try {
			await deleteAccount(password);
			await logout();
			await goto(resolve('/welcome'));
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '注销失败。';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>我的账号 | TAgent</title></svelte:head>
<main class="min-h-screen bg-slate-950 px-5 py-10 text-white">
	<div class="mx-auto max-w-2xl">
		<a href={resolve('/agent-select')} class="text-sm text-blue-300">← 返回平台</a>
		<h1 class="mt-6 text-3xl font-semibold">我的账号</h1>
		{#if $currentAccount}
			<p class="mt-3 text-slate-300">
				{$currentAccount.name || '未填写姓名'} · {$currentAccount.email}
			</p>
		{/if}
		<section class="mt-8 rounded-xl border border-white/15 p-6">
			<h2 class="text-lg font-medium">个人数据</h2>
			<p class="mt-2 text-sm text-slate-300">学习内容保存在账号中。导出文件会隐藏已保存的密钥。</p>
			<button
				type="button"
				disabled={busy}
				onclick={download}
				class="mt-4 rounded-lg bg-blue-500 px-4 py-2 disabled:opacity-50">导出我的数据</button
			>
		</section>
		{#if legacy.length}
			<section class="mt-5 rounded-xl border border-amber-500/40 p-6">
				<h2 class="text-lg font-medium">发现这台浏览器的旧数据</h2>
				<p class="mt-2 text-sm text-slate-300">
					这些内容没有账号归属，可能来自共用电脑。仅在确认属于你时导入；不会覆盖账号中已有的数据。
				</p>
				<button
					type="button"
					disabled={busy}
					onclick={importOld}
					class="mt-4 rounded-lg border border-amber-400 px-4 py-2 text-amber-200 disabled:opacity-50"
					>确认属于我并导入</button
				>
			</section>
		{/if}
		<section class="mt-5 rounded-xl border border-rose-500/30 p-6">
			<h2 class="text-lg font-medium">注销账号</h2>
			<p class="mt-2 text-sm text-slate-300">
				注销会删除该账号的个人内容和学习记录。请先导出需要保留的数据。
			</p>
			<label for="account-password" class="mt-4 block text-sm">输入当前密码</label>
			<input
				id="account-password"
				type="password"
				autocomplete="current-password"
				bind:value={password}
				class="mt-2 w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2"
			/>
			<button
				type="button"
				disabled={busy || !password}
				onclick={removeAccount}
				class="mt-4 rounded-lg bg-rose-700 px-4 py-2 disabled:opacity-50">注销账号</button
			>
		</section>
		{#if message}<p role="status" class="mt-5 text-emerald-300">{message}</p>{/if}
		{#if error}<p role="alert" class="mt-5 text-rose-300">{error}</p>{/if}
	</div>
</main>
