<script lang="ts">
	import { SvelteDate } from 'svelte/reactivity';
	import FolderModal, { type FolderFormValue } from './FolderModal.svelte';
	import RecursiveFolder from './RecursiveFolder.svelte';
	import UserMenu from '$lib/components/layout/UserMenu.svelte';
	import SearchModal from '$lib/components/layout/SearchModal.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import type { QaChat } from '$lib/data/qaConversations';
	import type { QaFolder } from '$lib/data/qaFolders';
	import { getI18nContext } from '$lib/i18n';

	const i18n = getI18nContext();

	export type ChatSummary = {
		id: string;
		title: string;
		updatedAt: number;
		folderId?: string | null;
	};

	type NavKey = 'chats' | 'notes' | 'workspace';

	type Props = {
		activeChatId?: string | null;
		selectedFolderId?: string | null;
		chats?: ChatSummary[];
		searchChats?: QaChat[];
		folders?: QaFolder[];
		userName?: string;
		avatarText?: string;
		activeNav?: NavKey;
		onHome?: () => void;
		onNewChat?: () => void;
		onSelectChat?: (chatId: string) => void;
		onSelectFolder?: (folderId: string | null) => void;
		onClose?: () => void;
		onOpenNotes?: () => void;
		onOpenWorkspace?: () => void;
		onSettings?: () => void;
		onArchivedChats?: () => void;
		onPlayground?: () => void;
		onAdmin?: () => void;
		onShortcuts?: () => void;
		onSignOut?: () => void;
		statusEmoji?: string;
		statusMessage?: string;
		onStatusSave?: (value: { emoji: string; message: string }) => void;
		onToast?: (message: string) => void;
		onCreateFolder?: (value: FolderFormValue, parentId?: string | null) => void;
		onUpdateFolder?: (folderId: string, value: FolderFormValue) => void;
		onDeleteFolder?: (folderId: string, deleteContents: boolean) => void;
		onToggleFolderExpanded?: (folderId: string) => void;
		onMoveChatToFolder?: (chatId: string, folderId: string | null) => void;
		onMoveFolder?: (folderId: string, parentId: string | null) => void;
		onExportFolder?: (folderId: string) => void;
		knowledgeOptions?: { id: string; name: string }[];
		onOpenWorkspaceKnowledge?: () => void;
	};

	let {
		activeChatId = null,
		selectedFolderId = null,
		chats = [],
		searchChats = [],
		folders = [],
		userName = 'Tagent',
		avatarText = 'T',
		activeNav = 'chats',
		onHome = () => {},
		onNewChat = () => {},
		onSelectChat = () => {},
		onSelectFolder = () => {},
		onClose = () => {},
		onOpenNotes = () => {},
		onOpenWorkspace = () => {},
		onSettings = () => {},
		onArchivedChats = () => {},
		onPlayground = () => {},
		onAdmin = () => {},
		onShortcuts = () => {},
		onSignOut = () => {},
		statusEmoji = '',
		statusMessage = '',
		onStatusSave = () => {},
		onToast = () => {},
		onCreateFolder = () => {},
		onUpdateFolder = () => {},
		onDeleteFolder = () => {},
		onToggleFolderExpanded = () => {},
		onMoveChatToFolder = () => {},
		onMoveFolder = () => {},
		onExportFolder = () => {},
		knowledgeOptions = [],
		onOpenWorkspaceKnowledge = () => {}
	}: Props = $props();

	let showSearch = $state(false);
	let showFolders = $state(
		typeof localStorage !== 'undefined'
			? localStorage.getItem('sidebar-folders-folder-state') !== 'false'
			: true
	);
	let folderModalOpen = $state(false);
	let folderModalMode = $state<'create' | 'rename' | 'sub'>('create');
	let folderModalTargetId = $state<string | null>(null);
	let folderModalParentId = $state<string | null>(null);
	let folderModalDraft = $state<FolderFormValue>({
		name: '',
		systemPrompt: '',
		backgroundImageUrl: null,
		knowledgeItems: []
	});
	let openFolderMenuId = $state<string | null>(null);
	let openChatMenuId = $state<string | null>(null);
	let dragOverFolderId = $state<string | null>(null);
	let deleteConfirmOpen = $state(false);
	let deleteTargetId = $state<string | null>(null);
	let deleteContents = $state(true);

	const sortedChats = $derived([...chats].sort((a, b) => b.updatedAt - a.updatedAt));
	const filteredChats = $derived(sortedChats);
	const isMac =
		typeof navigator !== 'undefined' ? /Mac|iPhone|iPad/i.test(navigator.userAgent) : false;
	const searchChatsForModal = $derived(searchChats.length > 0 ? searchChats : []);

	const rootFolders = $derived(
		folders
			.filter((f) => !f.parentId)
			.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }))
	);

	const chatsInFolder = (folderId: string) =>
		filteredChats.filter((chat) => chat.folderId === folderId);

	const unfiledChats = $derived(filteredChats.filter((chat) => !chat.folderId));

	const startOfToday = () => {
		const date = new SvelteDate();
		date.setHours(0, 0, 0, 0);
		return date.getTime();
	};

	const DAY = 24 * 60 * 60 * 1000;

	const groupOf = (chat: ChatSummary) => {
		const today = startOfToday();
		if (chat.updatedAt >= today) return '今天';
		if (chat.updatedAt >= today - DAY) return '昨天';
		if (chat.updatedAt >= today - 7 * DAY) return '过去 7 天';
		return '更早';
	};

	const timeLabel = (chat: ChatSummary) => {
		const minutes = Math.floor((Date.now() - chat.updatedAt) / 60000);
		if (minutes < 1) return '刚刚';
		if (minutes < 60) return `${minutes}分钟前`;
		if (minutes < 60 * 24) return `${Math.floor(minutes / 60)}小时前`;
		return `${Math.floor(minutes / (60 * 24))}天前`;
	};

	const GROUP_ORDER = ['今天', '昨天', '过去 7 天', '更早'];

	const groupedUnfiledChats = $derived(
		GROUP_ORDER.map((label) => ({
			label,
			items: unfiledChats.filter((chat) => groupOf(chat) === label)
		})).filter((group) => group.items.length > 0)
	);

	const navClass = (key: NavKey) =>
		`group flex w-full items-center gap-3 rounded-2xl px-2.5 py-2 outline-none transition hover:bg-gray-900 ${
			activeNav === key ? 'bg-gray-900 text-white' : 'text-gray-200'
		}`;

	const openCreateFolder = (parentId: string | null = null) => {
		folderModalMode = parentId ? 'sub' : 'create';
		folderModalParentId = parentId;
		folderModalTargetId = null;
		folderModalDraft = { name: '', systemPrompt: '', backgroundImageUrl: null, knowledgeItems: [] };
		folderModalOpen = true;
		openFolderMenuId = null;
	};

	const openRenameFolder = (folder: QaFolder) => {
		folderModalMode = 'rename';
		folderModalTargetId = folder.id;
		folderModalParentId = folder.parentId;
		folderModalDraft = {
			name: folder.name,
			systemPrompt: folder.systemPrompt ?? '',
			backgroundImageUrl: folder.backgroundImageUrl ?? null,
			knowledgeItems: folder.knowledgeItems ?? []
		};
		folderModalOpen = true;
		openFolderMenuId = null;
	};

	const submitFolderModal = (value: FolderFormValue) => {
		if (folderModalMode === 'rename' && folderModalTargetId) {
			onUpdateFolder(folderModalTargetId, value);
			return;
		}
		onCreateFolder(value, folderModalParentId);
		showFolders = true;
		localStorage.setItem('sidebar-folders-folder-state', 'true');
	};

	const askDeleteFolder = (folderId: string) => {
		deleteTargetId = folderId;
		deleteContents = true;
		deleteConfirmOpen = true;
		openFolderMenuId = null;
	};

	const confirmDeleteFolder = () => {
		if (!deleteTargetId) return;
		onDeleteFolder(deleteTargetId, deleteContents);
		deleteConfirmOpen = false;
		deleteTargetId = null;
	};

	const onChatDragStart = (event: DragEvent, chatId: string) => {
		event.dataTransfer?.setData('application/x-chat-id', chatId);
		event.dataTransfer?.setData('text/plain', JSON.stringify({ type: 'chat', id: chatId }));
		if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
	};

	const onFolderDragStart = (event: DragEvent, folderId: string) => {
		event.dataTransfer?.setData('text/plain', JSON.stringify({ type: 'folder', id: folderId }));
		event.dataTransfer?.setData('application/x-folder-id', folderId);
		if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
	};

	const onFolderDragOver = (event: DragEvent, folderId: string) => {
		event.preventDefault();
		dragOverFolderId = folderId;
	};

	const onFolderDragLeave = (folderId: string) => {
		if (dragOverFolderId === folderId) dragOverFolderId = null;
	};

	const onFolderDrop = (event: DragEvent, folderId: string) => {
		event.preventDefault();
		dragOverFolderId = null;
		const raw =
			event.dataTransfer?.getData('text/plain') ||
			event.dataTransfer?.getData('application/x-chat-id') ||
			'';
		try {
			const parsed = JSON.parse(raw) as { type?: string; id?: string };
			if (parsed.type === 'folder' && parsed.id) {
				onMoveFolder(parsed.id, folderId);
				return;
			}
			if (parsed.type === 'chat' && parsed.id) {
				onMoveChatToFolder(parsed.id, folderId);
				return;
			}
		} catch {
			// plain chat id fallback
		}
		const chatId = event.dataTransfer?.getData('application/x-chat-id') || raw;
		if (chatId && !chatId.startsWith('{')) onMoveChatToFolder(chatId, folderId);
	};
