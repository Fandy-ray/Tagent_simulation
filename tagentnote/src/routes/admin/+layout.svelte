<script lang="ts">
	import { SvelteURLSearchParams } from 'svelte/reactivity';
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import MockSidebar from '$lib/components/chat/MockSidebar.svelte';
	import type { FolderFormValue } from '$lib/components/chat/FolderModal.svelte';
	import { loadQaChats, saveQaChats, type QaChat } from '$lib/data/qaConversations';
	import {
		collectFolderTreeIds,
		createQaFolder,
		loadQaFolders,
		saveQaFolders,
		wouldCreateCycle,
		type QaFolder
	} from '$lib/data/qaFolders';
	import { loadUserSettings } from '$lib/data/userSettings';
	import { adminToken, clearAdminToken, restoreAdminToken } from '$lib/apis/admin';
	import { authMode, currentAccount, logout } from '$lib/apis/auth';
	import AdminTokenGate from '$lib/components/admin/AdminTokenGate.svelte';

	let sidebarOpen = $state(true);
	let sidebarChats = $state<
		{ id: string; title: string; updatedAt: number; folderId?: string | null }[]
	>([]);
	let searchChats = $state<QaChat[]>([]);
	let folders = $state<QaFolder[]>([]);
	let activeChatId = $state<string | null>(null);
	let selectedFolderId = $state<string | null>(null);
	let modelId = $state($page.url.searchParams.get('model') ?? '');
	const userSettings = $state(loadUserSettings());

	onMount(() => {
		restoreAdminToken();
		const stored = loadQaChats();
		searchChats = stored.chats;
		sidebarChats = stored.chats
			.filter((chat) => !chat.archived && (chat.mode ?? 'qa') === 'qa')
			.map(({ id, title, updatedAt, folderId }) => ({ id, title, updatedAt, folderId }));
		folders = loadQaFolders();
		activeChatId = stored.activeId;
	});

	const refreshSidebarChats = () => {
		const stored = loadQaChats();
		searchChats = stored.chats;
		sidebarChats = stored.chats
			.filter((chat) => !chat.archived && (chat.mode ?? 'qa') === 'qa')
			.map(({ id, title, updatedAt, folderId }) => ({ id, title, updatedAt, folderId }));
	};

	const goQa = (chatId?: string) => {
		const params = new SvelteURLSearchParams();
		if (modelId) params.set('model', modelId);
		if (chatId) params.set('chat', chatId);
		const search = params.toString();
		void goto(resolve(search ? `/qa?${search}` : '/qa'));
	};

	const persistFolders = (next: QaFolder[]) => {
		folders = next;
		saveQaFolders(next);
	};

	const createFolder = (value: FolderFormValue, parentId: string | null = null) => {
		const folder = createQaFolder(value.name, parentId, {
			systemPrompt: value.systemPrompt,
			backgroundImageUrl: value.backgroundImageUrl,
			knowledgeItems: value.knowledgeItems
		});
		persistFolders([folder, ...folders]);
		selectedFolderId = folder.id;
	};

	const updateFolder = (folderId: string, value: FolderFormValue) =>
		persistFolders(
			folders.map((folder) =>
				folder.id === folderId
					? {
							...folder,
							name: value.name,
							systemPrompt: value.systemPrompt,
							backgroundImageUrl: value.backgroundImageUrl,
							knowledgeItems: value.knowledgeItems,
							updatedAt: Date.now()
						}
					: folder
			)
		);

	const deleteFolder = (folderId: string, deleteContents: boolean) => {
		const ids = collectFolderTreeIds(folders, folderId);
		persistFolders(folders.filter((folder) => !ids.has(folder.id)));
		const stored = loadQaChats();
		const chats = deleteContents
			? stored.chats.filter((chat) => !chat.folderId || !ids.has(chat.folderId))
			: stored.chats.map((chat) =>
					chat.folderId && ids.has(chat.folderId) ? { ...chat, folderId: null } : chat
				);
		saveQaChats(chats, stored.activeId);
		refreshSidebarChats();
		if (selectedFolderId && ids.has(selectedFolderId)) selectedFolderId = null;
	};

	const moveChat = (chatId: string, folderId: string | null) => {
		const stored = loadQaChats();
		saveQaChats(
			stored.chats.map((chat) =>
				chat.id === chatId ? { ...chat, folderId, updatedAt: Date.now() } : chat
			),
			stored.activeId
		);
		refreshSidebarChats();
	};

	const moveFolder = (folderId: string, parentId: string | null) => {
		if (!wouldCreateCycle(folders, folderId, parentId))
			persistFolders(
				folders.map((folder) =>
					folder.id === folderId ? { ...folder, parentId, updatedAt: Date.now() } : folder
				)
			);
	};

	const exportFolder = (folderId: string) => {
		const ids = collectFolderTreeIds(folders, folderId);
		const folder = folders.find((item) => item.id === folderId);
		const chats = loadQaChats().chats.filter((chat) => chat.folderId && ids.has(chat.folderId));
		const blob = new Blob(
			[
				JSON.stringify(
					{ folder, folders: folders.filter((item) => ids.has(item.id)), chats },
					null,
					2
				)
			],
			{ type: 'application/json' }
		);
		const url = URL.createObjectURL(blob);
		const anchor = document.createElement('a');
		anchor.href = url;
		anchor.download = `folder-${folder?.name || 'export'}-${Date.now()}.json`;
		anchor.click();
		URL.revokeObjectURL(url);
	};

	const tabs = [
		{ label: '账号', href: '/admin/accounts', match: '/admin/accounts' },
		{ label: '课程', href: '/admin/courses', match: '/admin/courses' },
		{ label: '用户', href: '/admin/users/overview', match: '/admin/users' },
		{ label: '分析', href: '/admin/analytics/dashboard', match: '/admin/analytics' },
		{ label: '评估', href: '/admin/evaluations/leaderboard', match: '/admin/evaluations' },
		{ label: '函数', href: '/admin/functions', match: '/admin/functions' },
		{ label: '设置', href: '/admin/settings/general', match: '/admin/settings' }
	];

	const isActive = (match: string) => $page.url.pathname.startsWith(match);

	let { children } = $props();
