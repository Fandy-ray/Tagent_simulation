<script lang="ts">
	import RecursiveFolder from './RecursiveFolder.svelte';
	import type { QaFolder } from '$lib/data/qaFolders';

	export type FolderChatItem = {
		id: string;
		title: string;
		updatedAt: number;
		folderId?: string | null;
	};

	type Props = {
		folder: QaFolder;
		folders: QaFolder[];
		chats: FolderChatItem[];
		depth?: number;
		activeChatId?: string | null;
		selectedFolderId?: string | null;
		dragOverFolderId?: string | null;
		openMenuId?: string | null;
		onSelectFolder?: (folderId: string | null) => void;
		onToggleExpanded?: (folderId: string) => void;
		onOpenMenu?: (folderId: string | null) => void;
		onEdit?: (folder: QaFolder) => void;
		onCreateSub?: (parentId: string) => void;
		onExport?: (folderId: string) => void;
		onDelete?: (folderId: string) => void;
		onSelectChat?: (chatId: string) => void;
		onMoveChatOut?: (chatId: string) => void;
		onChatDragStart?: (event: DragEvent, chatId: string) => void;
		onFolderDragStart?: (event: DragEvent, folderId: string) => void;
		onFolderDragOver?: (event: DragEvent, folderId: string) => void;
		onFolderDragLeave?: (folderId: string) => void;
		onFolderDrop?: (event: DragEvent, folderId: string) => void;
		timeLabel?: (chat: FolderChatItem) => string;
	};

	let {
		folder,
		folders,
		chats,
		depth = 0,
		activeChatId = null,
		selectedFolderId = null,
		dragOverFolderId = null,
		openMenuId = null,
		onSelectFolder = () => {},
		onToggleExpanded = () => {},
		onOpenMenu = () => {},
		onEdit = () => {},
		onCreateSub = () => {},
		onExport = () => {},
		onDelete = () => {},
		onSelectChat = () => {},
		onMoveChatOut = () => {},
		onChatDragStart = () => {},
		onFolderDragStart = () => {},
		onFolderDragOver = () => {},
		onFolderDragLeave = () => {},
		onFolderDrop = () => {},
		timeLabel = () => ''
	}: Props = $props();

	const children = $derived(
		folders
			.filter((f) => f.parentId === folder.id)
			.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }))
	);

	const folderChats = $derived(
		chats.filter((c) => c.folderId === folder.id).sort((a, b) => b.updatedAt - a.updatedAt)
	);

	const selected = $derived(selectedFolderId === folder.id);
	const expanded = $derived(folder.expanded !== false);
	const pad = $derived(Math.min(depth, 4) * 12);
</script>

<div
	class={`mb-0.5 rounded-xl ${dragOverFolderId === folder.id ? 'bg-white/[0.06] ring-1 ring-white/10' : ''}`}
	style={`margin-left:${pad}px`}
	draggable="true"
	ondragstart={(e) => onFolderDragStart(e, folder.id)}
	ondragover={(e) => onFolderDragOver(e, folder.id)}
	ondragleave={() => onFolderDragLeave(folder.id)}
	ondrop={(e) => onFolderDrop(e, folder.id)}
	role="presentation"
