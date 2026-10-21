<script lang="ts">
	import { afterNavigate, goto } from '$app/navigation';
	import { page } from '$app/stores';

	import MockSidebar from '$lib/components/chat/MockSidebar.svelte';
	import type { FolderFormValue } from '$lib/components/chat/FolderModal.svelte';
	import { loadQaChats, saveQaChats, type QaChat } from '$lib/data/qaConversations';
	import { collectFolderTreeIds, createQaFolder, loadQaFolders, saveQaFolders, wouldCreateCycle, type QaFolder } from '$lib/data/qaFolders';
	import { loadUserSettings } from '$lib/data/userSettings';

	let { children } = $props();

	let sidebarOpen = $state(true);
	let modelId = $state($page.url.searchParams.get('model') ?? '');
	let chats = $state<{ id: string; title: string; updatedAt: number; folderId?: string | null }[]>([]);
	let searchChats = $state<QaChat[]>([]);
	let folders = $state<QaFolder[]>([]);
	let selectedFolderId = $state<string | null>(null);
	let activeChatId = $state<string | null>($page.url.searchParams.get('chat'));
	const userSettings = $state(loadUserSettings());

	const refreshSidebar = () => {
		const stored = loadQaChats();
		searchChats = stored.chats;
		chats = stored.chats.filter((chat) => !chat.archived).map(({ id, title, updatedAt, folderId }) => ({ id, title, updatedAt, folderId }));
		folders = loadQaFolders();
		activeChatId = $page.url.searchParams.get('chat') ?? stored.activeId;
	};

	afterNavigate(refreshSidebar);

	const tabs = [
		{ href: '/workspace/models', label: '模型' },
		{ href: '/workspace/knowledge', label: '知识库' },
		{ href: '/workspace/prompts', label: '提示词' },
		{ href: '/workspace/skills', label: '技能' },
		{ href: '/workspace/tools', label: '工具' }
	] as const;

	const withParams = (path: string, extra?: Record<string, string>) => {
		const params = new URLSearchParams();
		if (modelId) params.set('model', modelId);
		if (activeChatId) params.set('chat', activeChatId);
		if (extra) {
			for (const [key, value] of Object.entries(extra)) {
				if (value) params.set(key, value);
			}
		}
		const search = params.toString();
		return search ? `${path}?${search}` : path;
	};

	const isActiveTab = (href: string) => $page.url.pathname.startsWith(href);

	const goQa = (opts?: { newChat?: boolean; chatId?: string }) => {
		const params = new URLSearchParams();
		if (modelId) params.set('model', modelId);
		if (!opts?.newChat) {
			const chatId = opts?.chatId ?? activeChatId;
			if (chatId) params.set('chat', chatId);
		}
		const search = params.toString();
		void goto(search ? `/qa?${search}` : '/qa');
	};

	const persistFolders = (next: QaFolder[]) => {
		folders = next;
		saveQaFolders(next);
	};

	const createFolder = (value: FolderFormValue, parentId: string | null = null) => {
		const folder = createQaFolder(value.name, parentId, { systemPrompt: value.systemPrompt, backgroundImageUrl: value.backgroundImageUrl, knowledgeItems: value.knowledgeItems });
		persistFolders([folder, ...folders]);
		selectedFolderId = folder.id;
	};

	const updateFolder = (folderId: string, value: FolderFormValue) => persistFolders(folders.map((folder) => folder.id === folderId ? { ...folder, name: value.name, systemPrompt: value.systemPrompt, backgroundImageUrl: value.backgroundImageUrl, knowledgeItems: value.knowledgeItems, updatedAt: Date.now() } : folder));

	const deleteFolder = (folderId: string, deleteContents: boolean) => {
		const ids = collectFolderTreeIds(folders, folderId);
		persistFolders(folders.filter((folder) => !ids.has(folder.id)));
		const stored = loadQaChats();
		const updated = deleteContents ? stored.chats.filter((chat) => !chat.folderId || !ids.has(chat.folderId)) : stored.chats.map((chat) => chat.folderId && ids.has(chat.folderId) ? { ...chat, folderId: null } : chat);
		saveQaChats(updated, stored.activeId);
		refreshSidebar();
		if (selectedFolderId && ids.has(selectedFolderId)) selectedFolderId = null;
	};

	const moveChat = (chatId: string, folderId: string | null) => {
		const stored = loadQaChats();
		saveQaChats(stored.chats.map((chat) => chat.id === chatId ? { ...chat, folderId, updatedAt: Date.now() } : chat), stored.activeId);
		refreshSidebar();
	};

	const moveFolder = (folderId: string, parentId: string | null) => {
		if (!wouldCreateCycle(folders, folderId, parentId)) persistFolders(folders.map((folder) => folder.id === folderId ? { ...folder, parentId, updatedAt: Date.now() } : folder));
	};

	const exportFolder = (folderId: string) => {
		const ids = collectFolderTreeIds(folders, folderId);
		const folder = folders.find((item) => item.id === folderId);
		const chats = loadQaChats().chats.filter((chat) => chat.folderId && ids.has(chat.folderId));
		const url = URL.createObjectURL(new Blob([JSON.stringify({ folder, folders: folders.filter((item) => ids.has(item.id)), chats }, null, 2)], { type: 'application/json' }));
		const anchor = document.createElement('a');
		anchor.href = url;
		anchor.download = `folder-${folder?.name || 'export'}-${Date.now()}.json`;
		anchor.click();
		URL.revokeObjectURL(url);
	};
