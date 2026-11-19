<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import {
		changePassword,
		currentAccount,
		deleteAccount,
		exportAccount,
		exportPendingPersonalData,
		importLegacyData,
		legacyDataOverview,
		logout,
		syncError,
		type LegacyDataOverview
	} from '$lib/apis/auth';

	let legacy = $state<LegacyDataOverview[]>([]);
	let password = $state('');
	let currentPassword = $state('');
	let nextPassword = $state('');
	let repeatPassword = $state('');
	let busy = $state(false);
	let message = $state('');
	let error = $state('');
	onMount(() => {
		legacy = legacyDataOverview();
	});

	async function importOld() {
		if (!confirm('这台电脑的旧数据可能属于其他使用者。确认它属于你的账号并导入吗？')) return;
		busy = true;
		error = '';
		try {
			const result = await importLegacyData();
			message = `已导入 ${result.imported.length} 类数据到通用区；${result.skipped.length} 类已有服务端数据，未覆盖。`;
			legacy = legacyDataOverview();
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
			anchor.download = 'tagent-account-data.zip';
			anchor.click();
			URL.revokeObjectURL(url);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '导出失败。';
		} finally {
			busy = false;
		}
	}

	function downloadPending() {
		error = '';
		try {
			const blob = exportPendingPersonalData();
			const url = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = url;
			anchor.download = 'tagent-unsynced-draft.json';
			anchor.click();
			URL.revokeObjectURL(url);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '导出本机草稿失败。';
		}
	}

	async function leave() {
		busy = true;
		error = '';
		try {
			await logout();
			await goto(resolve('/login'));
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '退出失败，请稍后重试。';
		} finally {
			busy = false;
		}
	}

	async function changeOwnPassword(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		if (nextPassword !== repeatPassword) {
			error = '两次输入的新密码不一致。';
			return;
		}
		busy = true;
		try {
			await changePassword(currentPassword, nextPassword);
			await logout();
			await goto(resolve('/login'));
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '修改密码失败。';
		} finally {
			currentPassword = '';
			nextPassword = '';
			repeatPassword = '';
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
				{$currentAccount.name || '未填写姓名'} · {$currentAccount.username || $currentAccount.email}
			</p>
			<button
				type="button"
				disabled={busy}
				onclick={leave}
				class="mt-3 text-sm text-blue-300 disabled:opacity-50">退出登录</button
			>
		{/if}
		<section class="mt-8 rounded-xl border border-white/15 p-6">
			<h2 class="text-lg font-medium">个人数据</h2>
			<p class="mt-2 text-sm text-slate-300">
				导出包包含学习内容、笔记和资料。模型密钥保留为加密数据，换服务器时需要重新配置。
			</p>
			<button
				type="button"
				disabled={busy}
				onclick={download}
				class="mt-4 rounded-lg bg-blue-500 px-4 py-2 disabled:opacity-50">导出我的数据</button
			>
			{#if $syncError}
				<div class="mt-4 rounded-lg border border-amber-400/40 p-3 text-sm text-amber-100">
					<p>本机有未同步草稿。导出文件可能包含连接密钥，请妥善保管。</p>
					<button type="button" onclick={downloadPending} class="mt-2 underline"
						>导出本机未同步草稿</button
					>
				</div>
			{/if}
		</section>
		<section class="mt-5 rounded-xl border border-white/15 p-6">
			<h2 class="text-lg font-medium">修改密码</h2>
			<p class="mt-2 text-sm text-slate-300">修改后，所有设备都需要用新密码重新登录。</p>
			<form onsubmit={changeOwnPassword} class="mt-4 space-y-3">
				<label for="current-password" class="block text-sm">当前密码</label>
				<input
					id="current-password"
					type="password"
					autocomplete="current-password"
					required
					bind:value={currentPassword}
					class="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2"
				/>
				<label for="new-password" class="block text-sm">新密码（至少 12 个字符）</label>
				<input
					id="new-password"
					type="password"
					autocomplete="new-password"
					minlength="12"
					required
					bind:value={nextPassword}
					class="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2"
				/>
				<label for="repeat-password" class="block text-sm">再次输入新密码</label>
				<input
					id="repeat-password"
					type="password"
					autocomplete="new-password"
					required
					bind:value={repeatPassword}
					class="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2"
				/>
				<button
					type="submit"
					disabled={busy}
					class="rounded-lg bg-blue-500 px-4 py-2 disabled:opacity-50">保存新密码</button
				>
			</form>
		</section>
		{#if legacy.length}
			<section class="mt-5 rounded-xl border border-amber-500/40 p-6">
				<h2 class="text-lg font-medium">发现这台浏览器的旧数据</h2>
				<p class="mt-2 text-sm text-slate-300">
					这些内容没有账号归属，可能来自共用电脑。仅在确认属于你时导入到通用区；不会覆盖账号中已有的数据。
				</p>
				<ul class="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-200">
					{#each legacy as entry (entry.kind)}
						<li>{entry.label}：{entry.summary}</li>
					{/each}
				</ul>
				<button
					type="button"
					disabled={busy || legacy.some((entry) => !entry.valid)}
					onclick={importOld}
					class="mt-4 rounded-lg border border-amber-400 px-4 py-2 text-amber-200 disabled:opacity-50"
					>确认属于我并导入</button
				>
			</section>
		{/if}
		<section class="mt-5 rounded-xl border border-rose-500/30 p-6">
			<h2 class="text-lg font-medium">注销账号</h2>
			<p class="mt-2 text-sm text-slate-300">
				注销会删除该账号的个人内容、笔记和学习记录。请先导出需要保留的数据。
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
