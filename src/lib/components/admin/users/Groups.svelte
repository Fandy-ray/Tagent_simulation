<script lang="ts">
	import { DEFAULT_PERMISSIONS } from '$lib/constants/permissions';

	type PermissionKey = keyof typeof DEFAULT_PERMISSIONS;
	type PermissionState = { [K in PermissionKey]: { [P in keyof (typeof DEFAULT_PERMISSIONS)[K]]: boolean } };
	type PermissionRow = { key: string; label: string; childOf?: string };
	type PermissionSection = { key: PermissionKey; label: string; rows: PermissionRow[] };
	type MockGroup = { id: number; name: string; description: string; memberCount: number; permissions: PermissionState; shareWith: string };

	const clonePermissionState = (value: PermissionState): PermissionState => JSON.parse(JSON.stringify(value)) as PermissionState;
	const cloneDefaults = (): PermissionState => clonePermissionState(DEFAULT_PERMISSIONS as PermissionState);
	const permissionSections: PermissionSection[] = [
		{ key: 'workspace', label: '工作空间权限', rows: [
			{ key: 'models', label: '模型访问' }, { key: 'models_import', label: '导入模型', childOf: 'models' }, { key: 'models_export', label: '导出模型', childOf: 'models' },
			{ key: 'knowledge', label: '知识库访问' }, { key: 'prompts', label: '提示词访问' }, { key: 'prompts_import', label: '导入提示词', childOf: 'prompts' }, { key: 'prompts_export', label: '导出提示词', childOf: 'prompts' },
			{ key: 'tools', label: '工具访问' }, { key: 'tools_import', label: '导入工具', childOf: 'tools' }, { key: 'tools_export', label: '导出工具', childOf: 'tools' }, { key: 'skills', label: '技能访问' }
		] },
		{ key: 'sharing', label: '共享权限', rows: [
			{ key: 'models', label: '模型共享' }, { key: 'public_models', label: '公开共享模型', childOf: 'models' },
			{ key: 'knowledge', label: '知识库共享' }, { key: 'public_knowledge', label: '公开共享知识库', childOf: 'knowledge' },
			{ key: 'prompts', label: '提示词共享' }, { key: 'public_prompts', label: '公开共享提示词', childOf: 'prompts' },
			{ key: 'tools', label: '工具共享' }, { key: 'public_tools', label: '公开共享工具', childOf: 'tools' },
			{ key: 'skills', label: '技能共享' }, { key: 'public_skills', label: '公开共享技能', childOf: 'skills' },
			{ key: 'notes', label: '笔记共享' }, { key: 'public_notes', label: '公开共享笔记', childOf: 'notes' }
		] },
		{ key: 'access_grants', label: '访问授权', rows: [{ key: 'allow_users', label: '允许与用户共享' }] },
		{ key: 'chat', label: '对话权限', rows: [
			{ key: 'file_upload', label: '允许上传文件' }, { key: 'web_upload', label: '允许网页上传' }, { key: 'controls', label: '允许对话控制' },
			{ key: 'valves', label: '允许对话阀门', childOf: 'controls' }, { key: 'system_prompt', label: '允许设置系统提示词', childOf: 'controls' }, { key: 'params', label: '允许设置模型参数', childOf: 'controls' },
			{ key: 'edit', label: '允许编辑对话' }, { key: 'delete', label: '允许删除对话' }, { key: 'delete_message', label: '允许删除消息' }, { key: 'continue_response', label: '允许继续回答' },
			{ key: 'regenerate_response', label: '允许重新生成回答' }, { key: 'rate_response', label: '允许评价回答' }, { key: 'share', label: '允许分享对话' }, { key: 'export', label: '允许导出对话' },
			{ key: 'stt', label: '允许语音转文字' }, { key: 'tts', label: '允许文字转语音' }, { key: 'call', label: '允许语音通话' }, { key: 'multiple_models', label: '允许多模型对话' },
			{ key: 'temporary', label: '允许临时对话' }, { key: 'temporary_enforced', label: '强制临时对话', childOf: 'temporary' }
		] },
		{ key: 'features', label: '功能权限', rows: [
			{ key: 'api_keys', label: 'API 密钥' }, { key: 'notes', label: '笔记' }, { key: 'channels', label: '频道' }, { key: 'folders', label: '文件夹' },
			{ key: 'direct_tool_servers', label: '直接连接工具服务器' }, { key: 'web_search', label: '网页搜索' }, { key: 'image_generation', label: '图像生成' }, { key: 'code_interpreter', label: '代码解释器' }, { key: 'memories', label: '记忆' }
		] },
		{ key: 'settings', label: '设置权限', rows: [{ key: 'interface', label: '界面设置访问' }] }
	];
	const permissionLabels = new Map(permissionSections.flatMap((section) => section.rows.filter((row) => !row.childOf).map((row) => [`${section.key}.${row.key}`, row.label] as const)));

	let groups = $state<MockGroup[]>([]);
	let query = $state('');
	let sort = $state<'name' | 'members'>('members');
	let modalOpen = $state(false);
	let defaultPermissionsOpen = $state(false);
	let editingId = $state<number | null>(null);
	let name = $state('');
	let description = $state('');
	let permissions = $state<PermissionState>(cloneDefaults());
	let defaultPermissions = $state<PermissionState>(cloneDefaults());
	let activeTab = $state<'general' | 'permissions'>('general');
	let shareWith = $state('成员');
	let formError = $state('');
	let filteredGroups = $derived(groups.filter((group) => `${group.name} ${group.description}`.toLowerCase().includes(query.trim().toLowerCase())).sort((a, b) => sort === 'name' ? a.name.localeCompare(b.name) : b.memberCount - a.memberCount));
	let grantedPermissions = $derived(permissionSections.flatMap((section) => section.rows.filter((row) => !row.childOf && permissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]]).map((row) => permissionLabels.get(`${section.key}.${row.key}`) ?? row.label)));

	function openGroup(group?: MockGroup) {
		editingId = group?.id ?? null;
		name = group?.name ?? '';
		description = group?.description ?? '';
		permissions = group ? clonePermissionState(group.permissions) : clonePermissionState(defaultPermissions);
		shareWith = group?.shareWith ?? '成员';
		activeTab = 'general';
		formError = '';
		modalOpen = true;
	}

	function saveGroup() {
		const cleanName = name.trim();
		if (!cleanName) { formError = '请输入用户组名称'; activeTab = 'general'; return; }
		if (groups.some((group) => group.name.toLowerCase() === cleanName.toLowerCase() && group.id !== editingId)) { formError = '该用户组名称已存在'; activeTab = 'general'; return; }
		if (editingId === null) groups = [...groups, { id: Date.now(), name: cleanName, description: description.trim(), memberCount: 0, permissions: clonePermissionState(permissions), shareWith }];
		else groups = groups.map((group) => group.id === editingId ? { ...group, name: cleanName, description: description.trim(), permissions: structuredClone(permissions), shareWith } : group);
		modalOpen = false;
	}

	function togglePermission(section: PermissionKey, key: string, value: boolean) {
		permissions = { ...permissions, [section]: { ...permissions[section], [key]: value } } as PermissionState;
	}

	function toggleDefaultPermission(section: PermissionKey, key: string, value: boolean) {
		defaultPermissions = { ...defaultPermissions, [section]: { ...defaultPermissions[section], [key]: value } } as PermissionState;
	}

	function isChildVisible(section: PermissionSection, row: PermissionRow, state: PermissionState) {
		if (!row.childOf) return true;
		return Boolean(state[section.key][row.childOf as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]]);
	}