</script>

<svelte:head>
	<title>管理员面板 | TAgent</title>
</svelte:head>

<div
	class="space-theme workspace-palette admin-workspace flex h-screen max-h-[100dvh] w-full min-w-0 flex-1 overflow-hidden"
>
	{#if sidebarOpen}
		<MockSidebar
			spaceBrand
			{activeChatId}
			{selectedFolderId}
			chats={sidebarChats}
			{searchChats}
			{folders}
			userName={userSettings.displayName}
			avatarText={userSettings.avatarText}
			statusEmoji={userSettings.statusEmoji}
			statusMessage={userSettings.statusMessage}
			activeNav="chats"
			onHome={() => goto(resolve('/agent-select'))}
			onNewChat={() => goQa()}
			onSelectChat={(chatId) => {
				activeChatId = chatId;
				goQa(chatId);
			}}
			onSelectFolder={(folderId) => (selectedFolderId = folderId)}
			onOpenNotes={() => goto(resolve('/notebook?from=qa'))}
			onOpenWorkspace={() => goto(resolve('/workspace/models'))}
			onSettings={() => goto(resolve('/qa?sidebar-action=settings'))}
			onArchivedChats={() => goto(resolve('/qa?sidebar-action=archived'))}
			onPlayground={() => goto(resolve('/playground'))}
			onAdmin={() => goto(resolve('/admin/users/overview'))}
			onShortcuts={() => goto(resolve('/qa?sidebar-action=shortcuts'))}
			onSignOut={async () => {
				if ($authMode === 'enabled') await logout();
				await goto(resolve($authMode === 'enabled' ? '/welcome' : '/space-exploration'));
			}}
			onCreateFolder={createFolder}
			onUpdateFolder={updateFolder}
			onDeleteFolder={deleteFolder}
			onToggleFolderExpanded={(folderId) =>
				persistFolders(
					folders.map((folder) =>
						folder.id === folderId ? { ...folder, expanded: !(folder.expanded ?? true) } : folder
					)
				)}
			onMoveChatToFolder={moveChat}
			onMoveFolder={moveFolder}
			onExportFolder={exportFolder}
			onClose={() => (sidebarOpen = false)}
		/>
		<button
			type="button"
			class="fixed inset-0 z-30 bg-black/50 md:hidden"
			aria-label="收起侧栏"
			onclick={() => (sidebarOpen = false)}
		></button>
	{/if}

	<section class="flex min-w-0 flex-1 flex-col overflow-hidden">
		<nav class="drag-region w-full shrink-0 px-2.5 pt-1.5 backdrop-blur-xl select-none">
			<div class="flex items-center gap-1">
				{#if !sidebarOpen}
					<button
						type="button"
						class="dark:hover:bg-gray-850 mr-1 flex rounded-lg p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:text-white"
						onclick={() => (sidebarOpen = true)}
						aria-label="打开侧边栏"
						title="打开侧边栏"
					>
						<svg
							class="size-5"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="1.5"
							aria-hidden="true"
							><rect x="3" y="4" width="18" height="16" rx="2"></rect><path d="M9 4v16"></path></svg
						>
					</button>
				{/if}
				<div class="flex w-full">
					<div
						class="flex w-fit scrollbar-none gap-1 overflow-x-auto rounded-full bg-transparent pt-1 text-center text-sm font-medium"
					>
						{#each tabs as tab (tab.href)}
							<a
								draggable="false"
								class="admin-tab min-w-fit rounded-lg p-1.5 transition select-none"
								aria-current={isActive(tab.match) ? 'page' : undefined}
								href={resolve(tab.href)}>{tab.label}</a
							>
						{/each}
					</div>
				</div>
				{#if $authMode !== 'enabled' && $adminToken}
					<button
						type="button"
						class="dark:hover:bg-gray-850 shrink-0 rounded-lg px-2 py-1 text-xs text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:text-white"
						onclick={clearAdminToken}
						title="清掉管理口令，这台电脑记住的也一起清掉">锁定</button
					>
				{/if}
			</div>
		</nav>

		<div class="min-h-0 flex-1 overflow-y-auto pb-1">
			{#if ($authMode === 'enabled' && $currentAccount?.role === 'admin') || ($authMode === 'disabled' && $adminToken)}
				{@render children?.()}
			{:else}
				<AdminTokenGate />
			{/if}
		</div>
	</section>
</div>

<style>
	.admin-workspace {
		--admin-chart-green: #65d5ae;
		--admin-chart-violet: #b9a4e6;
		--admin-field-background: #1b191e;
		--admin-field-focus: #aea7b2;
		background: var(--qa-surface);
		color: var(--qa-text);
	}

	:global(html.light) .admin-workspace {
		--admin-chart-green: #26725a;
		--admin-chart-violet: #69509c;
		--admin-field-background: #fffefa;
		--admin-field-focus: #77736c;
	}

	.admin-workspace
		:global(
			:is(.border-gray-100, .border-gray-200, .dark\:border-gray-800, .dark\:border-gray-700)
		) {
		border-color: var(--qa-line);
	}

	.admin-workspace
		:global(:is(div, section, header, footer, input, select, textarea).bg-white.dark\:bg-gray-900),
	.admin-workspace :global(:is(div, section, header).bg-white.dark\:bg-gray-850),
	.admin-workspace :global(.bg-white\/95.dark\:bg-gray-900\/95) {
		background: var(--qa-panel) !important;
	}

	.admin-workspace :global(.space-branded),
	.admin-workspace .drag-region {
		background: var(--qa-panel) !important;
		border-color: var(--qa-line) !important;
	}

	:global(html.light) .admin-workspace :global(.bg-gray-900),
	:global(html.light) .admin-workspace :global(.bg-gray-950) {
		background-color: var(--qa-surface) !important;
	}

	:global(html.light) .admin-workspace :global(.bg-gray-850) {
		background-color: var(--qa-panel) !important;
	}

	:global(html.light) .admin-workspace :global(.bg-gray-800),
	:global(html.light) .admin-workspace :global(.hover\:bg-gray-800:hover) {
		background-color: var(--qa-raised) !important;
	}

	:global(html.light)
		.admin-workspace
		:global(:is(.text-white, .text-gray-50, .text-gray-100, .text-gray-200, .text-gray-900)) {
		color: var(--qa-text) !important;
	}

	:global(html.light)
		.admin-workspace
		:global(:is(.text-gray-300, .text-gray-400, .text-gray-500, .text-gray-600, .text-gray-700)) {
		color: var(--qa-muted) !important;
	}

	.admin-workspace :global(.bg-gray-900.text-white.dark\:bg-white) {
		background: var(--qa-active) !important;
		color: var(--qa-on-active) !important;
	}

	.admin-workspace
		:global(:is(a, button).bg-gray-900.text-white.dark\:bg-white:hover:not(:disabled)) {
		filter: brightness(1.12);
	}

	:global(html.light) .admin-workspace :global(:is(.bg-red-600, .bg-sky-700).text-white) {
		color: #fff !important;
	}

	:global(html.light) .admin-workspace :global(.bg-amber-500.text-white:not(.sidebar-avatar)) {
		background: var(--qa-tint);
		color: var(--qa-active) !important;
	}

	.admin-workspace :global(:is(a, button, input, select, textarea):focus-visible) {
		outline: 2px solid var(--qa-active);
		outline-offset: 2px;
	}

	.admin-workspace :global(:is(.admin-secondary, .admin-search)) {
		background: var(--qa-panel);
		border-color: var(--qa-line);
		color: var(--qa-text);
	}

	.admin-workspace :global(.admin-secondary:hover),
	.admin-workspace :global(.admin-filter:hover) {
		background: var(--qa-raised);
		color: var(--qa-text);
	}

	.admin-workspace :global(.admin-filter) {
		color: var(--qa-muted);
	}

	.admin-workspace :global(.admin-filter[aria-pressed='true']) {
		background: var(--qa-tint);
		color: var(--qa-active);
		font-weight: 600;
	}

	.admin-workspace :global(.admin-primary) {
		background: var(--qa-active);
		color: var(--qa-on-active);
	}

	.admin-workspace :global(.admin-primary:hover:not(:disabled)) {
		filter: brightness(1.12);
	}

	.admin-workspace
		:global(
			:is(
				input:not([type]),
				input[type='text'],
				input[type='search'],
				input[type='number'],
				input[type='password'],
				input[type='url'],
				input[type='email'],
				select,
				textarea
			)
		) {
		background: var(--admin-field-background) !important;
		border-color: var(--qa-line);
		color: var(--qa-text) !important;
		caret-color: var(--qa-text);
	}

	.admin-workspace :global(.admin-search input) {
		background: transparent !important;
	}

	.admin-workspace :global(.admin-settings-heading) {
		background: var(--qa-surface);
	}

	:global(html.light) .admin-workspace .drag-region,
	:global(html.light) .admin-workspace :global(.admin-search),
	:global(html.light) .admin-workspace :global(input.admin-connection-address) {
		background: var(--qa-surface) !important;
	}

	.admin-workspace :global(:is(input, textarea)::placeholder) {
		color: var(--qa-muted);
		opacity: 1;
	}

	.admin-workspace
		:global(:is(input:not([type='checkbox'], [type='radio']), select, textarea):focus-visible) {
		border-color: var(--admin-field-focus);
		outline: 2px solid var(--admin-field-focus);
		outline-offset: 1px;
		box-shadow: none;
	}

	.admin-workspace :global(.admin-search:focus-within) {
		border-color: var(--admin-field-focus);
		outline: 2px solid var(--admin-field-focus);
		outline-offset: 1px;
	}

	.admin-workspace :global(.admin-search input:focus-visible) {
		outline: none;
	}

	.admin-tab {
		color: var(--qa-muted);
	}

	.admin-tab:hover,
	.admin-tab:focus-visible {
		background: var(--qa-raised);
		color: var(--qa-text);
	}

	.admin-tab[aria-current='page'] {
		background: var(--qa-tint);
		color: var(--qa-active);
	}

	.scrollbar-none {
		scrollbar-width: none;
	}
	.scrollbar-none::-webkit-scrollbar {
		display: none;
	}
</style>
