<script lang="ts">
	import { onMount } from 'svelte';
	import { identityRequest, type Account } from '$lib/apis/auth';
	let accounts = $state<Account[]>([]);
	let registrationOpen = $state(false);
	let busy = $state(false);
	let error = $state('');
	let message = $state('');

	async function load() {
		try {
			const [users, state] = await Promise.all([
				identityRequest<{ accounts: Account[] }>('/admin/accounts'),
				identityRequest<{ open: boolean }>('/admin/registration')
			]);
			accounts = users.accounts;
			registrationOpen = state.open;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '读取账号失败。';
		}
	}
	onMount(() => {
		void load();
	});

	async function toggleRegistration() {
		busy = true;
		error = '';
		message = '';
		try {
			const result = await identityRequest<{ open: boolean }>('/admin/registration', 'PUT', {
				open: !registrationOpen
			});
			registrationOpen = result.open;
			message = registrationOpen ? '学生注册已开放。' : '学生注册已暂停。';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '修改失败。';
		} finally {
			busy = false;
		}
	}

	async function toggleAccount(account: Account) {
		busy = true;
		error = '';
		message = '';
		try {
			const result = await identityRequest<{ account: Account }>(
				`/admin/accounts/${encodeURIComponent(account.id)}`,
				'PATCH',
				{ active: !account.active }
			);
			accounts = accounts.map((item) => (item.id === account.id ? result.account : item));
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '修改失败。';
		} finally {
			busy = false;
		}
	}
	async function finishDeletion(account: Account) {
		if (!confirm(`确认完成 ${account.email} 的待注销数据清理？`)) return;
		busy = true;
		error = '';
		message = '';
		try {
			await identityRequest(
				`/admin/accounts/${encodeURIComponent(account.id)}/complete-deletion`,
				'POST'
			);
			await load();
			message = '待注销账号已清理。';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : '清理失败。';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>账号管理 | TAgent</title></svelte:head>
<div class="p-6">
	<h1 class="text-2xl font-semibold">账号管理</h1>
	<p class="mt-2 text-sm text-gray-500">学生自行通过邮箱注册；管理员账号由部署人员单独创建。</p>
	<div
		class="mt-5 flex items-center gap-3 rounded-xl border border-gray-200 p-4 dark:border-white/15"
	>
		<span>学生注册：{registrationOpen ? '开放' : '暂停'}</span>
		<button
			type="button"
			disabled={busy}
			onclick={toggleRegistration}
			class="rounded-lg bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
			>{registrationOpen ? '暂停注册' : '开放注册'}</button
		>
	</div>
	{#if error}<p role="alert" class="mt-4 text-rose-600">{error}</p>{/if}
	{#if message}<p role="status" class="mt-4 text-emerald-600">{message}</p>{/if}
	<div class="mt-6 overflow-x-auto rounded-xl border border-gray-200 dark:border-white/15">
		<table class="w-full text-left text-sm">
			<thead class="bg-gray-50 dark:bg-white/5"
				><tr
					><th class="p-3">姓名</th><th class="p-3">邮箱</th><th class="p-3">角色</th><th
						class="p-3">验证</th
					><th class="p-3">状态</th><th class="p-3">操作</th></tr
				></thead
			>
			<tbody
				>{#each accounts as account (account.id)}
					<tr class="border-t border-gray-200 dark:border-white/10">
						<td class="p-3">{account.name || '—'}</td><td class="p-3">{account.email}</td>
						<td class="p-3">{account.role === 'admin' ? '管理员' : '学生'}</td>
						<td class="p-3">{account.verified ? '已验证' : '未验证'}</td>
						<td class="p-3"
							>{account.deletion_pending ? '待完成注销' : account.active ? '启用' : '停用'}</td
						>
						<td class="p-3"
							>{#if account.deletion_pending}<button
									type="button"
									disabled={busy}
									onclick={() => finishDeletion(account)}
									class="text-rose-600 disabled:opacity-50">完成清理</button
								>{:else if account.role === 'student'}<button
									type="button"
									disabled={busy}
									onclick={() => toggleAccount(account)}
									class="text-blue-600 disabled:opacity-50"
									>{account.active ? '停用' : '启用'}</button
								>{/if}</td
						>
					</tr>
				{/each}</tbody
			>
		</table>
	</div>
</div>
