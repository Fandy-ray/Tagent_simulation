<script lang="ts">
	type MockUser = {
		id: number;
		name: string;
		email: string;
		role: 'admin' | 'user';
		lastActive: string;
		createdAt: string;
	};

	let users = $state<MockUser[]>([
		{
			id: 1,
			name: '管理员',
			email: 'admin@example.com',
			role: 'admin',
			lastActive: '几分钟前',
			createdAt: '2026-06-06'
		}
	]);
	let query = $state('');
	let sortKey = $state<'name' | 'email' | 'lastActive' | 'createdAt'>('createdAt');
	let sortDirection = $state<'asc' | 'desc'>('desc');
	let modalOpen = $state(false);
	let editingId = $state<number | null>(null);
	let name = $state('');
	let email = $state('');
	let role = $state<'admin' | 'user'>('user');
	let formError = $state('');

	let filteredUsers = $derived(
		users
			.filter((item) =>
				`${item.name} ${item.email} ${item.role}`.toLowerCase().includes(query.trim().toLowerCase())
			)
			.sort((a, b) => {
				const result = String(a[sortKey]).localeCompare(String(b[sortKey]));
				return sortDirection === 'asc' ? result : -result;
			})
	);

	function sortBy(key: typeof sortKey) {
		if (sortKey === key) sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
		else {
			sortKey = key;
			sortDirection = 'asc';
		}
	}

	function openModal(user?: MockUser) {
		editingId = user?.id ?? null;
		name = user?.name ?? '';
		email = user?.email ?? '';
		role = user?.role ?? 'user';
		formError = '';
		modalOpen = true;
	}

	function saveUser() {
		const cleanName = name.trim();
		const cleanEmail = email.trim();
		if (!cleanName || !cleanEmail) {
			formError = '请填写姓名和邮箱';
			return;
		}
		if (!/^\S+@\S+\.\S+$/.test(cleanEmail)) {
			formError = '请输入有效的邮箱地址';
			return;
		}
		if (
			users.some(
				(item) => item.email.toLowerCase() === cleanEmail.toLowerCase() && item.id !== editingId
			)
		) {
			formError = '该邮箱已存在';
			return;
		}
		if (editingId === null) {
			users = [
				...users,
				{
					id: Date.now(),
					name: cleanName,
					email: cleanEmail,
					role,
					lastActive: '从未活跃',
					createdAt: new Date().toISOString().slice(0, 10)
				}
			];
		} else {
			users = users.map((item) =>
				item.id === editingId ? { ...item, name: cleanName, email: cleanEmail, role } : item
			);
		}
		modalOpen = false;
	}
</script>

