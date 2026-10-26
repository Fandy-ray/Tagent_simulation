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
	import { adminToken } from '$lib/apis/admin';
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
	class="flex h-screen max-h-[100dvh] w-full min-w-0 flex-1 overflow-hidden bg-white text-gray-900 selection:bg-blue-500/20 dark:bg-gray-900 dark:text-white"
>
	{#if sidebarOpen}
		<MockSidebar
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
			onSignOut={() => goto(resolve('/welcome'))}
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
								class="min-w-fit p-1.5 transition select-none {isActive(tab.match)
									? ''
									: 'text-gray-300 hover:text-gray-700 dark:text-gray-600 dark:hover:text-white'}"
								href={resolve(tab.href)}>{tab.label}</a
							>
						{/each}
					</div>
				</div>
				{#if $adminToken}
					<button
						type="button"
						class="dark:hover:bg-gray-850 shrink-0 rounded-lg px-2 py-1 text-xs text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 dark:hover:text-white"
						onclick={() => adminToken.set('')}
						title="清掉这个标签页里的管理口令">锁定</button
					>
				{/if}
			</div>
		</nav>

		<div class="min-h-0 flex-1 overflow-y-auto pb-1">
			{#if $adminToken}
				{@render children?.()}
			{:else}
				<AdminTokenGate />
			{/if}
		</div>
	</section>
</div>

<style>
	.scrollbar-none {
		scrollbar-width: none;
	}
	.scrollbar-none::-webkit-scrollbar {
		display: none;
	}
</style>