</script>

<svelte:head>
	<title>工作空间 | TAgent</title>
</svelte:head>

<main class="flex h-screen overflow-hidden bg-gray-900 text-white">
	{#if sidebarOpen}
		<MockSidebar
			{activeChatId}
			{selectedFolderId}
			{chats}
			{searchChats}
			{folders}
			{modelId}
			userName={userSettings.displayName}
			avatarText={userSettings.avatarText}
			statusEmoji={userSettings.statusEmoji}
			statusMessage={userSettings.statusMessage}
			activeNav="workspace"
			onHome={() => goto('/agent-select')}
			onNewChat={() => goQa({ newChat: true })}
			onSelectChat={(chatId) => { activeChatId = chatId; selectedFolderId = searchChats.find((chat) => chat.id === chatId)?.folderId ?? null; goQa({ chatId }); }}
			onSelectFolder={(folderId) => selectedFolderId = folderId}
			onOpenNotes={() => goto(withParams('/notebook', { from: 'qa' }))}
			onOpenWorkspace={() => goto(withParams('/workspace/models'))}
			onSettings={() => goto('/qa?sidebar-action=settings')}
			onArchivedChats={() => goto('/qa?sidebar-action=archived')}
			onPlayground={() => goto('/playground')}
			onAdmin={() => goto('/admin/users/overview')}
			onShortcuts={() => goto('/qa?sidebar-action=shortcuts')}
			onSignOut={() => goto('/welcome')}
			onCreateFolder={createFolder}
			onUpdateFolder={updateFolder}
			onDeleteFolder={deleteFolder}
			onToggleFolderExpanded={(folderId) => persistFolders(folders.map((folder) => folder.id === folderId ? { ...folder, expanded: !(folder.expanded ?? true) } : folder))}
			onMoveChatToFolder={moveChat}
			onMoveFolder={moveFolder}
			onExportFolder={exportFolder}
			onClose={() => {
				sidebarOpen = false;
			}}
		/>
	{/if}

	<section class="relative flex min-w-0 flex-1 flex-col bg-gray-900">
		<nav class="shrink-0 px-2.5 pt-1.5 select-none">
			<div class="flex items-center gap-1">
				{#if !sidebarOpen}
					<button
						type="button"
						class="mr-1 flex rounded-lg p-1.5 text-gray-400 transition hover:bg-gray-850 hover:text-white"
						onclick={() => {
							sidebarOpen = true;
						}}
						aria-label="打开侧边栏"
					>
						<svg
							class="size-5"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="1.5"
							aria-hidden="true"
						>
							<rect x="3" y="4" width="18" height="16" rx="2"></rect>
							<path d="M9 4v16"></path>
						</svg>
					</button>
				{/if}

				<div
					class="flex w-fit touch-auto gap-1 overflow-x-auto rounded-full bg-transparent py-1 text-center text-sm font-medium scrollbar-none"
				>
					{#each tabs as tab (tab.href)}
						<a
							draggable="false"
							aria-current={isActiveTab(tab.href) ? 'page' : undefined}
							class={`min-w-fit p-1.5 transition select-none ${
								isActiveTab(tab.href)
									? 'text-white'
									: 'text-gray-600 hover:text-white'
							}`}
							href={withParams(tab.href)}
						>
							{tab.label}
						</a>
					{/each}
				</div>
			</div>
		</nav>

		<div class="min-h-0 flex-1 overflow-y-auto px-3 pb-1 md:px-[18px]" id="workspace-container">
			{@render children()}
		</div>
	</section>
</main>