</script>

<section class="space-y-3 text-gray-900 dark:text-gray-100">
	<header class="flex items-center justify-between">
		<h1 class="text-lg font-semibold">用户组 <span class="ml-1 text-sm font-normal text-gray-500 dark:text-gray-400">{groups.length}</span></h1>
		<button class="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700" onclick={() => openGroup()}>
			<svg viewBox="0 0 20 20" fill="currentColor" class="size-3.5"><path d="M10 4a.75.75 0 0 1 .75.75v4.5h4.5a.75.75 0 0 1 0 1.5h-4.5v4.5a.75.75 0 0 1-1.5 0v-4.5h-4.5a.75.75 0 0 1 0-1.5h4.5v-4.5A.75.75 0 0 1 10 4Z" /></svg>
			新建用户组
		</button>
	</header>

	<div class="overflow-hidden rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
		<div class="flex items-center justify-between border-b border-gray-100 px-3 py-2.5 dark:border-gray-800">
			<label class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400"><svg viewBox="0 0 20 20" fill="currentColor" class="size-4"><path fill-rule="evenodd" d="M9 3.5a5.5 5.5 0 1 0 3.445 9.788l3.328 3.328a.75.75 0 1 0 1.06-1.06l-3.328-3.329A5.5 5.5 0 0 0 9 3.5ZM5 9a4 4 0 1 1 8 0 4 4 0 0 1-8 0Z" clip-rule="evenodd" /></svg><input class="w-44 bg-transparent text-xs outline-none placeholder:text-gray-500" bind:value={query} placeholder="搜索用户组" aria-label="搜索用户组" /></label>
			<select class="rounded-lg bg-gray-50 px-2.5 py-1.5 text-xs text-gray-700 outline-none dark:bg-gray-850 dark:text-gray-300" bind:value={sort} aria-label="排序方式"><option value="members">成员</option><option value="name">名称</option></select>
		</div>
		{#if filteredGroups.length}
			<div class="grid gap-2 p-3 xl:grid-cols-2">
				{#each filteredGroups as group (group.id)}
					<article class="rounded-xl border border-gray-100 p-3 dark:border-gray-800"><div class="flex items-start justify-between"><div><h2 class="text-sm font-medium">{group.name}</h2><p class="mt-1 text-xs text-gray-500">{group.description || '暂无描述'}</p></div><div class="flex gap-2"><button class="text-xs text-gray-500 hover:text-gray-900 dark:hover:text-white" onclick={() => openGroup(group)}>编辑</button><button class="text-xs text-red-500" onclick={() => groups = groups.filter((item) => item.id !== group.id)}>删除</button></div></div><p class="mt-3 border-t border-gray-100 pt-2 text-xs text-gray-500 dark:border-gray-800">成员 {group.memberCount}</p><div class="mt-2 flex flex-wrap gap-1">{#each permissionSections.flatMap((section) => section.rows.filter((row) => !row.childOf && group.permissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]]).map((row) => row.label)) as label (label)}<span class="rounded-full bg-gray-100 px-2 py-1 text-[10px] dark:bg-gray-800">{label}</span>{/each}</div></article>
				{/each}
			</div>
		{:else}
			<div class="flex min-h-[190px] flex-col items-center justify-center px-4 py-10 text-center">
				<svg viewBox="0 0 24 24" fill="currentColor" class="size-8 text-violet-500"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 20a5 5 0 0 1 10 0v1H5v-1ZM17.5 11a3 3 0 1 0-1.5-5.598 5.5 5.5 0 0 1 0 8.196A4.98 4.98 0 0 1 19 18v1h-2v-1a5 5 0 0 0-1.4-3.46A5.48 5.48 0 0 0 17.5 11Z" /></svg>
				<h2 class="mt-3 text-sm font-medium">暂无用户组</h2>
				<p class="mt-1 text-xs text-gray-500 dark:text-gray-400">使用用户组来管理用户并分配权限。</p>
			</div>
		{/if}
	</div>

	<button class="flex w-full items-center justify-between rounded-xl px-1 py-2 text-left transition hover:bg-gray-100/70 dark:hover:bg-gray-850" onclick={() => defaultPermissionsOpen = true}>
		<span class="flex items-center gap-2.5"><span class="flex size-8 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800"><svg viewBox="0 0 20 20" fill="currentColor" class="size-4"><path d="M10 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM4.75 16a4.75 4.75 0 0 1 9.5 0v.25h-9.5V16ZM15.2 8.1a2.25 2.25 0 1 0-1.3-4.1 4.5 4.5 0 0 1 .3 5.2c.35.15.68.34.98.56a2.25 2.25 0 0 0 .02-1.66ZM16.2 12.3a5.7 5.7 0 0 1 .55 2.45v.25h-1.1A6.2 6.2 0 0 0 14.5 11c.7.27 1.3.72 1.7 1.3Z" /></svg></span><span><span class="block text-xs font-medium">默认权限</span><span class="mt-0.5 block text-[10px] text-gray-500 dark:text-gray-400">应用于所有具有“普通用户”角色的用户</span></span></span>
		<svg viewBox="0 0 20 20" fill="currentColor" class="size-4 text-gray-400"><path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 0 1 .02-1.06L10.94 10 7.23 6.29a.75.75 0 1 1 1.06-1.06l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.08-.02Z" clip-rule="evenodd" /></svg>
	</button>
</section>

{#if modalOpen || defaultPermissionsOpen}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="presentation" onclick={(event) => { if (event.target === event.currentTarget) { modalOpen = false; defaultPermissionsOpen = false; } }}>
		<section class="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white text-gray-900 shadow-2xl dark:border dark:border-gray-800 dark:bg-[#171717] dark:text-gray-100" role="dialog" aria-modal="true" aria-labelledby="group-modal-title" tabindex="-1">
			<header class="flex items-center justify-between px-6 pb-2 pt-5">
				<h2 id="group-modal-title" class="text-xl font-semibold">{defaultPermissionsOpen ? '默认权限' : editingId === null ? '添加用户组' : '编辑用户组'}</h2>
				<button type="button" class="rounded-md p-1 text-gray-400 transition hover:text-gray-900 dark:hover:text-white" onclick={() => { modalOpen = false; defaultPermissionsOpen = false; }} aria-label="关闭">
					<svg viewBox="0 0 20 20" fill="currentColor" class="size-5"><path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" /></svg>
				</button>
			</header>

			{#if !defaultPermissionsOpen}
				<nav class="flex items-center gap-5 px-6 pb-3 text-sm font-medium" aria-label="用户组设置">
					<button type="button" class="flex items-center gap-2 transition {activeTab === 'general' ? 'text-gray-900 dark:text-white' : 'text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200'}" onclick={() => activeTab = 'general'}>
						<svg viewBox="0 0 16 16" fill="currentColor" class="size-4"><path fill-rule="evenodd" d="M6.955 1.45A.5.5 0 0 1 7.452 1h1.096a.5.5 0 0 1 .497.45l.17 1.699c.484.12.94.312 1.356.562l1.321-1.081a.5.5 0 0 1 .67.033l.774.775a.5.5 0 0 1 .034.67l-1.08 1.32c.25.417.44.873.561 1.357l1.699.17a.5.5 0 0 1 .45.497v1.096a.5.5 0 0 1-.45.497l-1.699.17c-.12.484-.312.94-.562 1.356l1.082 1.322a.5.5 0 0 1-.034.67l-.774.774a.5.5 0 0 1-.67.033l-1.322-1.08c-.416.25-.872.44-1.356.561l-.17 1.699a.5.5 0 0 1-.497.45H7.452a.5.5 0 0 1-.497-.45l-.17-1.699a4.973 4.973 0 0 1-1.356-.562L4.108 13.37a.5.5 0 0 1-.67-.033l-.774-.775a.5.5 0 0 1-.034-.67l1.08-1.32a4.971 4.971 0 0 1-.561-1.357l-1.699-.17A.5.5 0 0 1 1 8.548V7.452a.5.5 0 0 1 .45-.497l1.699-.17c.12-.484.312-.94.562-1.356L2.629 4.107a.5.5 0 0 1 .034-.67l.774-.774a.5.5 0 0 1 .67-.033L5.43 3.71a4.97 4.97 0 0 1 1.356-.561l.17-1.699ZM6 8c0 .538.212 1.026.558 1.385l.057.057a2 2 0 0 0 2.828-2.828l-.058-.056A2 2 0 0 0 6 8Z" clip-rule="evenodd" /></svg>
						通用
					</button>
					<button type="button" class="flex items-center gap-2 transition {activeTab === 'permissions' ? 'text-gray-900 dark:text-white' : 'text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200'}" onclick={() => activeTab = 'permissions'}>
						<svg viewBox="0 0 16 16" fill="currentColor" class="size-4"><path d="M11.05 2.05a2.5 2.5 0 0 1 2.9 3.28l-2.1 2.1 1.05 1.05a.75.75 0 0 1-1.06 1.06L10.79 8.5l-5.3 5.3a1.5 1.5 0 0 1-.34.22l-2.6 1.3a.75.75 0 0 1-1.05-.83l.6-2.78a1.5 1.5 0 0 1 .2-.47l5.32-5.32-.54-.54a.75.75 0 0 1 0-1.06l.68-.68a2.5 2.5 0 0 1 3.29.36Z" /></svg>
						权限
					</button>
				</nav>
			{/if}

			<div class="min-h-[220px] flex-1 overflow-y-auto px-6">
				{#if defaultPermissionsOpen}
					<div class="space-y-5 pb-4">{#each permissionSections as section (section.key)}<section class="border-b border-gray-100 pb-3 last:border-0 dark:border-gray-800"><h3 class="mb-2 text-sm font-medium">{section.label}</h3><div class="space-y-1">{#each section.rows as row (row.key)}{#if isChildVisible(section, row, defaultPermissions)}<label class="flex min-h-8 items-center justify-between gap-4 {row.childOf ? 'ml-3 border-l border-gray-200 pl-3 dark:border-gray-700' : ''}"><span class="text-xs {row.childOf ? 'text-gray-500 dark:text-gray-400' : 'font-medium'}">{row.label}</span><button type="button" role="switch" aria-label={'默认权限：' + row.label} aria-checked={Boolean(defaultPermissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]])} class="flex h-[1.125rem] w-8 shrink-0 items-center rounded-full px-1 outline outline-1 outline-gray-700 transition {defaultPermissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]] ? 'bg-emerald-700' : 'bg-transparent'}" onclick={() => toggleDefaultPermission(section.key, row.key, !Boolean(defaultPermissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]]))}><span class="size-3 rounded-full bg-white transition-transform {defaultPermissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]] ? 'translate-x-3' : ''}"></span></button></label>{/if}{/each}</div></section>{/each}</div>
				{:else if activeTab === 'general'}
					<form onsubmit={(event) => { event.preventDefault(); saveGroup(); }} id="group-form">
						<label class="block pb-2"><span class="text-xs text-gray-500 dark:text-gray-400">名称</span><input class="mt-1 w-full bg-transparent text-sm outline-none placeholder:text-gray-400 dark:placeholder:text-gray-500" bind:value={name} placeholder="用户组名称" /></label>
						<label class="block border-t border-gray-100 py-2 dark:border-gray-800"><span class="text-xs text-gray-500 dark:text-gray-400">描述</span><textarea class="mt-1 min-h-[56px] w-full resize-none bg-transparent text-sm outline-none placeholder:text-gray-400 dark:placeholder:text-gray-500" bind:value={description} placeholder="用户组描述"></textarea></label>
						<div class="mt-3 border-t border-gray-100 pt-3 dark:border-gray-800">
							<p class="text-xs text-gray-500 dark:text-gray-400">设置</p>
							<div class="mt-2 flex items-center justify-between border-b border-gray-100 py-2 text-sm dark:border-gray-800">
								<span>允许谁可以分享到此组</span>
								<select class="bg-transparent text-sm font-medium outline-none dark:text-gray-100" bind:value={shareWith} aria-label="分享范围">
									<option value="成员">成员</option>
									<option value="任何人">任何人</option>
									<option value="仅管理员">仅管理员</option>
								</select>
							</div>
						</div>
						{#if formError}<p class="mt-2 text-sm text-red-600" role="alert">{formError}</p>{/if}
					</form>
				{:else}
					<div class="space-y-5 pb-4">{#each permissionSections as section (section.key)}<section class="border-b border-gray-100 pb-3 last:border-0 dark:border-gray-800"><h3 class="mb-2 text-sm font-medium">{section.label}</h3><div class="space-y-1">{#each section.rows as row (row.key)}{#if isChildVisible(section, row, permissions)}<label class="flex min-h-8 items-center justify-between gap-4 {row.childOf ? 'ml-3 border-l border-gray-200 pl-3 dark:border-gray-700' : ''}"><span class="text-xs {row.childOf ? 'text-gray-500 dark:text-gray-400' : 'font-medium'}">{row.label}{#if defaultPermissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]]}<span class="ml-1 text-[10px] text-gray-400">（默认开启）</span>{/if}</span><button type="button" role="switch" aria-label={row.label} aria-checked={Boolean(permissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]])} class="flex h-[1.125rem] w-8 shrink-0 items-center rounded-full px-1 outline outline-1 outline-gray-700 transition {permissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]] ? 'bg-emerald-700' : 'bg-transparent'}" onclick={() => togglePermission(section.key, row.key, !Boolean(permissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]]))}><span class="size-3 rounded-full bg-white transition-transform {permissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]] ? 'translate-x-3' : ''}"></span></button></label>{#if defaultPermissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]] && !permissions[section.key][row.key as keyof (typeof DEFAULT_PERMISSIONS)[typeof section.key]]}<p class="ml-3 text-[10px] text-gray-500">该权限由默认用户权限提供，关闭用户组权限后仍对普通用户生效。</p>{/if}{/if}{/each}</div></section>{/each}</div>
				{/if}
			</div>

			<footer class="flex justify-end px-6 pb-5 pt-3">
				{#if defaultPermissionsOpen}
					<button type="button" class="rounded-full bg-gray-900 px-5 py-2 text-sm font-medium text-white transition hover:bg-gray-700 dark:bg-white dark:text-black dark:hover:bg-gray-200" onclick={() => defaultPermissionsOpen = false}>保存</button>
				{:else}
					<button type="submit" form="group-form" class="rounded-full bg-gray-900 px-5 py-2 text-sm font-medium text-white transition hover:bg-gray-700 dark:bg-white dark:text-black dark:hover:bg-gray-200">保存</button>
				{/if}
			</footer>
		</section>
	</div>
{/if}