<section class="min-h-full text-gray-900 dark:text-gray-100">
	<header
		class="flex items-center justify-between border-b border-gray-200 pb-3 dark:border-gray-800"
	>
		<h1 class="text-lg font-semibold">
			用户 <span class="ml-1 text-sm font-normal text-gray-500 dark:text-gray-400"
				>{users.length}</span
			>
		</h1>
		<div class="flex items-center gap-2">
			<label
				class="dark:focus-within:bg-gray-850 flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-gray-500 transition focus-within:bg-gray-100"
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
					><path
						fill-rule="evenodd"
						d="M9 3.5a5.5 5.5 0 1 0 3.445 9.788l3.328 3.328a.75.75 0 1 0 1.06-1.06l-3.328-3.329A5.5 5.5 0 0 0 9 3.5ZM5 9a4 4 0 1 1 8 0 4 4 0 0 1-8 0Z"
						clip-rule="evenodd"
					/></svg
				>
				<input
					class="w-24 bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-500 focus:w-40 dark:text-gray-100"
					bind:value={query}
					placeholder="搜索"
					aria-label="搜索用户"
				/>
			</label>
			<button
				class="dark:hover:bg-gray-850 flex size-7 items-center justify-center rounded-lg text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:hover:text-white"
				onclick={() => openModal()}
				aria-label="添加用户"
				title="添加用户"
			>
				<svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
					><path
						d="M10 4a.75.75 0 0 1 .75.75v4.5h4.5a.75.75 0 0 1 0 1.5h-4.5v4.5a.75.75 0 0 1-1.5 0v-4.5h-4.5a.75.75 0 0 1 0-1.5h4.5v-4.5A.75.75 0 0 1 10 4Z"
					/></svg
				>
			</button>
		</div>
	</header>

	<div class="overflow-x-auto">
		<table
			class="w-full min-w-[1100px] table-fixed border-collapse text-left text-xs whitespace-nowrap"
		>
			<colgroup>
				<col class="w-[140px]" />
				<col class="w-[220px]" />
				<col class="w-[360px]" />
				<col class="w-[150px]" />
				<col class="w-[170px]" />
				<col class="w-[48px]" />
			</colgroup>
			<thead class="border-b border-gray-200 text-gray-500 dark:border-gray-800 dark:text-gray-400">
				<tr>
					<th class="px-2 py-2 font-medium">角色</th>
					<th class="px-2 py-2 font-medium"><button onclick={() => sortBy('name')}>名称</button></th
					>
					<th class="px-3 py-3 font-medium"
						><button onclick={() => sortBy('email')}>电子邮箱</button></th
					>
					<th class="px-3 py-3 font-medium"
						><button onclick={() => sortBy('lastActive')}>最后在线时间</button></th
					>
					<th class="px-3 py-3 font-medium"
						><button onclick={() => sortBy('createdAt')}>创建于</button></th
					>
					<th class="px-2 py-2"></th>
				</tr>
			</thead>
			<tbody>
				{#each filteredUsers as user (user.id)}
					<tr
						class="border-b border-gray-100 text-gray-700 dark:border-gray-800/80 dark:text-gray-300"
					>
						<td class="px-2 py-3 whitespace-nowrap"
							><span
								class="rounded-md bg-blue-100 px-2 py-1 text-[10px] font-medium whitespace-nowrap text-blue-700 dark:bg-blue-950/70 dark:text-blue-300"
								>{user.role === 'admin' ? '管理员' : '普通用户'}</span
							></td
						>
						<td class="px-3 py-3 whitespace-nowrap"
							><span class="inline-flex items-center gap-2"
								><span
									class="flex size-6 items-center justify-center rounded-full bg-amber-500 text-[10px] font-semibold text-white"
									>{user.name.slice(0, 1)}</span
								><span>{user.name}</span><span
									class="size-1.5 rounded-full bg-emerald-500"
									aria-label="在线"
								></span></span
							></td
						>
						<td class="px-3 py-3">{user.email}</td>
						<td class="px-3 py-3">{user.lastActive}</td>
						<td class="px-3 py-3">{user.createdAt}</td>
						<td class="px-3 py-3 text-right"
							><button
								class="rounded-md p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-gray-800 dark:hover:text-white"
								onclick={() => openModal(user)}
								aria-label="编辑用户"
								title="编辑用户"
								><svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
									><path
										d="M13.586 3.586a2 2 0 0 1 2.828 2.828l-8.5 8.5a2 2 0 0 1-.878.513l-3 .857a.75.75 0 0 1-.927-.927l.857-3a2 2 0 0 1 .513-.878l8.5-8.5ZM12.5 5.5l2 2"
									/></svg
								></button
							></td
						>
					</tr>
				{:else}
					<tr
						><td colspan="6" class="px-3 py-12 text-center text-sm text-gray-500">没有找到用户</td
						></tr
					>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="mt-2 text-right text-[10px] text-gray-400">ⓘ 点击用户角色按钮可以更改用户的角色</p>
</section>

{#if modalOpen}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget) modalOpen = false;
		}}
	>
		<div
			class="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-5 shadow-2xl dark:border-gray-700 dark:bg-gray-900"
			role="dialog"
			aria-modal="true"
			aria-labelledby="user-modal-title"
			tabindex="-1"
		>
			<h2 id="user-modal-title" class="text-lg font-semibold">
				{editingId === null ? '添加用户' : '编辑用户'}
			</h2>
			<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">修改仅保存在当前页面会话中。</p>
			<form
				class="mt-5 space-y-4"
				onsubmit={(event) => {
					event.preventDefault();
					saveUser();
				}}
			>
				<label class="block space-y-1.5"
					><span class="text-sm font-medium">姓名</span><input
						class="w-full rounded-xl border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-gray-700"
						bind:value={name}
					/></label
				>
				<label class="block space-y-1.5"
					><span class="text-sm font-medium">邮箱</span><input
						class="w-full rounded-xl border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-gray-700"
						bind:value={email}
						type="email"
					/></label
				>
				<label class="block space-y-1.5"
					><span class="text-sm font-medium">角色</span><select
						class="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm outline-none dark:border-gray-700 dark:bg-gray-900"
						bind:value={role}
						><option value="user">普通用户</option><option value="admin">管理员</option></select
					></label
				>
				{#if formError}<p class="text-sm text-red-600" role="alert">{formError}</p>{/if}
				<div class="flex justify-end gap-2 pt-1">
					<button
						type="button"
						class="rounded-xl px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
						onclick={() => (modalOpen = false)}>取消</button
					><button
						type="submit"
						class="rounded-xl bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 dark:bg-white dark:text-gray-900"
						>保存</button
					>
				</div>
			</form>
		</div>
	</div>
{/if}