>
	<div
		class={`group relative flex items-center rounded-xl transition hover:bg-gray-900 ${
			selected ? 'bg-gray-900 text-white' : 'text-gray-300'
		}`}
	>
		<button
			type="button"
			class="flex shrink-0 items-center self-stretch px-1.5 text-gray-500 hover:text-white"
			aria-label={expanded ? '收起分组' : '展开分组'}
			onclick={(e) => {
				e.stopPropagation();
				onToggleExpanded(folder.id);
			}}
		>
			<svg
				class={`size-3 transition ${expanded ? 'rotate-90' : ''}`}
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2.5"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="m9 6 6 6-6 6"></path>
			</svg>
		</button>

		<button
			type="button"
			class="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 pr-2 text-left"
			onclick={() => {
				onSelectFolder(selected ? null : folder.id);
				if (!expanded) onToggleExpanded(folder.id);
			}}
			ondblclick={() => onEdit(folder)}
		>
			{#if folder.icon}
				<span class="text-sm leading-none">{folder.icon}</span>
			{:else}
				<svg
					class="size-3.5 shrink-0 text-gray-500"
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
			{/if}
			<span class="min-w-0 flex-1 truncate text-sm">{folder.name}</span>
			{#if folderChats.length > 0}
				<span class="text-[10px] text-gray-600">{folderChats.length}</span>
			{/if}
		</button>

		<div class="relative pr-1 opacity-0 transition group-hover:opacity-100">
			<button
				type="button"
				class="rounded-md p-1 text-gray-500 hover:bg-gray-800 hover:text-white"
				aria-label="分组选项"
				onclick={(e) => {
					e.stopPropagation();
					onOpenMenu(openMenuId === folder.id ? null : folder.id);
				}}
			>
				<svg class="size-4" viewBox="0 0 24 24" fill="currentColor">
					<circle cx="5" cy="12" r="1.4"></circle>
					<circle cx="12" cy="12" r="1.4"></circle>
					<circle cx="19" cy="12" r="1.4"></circle>
				</svg>
			</button>
			{#if openMenuId === folder.id}
				<div
					class="absolute right-0 z-50 mt-1 w-44 rounded-xl border border-white/10 bg-gray-900 py-1 shadow-xl"
				>
					<button
						type="button"
						class="flex w-full px-3 py-1.5 text-left text-xs hover:bg-white/[0.06]"
						onclick={() => {
							onCreateSub(folder.id);
							onOpenMenu(null);
						}}
					>
						创建子分组
					</button>
					<button
						type="button"
						class="flex w-full px-3 py-1.5 text-left text-xs hover:bg-white/[0.06]"
						onclick={() => {
							onEdit(folder);
							onOpenMenu(null);
						}}
					>
						编辑
					</button>
					<button
						type="button"
						class="flex w-full px-3 py-1.5 text-left text-xs hover:bg-white/[0.06]"
						onclick={() => {
							onExport(folder.id);
							onOpenMenu(null);
						}}
					>
						导出
					</button>
					<button
						type="button"
						class="flex w-full px-3 py-1.5 text-left text-xs text-red-300 hover:bg-white/[0.06]"
						onclick={() => {
							onDelete(folder.id);
							onOpenMenu(null);
						}}
					>
						删除
					</button>
				</div>
			{/if}
		</div>
	</div>

	{#if expanded}
		{#each children as child (child.id)}
			<RecursiveFolder
				folder={child}
				{folders}
				{chats}
				depth={depth + 1}
				{activeChatId}
				{selectedFolderId}
				{dragOverFolderId}
				{openMenuId}
				{onSelectFolder}
				{onToggleExpanded}
				{onOpenMenu}
				{onEdit}
				{onCreateSub}
				{onExport}
				{onDelete}
				{onSelectChat}
				{onMoveChatOut}
				{onChatDragStart}
				{onFolderDragStart}
				{onFolderDragOver}
				{onFolderDragLeave}
				{onFolderDrop}
				{timeLabel}
			/>
		{/each}

		{#each folderChats as chat (chat.id)}
			<div class="group relative ml-3">
				<button
					type="button"
					class={`flex w-full items-center gap-2 rounded-xl px-2.5 py-1.5 text-left transition ${
						activeChatId === chat.id ? 'bg-gray-900 text-white' : 'text-gray-400 hover:bg-gray-900'
					}`}
					aria-current={activeChatId === chat.id ? 'true' : undefined}
					draggable="true"
					ondragstart={(e) => onChatDragStart(e, chat.id)}
					onclick={() => onSelectChat(chat.id)}
				>
					<span class="min-w-0 flex-1 truncate text-sm">{chat.title}</span>
					<span class="shrink-0 text-[10px] text-gray-600 opacity-0 group-hover:opacity-100">
						{timeLabel(chat)}
					</span>
				</button>
				<button
					type="button"
					class="absolute top-1 right-1 rounded-md p-0.5 text-gray-500 opacity-0 group-hover:opacity-100 hover:bg-gray-800 hover:text-white"
					title="移出分组"
					aria-label="移出分组"
					onclick={(e) => {
						e.stopPropagation();
						onMoveChatOut(chat.id);
					}}
				>
					<svg
						class="size-3.5"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
					>
						<path stroke-linecap="round" d="M18 6 6 18M6 6l12 12"></path>
					</svg>
				</button>
			</div>
		{/each}

		{#if folderChats.length === 0 && children.length === 0}
			<p class="px-4 py-1 text-[11px] text-gray-600">此分组为空</p>
		{/if}
	{/if}
</div>