</script>

<aside
	class="fixed inset-y-0 left-0 z-40 flex h-screen w-[260px] shrink-0 flex-col overflow-hidden border-r border-white/[0.04] bg-gray-900 text-sm text-gray-200 shadow-2xl shadow-black/50 select-none md:static md:z-auto md:shadow-none"
>
	<header class="flex h-12 shrink-0 items-center gap-2 px-2">
		<button
			type="button"
			class="flex size-8 shrink-0 items-center justify-center rounded-xl transition hover:bg-gray-900"
			onclick={onHome}
			title="返回选择智能体"
			aria-label="返回选择智能体"
		>
			<div
				class="flex size-6 items-center justify-center rounded-full border border-black/20 bg-white text-xs font-black text-black dark:border-transparent"
			>
				T
			</div>
		</button>

		<button
			type="button"
			class="min-w-0 flex-1 truncate px-1 text-left text-xs font-medium text-white"
			onclick={onHome}
		>
			系统建模与仿真智能体
		</button>

		<button
			type="button"
			class="flex size-8 shrink-0 items-center justify-center rounded-xl text-gray-400 transition hover:bg-gray-900 hover:text-white"
			onclick={onClose}
			title="收起侧边栏"
			aria-label="收起侧边栏"
		>
			<svg
				class="size-[18px]"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="1.5"
				stroke-linecap="round"
				stroke-linejoin="round"
				aria-hidden="true"
			>
				<rect x="3" y="4" width="18" height="16" rx="2"></rect>
				<path d="M9 4v16"></path>
			</svg>
		</button>
	</header>

	<div class="min-h-0 flex-1 overflow-y-auto px-[7px] pt-1 pb-3">
		<nav class="pb-2">
			<button
				type="button"
				id="sidebar-new-chat-button"
				class="group flex w-full items-center gap-3 rounded-2xl px-2.5 py-2 text-gray-200 transition outline-none hover:bg-gray-900"
				onclick={onNewChat}
			>
				<svg
					class="size-[18px] shrink-0"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					stroke-linecap="round"
					stroke-linejoin="round"
					aria-hidden="true"
				>
					<path d="M12 20h9"></path>
					<path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"></path>
				</svg>
				<span class="flex-1 text-left text-sm">{$i18n.t('New Chat')}</span>
			</button>

			<button
				type="button"
				id="sidebar-search-button"
				class="group flex w-full items-center gap-3 rounded-2xl px-2.5 py-2 text-gray-200 transition outline-none hover:bg-gray-900"
				onclick={() => {
					showSearch = true;
				}}
				draggable="false"
				aria-label={$i18n.t('Search')}
			>
				<div class="self-center">
					<Search strokeWidth="2" className="size-[18px]" />
				</div>
				<div class="flex flex-1 translate-y-[0.5px] self-center">
					<div class="self-center text-sm">{$i18n.t('Search')}</div>
				</div>
				<span
					class="invisible rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-gray-500 group-hover:visible"
				>
					{isMac ? '⌘' : 'Ctrl'} K
				</span>
			</button>

			<button
				type="button"
				class={navClass('notes')}
				onclick={onOpenNotes}
				title={$i18n.t('Open Notes')}
			>
				<svg
					class="size-[18px] shrink-0"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
					stroke-linecap="round"
					stroke-linejoin="round"
					aria-hidden="true"
				>
					<path d="M8 2v4"></path>
					<path d="M12 2v4"></path>
					<path d="M16 2v4"></path>
					<path d="M4 6h16v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6z"></path>
					<path d="M8 12h8"></path>
					<path d="M8 16h5"></path>
				</svg>
				<span class="flex-1 text-left text-sm">{$i18n.t('Notes')}</span>
			</button>

			<button
				type="button"
				class={navClass('workspace')}
				onclick={onOpenWorkspace}
				title={$i18n.t('Open Workspace')}
			>
				<svg
					class="size-[18px] shrink-0"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
					stroke-linecap="round"
					stroke-linejoin="round"
					aria-hidden="true"
				>
					<path
						d="M13.5 16.875h3.375m0 0h3.375m-3.375 0V13.5m0 3.375v3.375M6 10.5h2.25a2.25 2.25 0 0 0 2.25-2.25V6a2.25 2.25 0 0 0-2.25-2.25H6A2.25 2.25 0 0 0 3.75 6v2.25A2.25 2.25 0 0 0 6 10.5Zm0 9.75h2.25A2.25 2.25 0 0 0 10.5 18v-2.25a2.25 2.25 0 0 0-2.25-2.25H6a2.25 2.25 0 0 0-2.25 2.25V18A2.25 2.25 0 0 0 6 20.25Zm9.75-9.75H18a2.25 2.25 0 0 0 2.25-2.25V6A2.25 2.25 0 0 0 18 3.75h-2.25A2.25 2.25 0 0 0 13.5 6v2.25a2.25 2.25 0 0 0 2.25 2.25Z"
					></path>
				</svg>
				<span class="flex-1 text-left text-sm">{$i18n.t('Workspace')}</span>
			</button>
		</nav>

		<section class="mt-0.5 px-0.5 pb-1">
			<div
				class="group relative flex w-full items-center justify-between rounded-xl text-gray-400 transition hover:bg-gray-900"
			>
				<button
					type="button"
					class="flex w-full items-center gap-1.5 py-1.5 pl-2.5 text-xs font-medium"
					onclick={() => {
						showFolders = !showFolders;
						localStorage.setItem('sidebar-folders-folder-state', String(showFolders));
					}}
				>
					<span class="translate-y-[0.5px]">{$i18n.t('Folders')}</span>
				</button>
				<button
					type="button"
					class="absolute right-2 z-10 flex items-center rounded-md p-0.5 text-gray-400 opacity-0 transition group-hover:opacity-100 hover:text-white"
					title={$i18n.t('Create Folder')}
					aria-label={$i18n.t('Create Folder')}
					onclick={(e) => {
						e.stopPropagation();
						openCreateFolder(null);
					}}
				>
					<svg
						class="size-3.5"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
					>
						<path stroke-linecap="round" d="M12 5v14M5 12h14"></path>
					</svg>
				</button>
			</div>

			{#if showFolders}
				{#if rootFolders.length === 0}
					<p class="px-2.5 py-1 text-[11px] leading-4 text-gray-600">
						点击 + 创建分组。可拖拽对话/分组进行整理，编辑里可设系统提示词与背景。
					</p>
				{/if}

				{#each rootFolders as folder (folder.id)}
					<RecursiveFolder
						{folder}
						{folders}
						chats={filteredChats}
						{activeChatId}
						{selectedFolderId}
						{dragOverFolderId}
						openMenuId={openFolderMenuId}
						{onSelectFolder}
						onToggleExpanded={onToggleFolderExpanded}
						onOpenMenu={(id) => {
							openFolderMenuId = id;
							openChatMenuId = null;
						}}
						onEdit={openRenameFolder}
						onCreateSub={(parentId) => openCreateFolder(parentId)}
						onExport={onExportFolder}
						onDelete={askDeleteFolder}
						{onSelectChat}
						onMoveChatOut={(chatId) => onMoveChatToFolder(chatId, null)}
						{onChatDragStart}
						{onFolderDragStart}
						{onFolderDragOver}
						{onFolderDragLeave}
						{onFolderDrop}
						{timeLabel}
					/>
				{/each}
			{/if}
		</section>

		<section>
			<div class="flex items-center justify-between px-2.5 pt-1 pb-2">
				<div class="text-xs font-medium text-gray-500">{$i18n.t('Chats')}</div>
				{#if selectedFolderId}
					<button
						type="button"
						class="text-[10px] text-sky-400/90 hover:text-sky-300"
						onclick={() => onSelectFolder(null)}
					>
						{$i18n.t('Clear Filters')}
					</button>
				{/if}
			</div>

			{#if selectedFolderId}
				{@const selectedChats = chatsInFolder(selectedFolderId)}
				{#each selectedChats as chat (chat.id)}
					<button
						type="button"
						class={`group flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left transition ${
							activeChatId === chat.id
								? 'bg-gray-900 text-white'
								: 'text-gray-300 hover:bg-gray-900'
						}`}
						draggable="true"
						ondragstart={(e) => onChatDragStart(e, chat.id)}
						onclick={() => onSelectChat(chat.id)}
					>
						<span class="min-w-0 flex-1 truncate text-sm">{chat.title}</span>
						<span class="shrink-0 text-[10px] text-gray-600">{timeLabel(chat)}</span>
					</button>
				{/each}
				{#if selectedChats.length === 0}
					<p class="px-2.5 py-4 text-xs text-gray-500">
						{$i18n.t('No chats in this folder. New chats will be placed here.')}
					</p>
				{/if}
			{:else}
				{#each groupedUnfiledChats as group (group.label)}
					<div class="px-2.5 pt-1 pb-1.5 text-xs font-medium text-gray-500">
						{group.label}
					</div>
					<div class="space-y-0.5">
						{#each group.items as chat (chat.id)}
							<div class="group relative">
								<button
									type="button"
									class={`flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left transition ${
										activeChatId === chat.id
											? 'bg-gray-900 text-white'
											: 'text-gray-300 hover:bg-gray-900'
									}`}
									draggable="true"
									ondragstart={(e) => onChatDragStart(e, chat.id)}
									onclick={() => onSelectChat(chat.id)}
								>
									<span class="min-w-0 flex-1 truncate text-sm">{chat.title}</span>
									<span class="shrink-0 text-[10px] text-gray-600">{timeLabel(chat)}</span>
								</button>

								{#if folders.length > 0}
									<button
										type="button"
										class="absolute top-1.5 right-1 rounded-md p-0.5 text-gray-500 opacity-0 group-hover:opacity-100 hover:bg-gray-800 hover:text-white"
										title={$i18n.t('Move to Folder')}
										aria-label={$i18n.t('Move to Folder')}
										onclick={(e) => {
											e.stopPropagation();
											openChatMenuId = openChatMenuId === chat.id ? null : chat.id;
											openFolderMenuId = null;
										}}
									>
										<svg
											class="size-3.5"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="1.8"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"
											></path>
										</svg>
									</button>
									{#if openChatMenuId === chat.id}
										<div
											class="absolute top-8 right-1 z-40 max-h-48 w-40 overflow-y-auto rounded-xl border border-white/10 bg-gray-900 py-1 shadow-xl"
										>
											{#each folders as folder (folder.id)}
												<button
													type="button"
													class="flex w-full truncate px-3 py-1.5 text-left text-xs hover:bg-white/[0.06]"
													onclick={() => {
														onMoveChatToFolder(chat.id, folder.id);
														openChatMenuId = null;
													}}
												>
													{folder.name}
												</button>
											{/each}
										</div>
									{/if}
								{/if}
							</div>
						{/each}
					</div>
				{/each}

				{#if unfiledChats.length === 0}
					<p class="px-2.5 py-6 text-xs leading-5 text-gray-500">
						{#if chats.length === 0}
							{$i18n.t('No chats yet. Questions will appear here and persist after refresh.')}
						{:else}
							{$i18n.t('All chats are in folders. Click on a folder above to view.')}
						{/if}
					</p>
				{/if}
			{/if}
		</section>
	</div>

	<footer class="relative shrink-0 px-1.5 pt-4 pb-2">
		<div class="relative">
			<UserMenu
				variant="sidebar"
				className="w-[240px]"
				align="start"
				placement="top"
				userRole="admin"
				{userName}
				{avatarText}
				{statusEmoji}
				{statusMessage}
				triggerClassName="flex w-full items-center rounded-2xl px-1.5 py-2 transition hover:bg-gray-900/50"
				{onSettings}
				{onArchivedChats}
				{onPlayground}
				{onAdmin}
				{onShortcuts}
				{onSignOut}
				{onStatusSave}
				{onToast}
			>
				<div class="flex w-full items-center text-left">
					<div class="relative mr-3 shrink-0 self-center">
						<div
							class="flex size-7 items-center justify-center rounded-full bg-amber-500 text-[10px] font-semibold text-white"
						>
							{avatarText}
						</div>
						<span
							class="absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full border-2 border-gray-200 bg-green-500 dark:border-gray-950"
						></span>
					</div>
					<div class="self-center font-medium text-gray-100">{userName}</div>
				</div>
			</UserMenu>
		</div>
	</footer>
</aside>

<SearchModal
	bind:show={showSearch}
	chats={searchChatsForModal}
	{folders}
	onClose={() => {
		showSearch = false;
	}}
	onSelectChat={(chatId) => {
		onSelectChat(chatId);
	}}
	onNewChat={() => {
		onNewChat();
	}}
	onOpenNotes={() => {
		onOpenNotes();
	}}
/>

<FolderModal
	open={folderModalOpen}
	title={folderModalMode === 'rename'
		? $i18n.t('Edit Folder')
		: folderModalMode === 'sub'
			? $i18n.t('Create Subfolder')
			: $i18n.t('Create Folder')}
	initialName={folderModalDraft.name}
	initialSystemPrompt={folderModalDraft.systemPrompt}
	initialBackgroundImageUrl={folderModalDraft.backgroundImageUrl}
	initialKnowledgeItems={folderModalDraft.knowledgeItems}
	{knowledgeOptions}
	{onOpenWorkspaceKnowledge}
	onClose={() => {
		folderModalOpen = false;
	}}
	onSubmit={submitFolderModal}
/>

{#if deleteConfirmOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-[95] flex items-center justify-center bg-black/60 px-4"
		onclick={() => {
			deleteConfirmOpen = false;
		}}
	>
		<div
			class="bg-gray-850 w-full max-w-sm rounded-2xl border border-gray-800 p-4 text-white shadow-2xl"
			onclick={(e) => e.stopPropagation()}
			tabindex="-1"
			role="dialog"
			aria-modal="true"
			aria-label={$i18n.t('Delete Folder')}
		>
			<h3 class="text-base font-medium">{$i18n.t('Delete this folder?')}</h3>
			<p class="mt-2 text-sm text-gray-400">
				{$i18n.t('Are you sure you want to delete "{{NAME}}"?', {
					NAME: folders.find((f) => f.id === deleteTargetId)?.name ?? ''
				})}
			</p>
			<label class="mt-3 flex items-center gap-2 text-xs text-gray-400">
				<input type="checkbox" bind:checked={deleteContents} />
				{$i18n.t('Delete all contents in this folder')}
			</label>
			<div class="mt-4 flex justify-end gap-2">
				<button
					type="button"
					class="rounded-xl px-3 py-1.5 text-sm text-gray-400 hover:bg-gray-800"
					onclick={() => {
						deleteConfirmOpen = false;
					}}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					type="button"
					class="rounded-xl bg-red-500/90 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500"
					onclick={confirmDeleteFolder}
				>
					{$i18n.t('Delete')}
				</button>
			</div>
		</div>
	</div>
{/if}
