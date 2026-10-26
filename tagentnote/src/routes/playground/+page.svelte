<script lang="ts">
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import MockSidebar from '$lib/components/chat/MockSidebar.svelte';
	import type { FolderFormValue } from '$lib/components/chat/FolderModal.svelte';
	import { getAgentModels, streamAgentChat, type AgentModel } from '$lib/apis/agent';
	import { loadQaChats, saveQaChats, type QaChat } from '$lib/data/qaConversations';
	import {
		collectFolderTreeIds,
		createQaFolder,
		loadQaFolders,
		saveQaFolders,
		type QaFolder
	} from '$lib/data/qaFolders';

	type Role = 'user' | 'assistant';
	type Message = { id: number; role: Role; content: string };
	type Tab = 'chat' | 'completions' | 'images';

	let activeTab = $state<Tab>('chat');
	let sidebarOpen = $state(true);
	let showSystem = $state(false);
	let system = $state('');
	let role = $state<Role>('user');
	let message = $state('');
	let selectedModel = $state('');
	// Playground 的对话只在这个页面里，不写进答疑的会话记录（以前会把答疑当前那段对话读进来、
	// 改动又写回去，在这里试几句就改坏了学生真正的答疑记录）
	let messages = $state<Message[]>([]);
	let chats = $state<QaChat[]>([]);
	let folders = $state<QaFolder[]>([]);
	let selectedFolderId = $state<string | null>(null);
	let completionText = $state('');
	let imagePrompt = $state('');
	let imageInput = $state<HTMLInputElement | null>(null);

	// 图像生成没有接后端，示例图片取自 picsum.photos。种子只给一个本地算出来的数字，别把学生输入的提示词原样发到第三方
	const imageSeed = (text: string) => {
		let hash = 2166136261;
		for (const char of text) {
			hash ^= char.codePointAt(0) ?? 0;
			hash = Math.imul(hash, 16777619);
		}
		return (hash >>> 0).toString(36);
	};
	let generatedImages = $state<string[]>([]);
	let uploadedImages = $state<string[]>([]);
	let loading = $state(false);
	let abortController: AbortController | null = null;
	let moreOpen = $state(false);
	let modelOpen = $state(false);
	let modelSearch = $state('');
	let nextId = 1;
	let models = $state<AgentModel[]>([]);
	let modelsError = $state('');
	let runError = $state('');

	let completionModel = $state('');
	const modelLabel = (id: string) => models.find((model) => model.id === id)?.name || id;
	const filteredModels = $derived(
		models.filter((model) =>
			`${model.name} ${model.id}`.toLowerCase().includes(modelSearch.trim().toLowerCase())
		)
	);

	// 侧栏是答疑的会话列表：这里只读、点了去答疑页打开，文件夹操作照常存
	const sidebarChats = $derived(chats.filter((chat) => !chat.archived));

	const loadChat = (chatId: string) => {
		if (!chats.some((item) => item.id === chatId)) return;
		void goto(resolve(`/qa?chat=${encodeURIComponent(chatId)}`));
	};

	onMount(() => {
		chats = loadQaChats().chats;
		folders = loadQaFolders();
		getAgentModels()
			.then((list) => {
				models = list.data;
				selectedModel ||= list.data[0]?.id ?? '';
				completionModel ||= list.data[0]?.id ?? '';
				modelsError = list.data.length ? '' : '还没有登记模型：先去「模型」页登记一个。';
			})
			.catch((error: unknown) => {
				modelsError = error instanceof Error ? error.message : '读取模型列表失败。';
			});
	});

	/** 直接和模型聊（mode = chat）：不检索知识库，系统指令、消息原样发出去 */
	const streamDirect = async (
		model: string,
		turns: { role: Role; content: string }[],
		systemPrompt: string,
		onDelta: (content: string) => void
	) => {
		const last = turns.at(-1);
		if (!last) return;
		abortController = new AbortController();
		try {
			await streamAgentChat(last.content, model, onDelta, abortController.signal, {
				mode: 'chat',
				system: systemPrompt.trim() || undefined,
				history: turns.slice(0, -1)
			});
		} finally {
			abortController = null;
		}
	};

	const failed = (error: unknown) =>
		!(error instanceof DOMException && error.name === 'AbortError');

	const handleSelectFolder = (folderId: string | null) => {
		selectedFolderId = folderId;
	};

	const handleCreateFolder = (value: FolderFormValue, parentId: string | null = null) => {
		folders = [
			...folders,
			createQaFolder(value.name, parentId, {
				systemPrompt: value.systemPrompt,
				backgroundImageUrl: value.backgroundImageUrl,
				knowledgeItems: value.knowledgeItems
			})
		];
		saveQaFolders(folders);
	};

	const handleUpdateFolder = (folderId: string, value: FolderFormValue) => {
		folders = folders.map((folder) =>
			folder.id === folderId
				? {
						...folder,
						name: value.name.trim() || folder.name,
						systemPrompt: value.systemPrompt,
						backgroundImageUrl: value.backgroundImageUrl,
						knowledgeItems: value.knowledgeItems,
						updatedAt: Date.now()
					}
				: folder
		);
		saveQaFolders(folders);
	};

	const handleToggleFolderExpanded = (folderId: string) => {
		folders = folders.map((folder) =>
			folder.id === folderId ? { ...folder, expanded: !folder.expanded } : folder
		);
		saveQaFolders(folders);
	};

	const handleDeleteFolder = (folderId: string, deleteContents: boolean) => {
		const ids = collectFolderTreeIds(folders, folderId);
		folders = folders.filter((folder) => !ids.has(folder.id));
		saveQaFolders(folders);

		if (deleteContents) {
			const removed = chats
				.filter((chat) => chat.folderId && ids.has(chat.folderId))
				.map((chat) => chat.id);
			chats = chats.filter((chat) => !chat.folderId || !ids.has(chat.folderId));
			const stored = loadQaChats();
			saveQaChats(chats, removed.includes(stored.activeId ?? '') ? null : stored.activeId);
		} else {
			chats = chats.map((chat) =>
				chat.folderId && ids.has(chat.folderId) ? { ...chat, folderId: null } : chat
			);
			saveQaChats(chats, loadQaChats().activeId);
		}

		if (selectedFolderId && ids.has(selectedFolderId)) selectedFolderId = null;
	};

	const handleMoveChatToFolder = (chatId: string, folderId: string | null) => {
		chats = chats.map((chat) =>
			chat.id === chatId ? { ...chat, folderId, updatedAt: Date.now() } : chat
		);
		saveQaChats(chats, loadQaChats().activeId);
	};

	const handleMoveFolder = (folderId: string, parentId: string | null) => {
		if (parentId === folderId) return;
		folders = folders.map((folder) =>
			folder.id === folderId ? { ...folder, parentId, updatedAt: Date.now() } : folder
		);
		saveQaFolders(folders);
	};

	const addMessage = () => {
		if (!message.trim() || loading) return;
		messages = [...messages, { id: nextId++, role, content: message }];
		message = '';
	};

	const runChat = async () => {
		if (loading) return;
		if (message.trim()) addMessage();
		if (messages.length === 0 || messages.at(-1)?.role !== 'user') return;
		if (!selectedModel) {
			runError = modelsError || '先选一个模型。';
			return;
		}

		loading = true;
		runError = '';
		const turns = messages.map(({ role, content }) => ({ role, content }));
		const assistantId = nextId++;
		messages = [...messages, { id: assistantId, role: 'assistant', content: '' }];
		try {
			await streamDirect(selectedModel, turns, system, (content) => {
				messages = messages.map((item) => (item.id === assistantId ? { ...item, content } : item));
			});
		} catch (error) {
			if (failed(error)) runError = error instanceof Error ? error.message : '运行失败。';
		} finally {
			// 一个字都没回（出错、马上取消）就别留一条空的助手消息
			messages = messages.filter((item) => item.id !== assistantId || item.content);
			loading = false;
		}
	};

	const stopResponse = () => {
		abortController?.abort();
	};

	const chatToText = () =>
		[
			system.trim() ? `### 系统\n${system}` : '',
			...messages.map((item) => `### ${item.role === 'user' ? '用户' : '助手'}\n${item.content}`)
		]
			.filter(Boolean)
			.join('\n\n');

	const exportChat = () => {
		const url = URL.createObjectURL(new Blob([chatToText()], { type: 'text/plain;charset=utf-8' }));
		const link = document.createElement('a');
		link.href = url;
		link.download = `对话-${Date.now()}.txt`;
		link.click();
		URL.revokeObjectURL(url);
		moreOpen = false;
	};

	const copyChat = async () => {
		try {
			await navigator.clipboard.writeText(chatToText());
		} catch {
			// clipboard unavailable in mock environment
		}
		moreOpen = false;
	};

	const removeMessage = (id: number) => {
		messages = messages.filter((item) => item.id !== id);
	};

	/** 续写：让模型接着文本往下写，写出来的直接接在原文后面 */
	const runCompletion = async () => {
		if (!completionText.trim() || loading) return;
		if (!completionModel) {
			runError = modelsError || '先选一个模型。';
			return;
		}
		loading = true;
		runError = '';
		const input = completionText;
		try {
			await streamDirect(
				completionModel,
				[{ role: 'user', content: input }],
				'接着用户给的文字往下写。只输出续写的部分，不要重复原文，不要解释，不要加引号或标题。',
				(content) => (completionText = input + content)
			);
		} catch (error) {
			if (failed(error)) runError = error instanceof Error ? error.message : '运行失败。';
		} finally {
			loading = false;
		}
	};

	const addImages = (event: Event) => {
		const input = event.currentTarget as HTMLInputElement;
		const files = Array.from(input.files ?? []).filter((file) => file.type.startsWith('image/'));
		for (const file of files) {
			const reader = new FileReader();
			reader.onload = () => {
				if (typeof reader.result === 'string') uploadedImages = [...uploadedImages, reader.result];
			};
			reader.readAsDataURL(file);
		}
		input.value = '';
	};

	const removeUploadedImage = (index: number) => {
		uploadedImages = uploadedImages.filter((_, itemIndex) => itemIndex !== index);
	};

	const runImage = async () => {
		if ((!imagePrompt.trim() && uploadedImages.length === 0) || loading) return;
		loading = true;
		await new Promise((resolve) => setTimeout(resolve, 650));
		generatedImages = [
			`https://picsum.photos/seed/${imageSeed(imagePrompt || 'uploaded-image')}-${generatedImages.length}/720/520`,
			...generatedImages
		];
		imagePrompt = '';
		loading = false;
	};
</script>

<svelte:head>
	<title>AI 对话探索区 | TAgent</title>
</svelte:head>

<div class="playground-shell">
	{#if sidebarOpen}
		<MockSidebar
			activeChatId={null}
			{selectedFolderId}
			chats={sidebarChats}
			searchChats={chats}
			{folders}
			userName="Tagent"
			avatarText="T"
			activeNav="chats"
			onHome={() => goto(resolve('/qa'))}
			onNewChat={() => goto(resolve('/qa'))}
			onSelectChat={loadChat}
			onSelectFolder={handleSelectFolder}
			onCreateFolder={handleCreateFolder}
			onUpdateFolder={handleUpdateFolder}
			onDeleteFolder={handleDeleteFolder}
			onToggleFolderExpanded={handleToggleFolderExpanded}
			onMoveChatToFolder={handleMoveChatToFolder}
			onMoveFolder={handleMoveFolder}
			onClose={() => (sidebarOpen = false)}
			onOpenNotes={() => goto(resolve('/notebook'))}
			onOpenWorkspace={() => goto(resolve('/workspace'))}
			onSettings={() => goto(resolve('/qa?sidebar-action=settings'))}
			onArchivedChats={() => goto(resolve('/qa?sidebar-action=archived'))}
			onPlayground={() => (activeTab = 'chat')}
			onAdmin={() => goto(resolve('/admin/users/overview'))}
			onShortcuts={() => goto(resolve('/qa?sidebar-action=shortcuts'))}
			onSignOut={() => goto(resolve('/welcome'))}
		/>
	{/if}
	<div class="playground">
		<nav class="tabs" aria-label="探索工具">
			{#if !sidebarOpen}
				<button class="sidebar-open" aria-label="展开侧边栏" onclick={() => (sidebarOpen = true)}
					>☰</button
				>
			{/if}
			<button class:active={activeTab === 'chat'} onclick={() => (activeTab = 'chat')}>对话</button>
			<button class:active={activeTab === 'completions'} onclick={() => (activeTab = 'completions')}
				>续写</button
			>
			<button class:active={activeTab === 'images'} onclick={() => (activeTab = 'images')}
				>图片</button
			>
		</nav>

		{#if activeTab === 'chat'}
			<section class="chat-panel">
				<div class="system-row">
					<button
						class="system-toggle"
						aria-expanded={showSystem}
						onclick={() => (showSystem = !showSystem)}
					>
						<span class="system-title">系统指令</span>
						{#if !showSystem && system.trim()}<span class="system-preview">{system}</span>{/if}
						<span class="system-icon">
							{#if showSystem}
								<svg
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									stroke-linecap="round"
									stroke-linejoin="round"
								>
									<path d="m18 15-6-6-6 6" />
								</svg>
							{:else}
								<svg
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.6"
									stroke-linecap="round"
									stroke-linejoin="round"
								>
									<path
										d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.862 4.487Zm0 0L19.5 7.125"
									/>
								</svg>
							{/if}
						</span>
					</button>

					<div class="more-wrap">
						<button
							type="button"
							class="more-button"
							aria-label="更多选项"
							onclick={() => (moreOpen = !moreOpen)}
						>
							<svg viewBox="0 0 24 24" fill="currentColor">
								<circle cx="5" cy="12" r="1.6" />
								<circle cx="12" cy="12" r="1.6" />
								<circle cx="19" cy="12" r="1.6" />
							</svg>
						</button>
						{#if moreOpen}
							<button
								type="button"
								class="more-backdrop"
								aria-label="关闭菜单"
								onclick={() => (moreOpen = false)}
							></button>
							<div class="more-menu">
								<button type="button" onclick={exportChat}>导出对话</button>
								<button type="button" onclick={() => void copyChat()}>复制对话</button>
							</div>
						{/if}
					</div>
				</div>

				{#if showSystem}
					<div class="system-content">
						<textarea bind:value={system} rows="4" placeholder="你是一个乐于助人的助手。"
						></textarea>
					</div>
				{/if}

				<div class="messages-container">
					<div class="messages-list">
						{#each messages as item (item.id)}
							<article class="conversation-message">
								<div class="conversation-avatar" class:assistant-avatar={item.role === 'assistant'}>
									{item.role === 'user' ? '你' : 'AI'}
								</div>
								<div class="conversation-content">
									<div class="conversation-author">{item.role === 'user' ? '你' : '助手'}</div>
									<textarea
										class="conversation-textarea"
										rows="1"
										bind:value={item.content}
										aria-label={`${item.role === 'user' ? '用户' : '助手'}消息`}></textarea>
								</div>
								<button
									class="delete-message"
									aria-label="删除消息"
									onclick={() => removeMessage(item.id)}
								>
									<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
										<path stroke-linecap="round" d="M15 12H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
									</svg>
								</button>
							</article>
						{/each}
						{#if runError}<p class="run-error" role="alert">{runError}</p>{/if}
					</div>
				</div>

				<div class="input-area">
					<div class="input-box">
						<textarea
							class="message-input"
							bind:value={message}
							rows="2"
							placeholder={`在此处输入 ${role === 'user' ? '用户' : '助手'} 的对话内容`}
							onkeydown={(event) => {
								if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !loading) {
									event.preventDefault();
									void runChat();
								}
							}}></textarea>
						<div class="composer-row">
							<button
								class="role-button"
								aria-label="切换消息角色"
								onclick={() => (role = role === 'user' ? 'assistant' : 'user')}
							>
								{role === 'user' ? '用户' : '助手'}
							</button>
							<div class="composer-right">
								<select class="model-select" bind:value={selectedModel} aria-label="选择模型">
									{#each models as model (model.id)}<option value={model.id}
											>{model.name || model.id}</option
										>{/each}
								</select>
								{#if !loading}
									<button class="add-button" disabled={!message} onclick={addMessage}>添加</button>
									<button class="run-button" onclick={() => void runChat()}>运行</button>
								{:else}
									<button class="cancel-button" onclick={stopResponse}>取消</button>
								{/if}
							</div>
						</div>
					</div>
				</div>
			</section>
		{:else if activeTab === 'completions'}
			<section class="completion-panel">
				<div class="completion-model">
					<button
						class="model-trigger"
						aria-expanded={modelOpen}
						onclick={() => (modelOpen = !modelOpen)}
					>
						<span>{completionModel ? modelLabel(completionModel) : '选择模型'}</span>
						<svg
							width="16"
							height="16"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"><path d="m6 9 6 6 6-6" /></svg
						>
					</button>
					{#if modelOpen}
						<button
							class="model-backdrop"
							aria-label="关闭模型选择"
							onclick={() => (modelOpen = false)}
						></button>
						<div class="model-popover">
							<div class="model-search">
								<svg
									width="20"
									height="20"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									><circle cx="10.5" cy="10.5" r="7.5" /><path d="m16 16 5 5" /></svg
								>
								<input aria-label="搜索模型" placeholder="搜索模型" bind:value={modelSearch} />
							</div>
							<div class="model-options">
								{#each filteredModels as model, index (model.id)}
									<button
										class="model-option"
										class:highlighted={completionModel === model.id ||
											(!completionModel && index === 0)}
										onclick={() => {
											completionModel = model.id;
											modelOpen = false;
										}}
									>
										<span class="model-logo">T</span>
										<span>{model.name || model.id}</span>
									</button>
								{:else}<p class="model-empty">{modelsError || '未找到模型'}</p>{/each}
							</div>
						</div>
					{/if}
				</div>
				<div class="completion-area">
					<textarea
						bind:value={completionText}
						placeholder="你是一个乐于助人的助手。"
						onkeydown={(event) => {
							if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !loading) {
								event.preventDefault();
								void runCompletion();
							}
						}}></textarea>
				</div>
				<div class="completion-actions">
					{#if runError}<p class="run-error" role="alert">{runError}</p>{/if}
					{#if !loading}
						<button
							class="run-button"
							disabled={!completionText.trim()}
							onclick={() => void runCompletion()}>运行</button
						>
					{:else}
						<button class="cancel-button" onclick={stopResponse}>取消</button>
					{/if}
				</div>
			</section>
		{:else}
			<section class="image-panel">
				<div class="image-results">
					{#if uploadedImages.length > 0 || generatedImages.length > 0}
						<div class="image-grid">
							{#each uploadedImages as image, index (`${index}:${image}`)}
								<div class="image-item">
									<img src={image} alt="已添加的图像" />
									<button
										class="remove-image"
										aria-label="移除图像"
										onclick={() => removeUploadedImage(index)}>×</button
									>
								</div>
							{/each}
							{#each generatedImages as image, index (`${index}:${image}`)}<img
									src={image}
									alt="生成的图像"
								/>{/each}
						</div>
					{:else}
						<div class="image-empty">
							<span>生成的图像将显示在此处</span>
							<small>图像生成还没有接后端：点「运行」显示的是示例图片</small>
						</div>
					{/if}
				</div>
				<div class="input-area">
					<div class="input-box">
						<input
							bind:this={imageInput}
							class="file-input"
							type="file"
							accept="image/*"
							multiple
							onchange={addImages}
						/>
						<textarea
							class="message-input"
							bind:value={imagePrompt}
							rows="2"
							placeholder="描述图像..."></textarea>
						<div class="input-actions">
							<button class="secondary-button" onclick={() => imageInput?.click()}
								>＋ 添加图像</button
							>
							{#if !loading}
								<button
									class="run-button"
									disabled={!imagePrompt.trim() && uploadedImages.length === 0}
									onclick={() => void runImage()}>运行</button
								>
							{:else}
								<button class="cancel-button" onclick={() => (loading = false)}>取消</button>
							{/if}
						</div>
					</div>
				</div>
			</section>
		{/if}
	</div>
</div>

<style>
	:global(*) {
		box-sizing: border-box;
	}
	.run-error {
		margin: 8px 0 0;
		color: #f87171;
		font-size: 13px;
	}
	:global(body) {
		margin: 0;
	}
	.playground-shell {
		display: flex;
		height: 100dvh;
		max-height: 100dvh;
		overflow: hidden;
		color: #e5e7eb;
	}
	.playground {
		display: flex;
		min-width: 0;
		flex: 1;
		flex-direction: column;
		overflow: hidden;
		color: #e5e7eb;
		background: transparent;
	}
	.sidebar-open {
		flex: none;
		margin-right: 2px;
		color: #e5e7eb;
	}
	.tabs {
		display: flex;
		width: fit-content;
		max-width: 100%;
		flex: none;
		gap: 2px;
		overflow-x: auto;
		padding: 4px 8px 2px;
	}
	.tabs button {
		min-width: fit-content;
		padding: 6px 8px;
		color: #6b7280;
		background: transparent;
		border-radius: 7px;
		font-size: 13px;
		transition:
			color 0.15s,
			background 0.15s;
	}
	.tabs button:hover {
		color: #d1d5db;
	}
	.tabs button.active {
		color: #f9fafb;
	}
	.chat-panel,
	.image-panel {
		display: flex;
		width: 100%;
		min-height: 0;
		flex: 1;
		flex-direction: column;
		padding: 0 14px;
	}
	.system-row {
		display: flex;
		width: 100%;
		flex: none;
		align-items: center;
		gap: 6px;
		padding: 0 0 2px;
	}
	.system-toggle {
		display: flex;
		min-width: 0;
		flex: 1;
		align-items: center;
		gap: 8px;
		padding: 5px 6px;
		color: inherit;
		background: transparent;
		border: 1px solid rgb(255 255 255 / 8%);
		border-radius: 8px;
		text-align: left;
		font-size: 14px;
	}
	.system-toggle:hover {
		background: rgb(255 255 255 / 3%);
	}
	.system-title {
		flex: none;
		margin-left: 2px;
		font-weight: 500;
	}
	.system-preview {
		min-width: 0;
		flex: 1;
		overflow: hidden;
		color: #6b7280;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.system-icon {
		display: flex;
		flex: none;
		align-items: center;
		margin-left: auto;
		padding: 3px;
		color: #9ca3af;
		border-radius: 6px;
	}
	.system-icon svg {
		width: 14px;
		height: 14px;
	}
	.more-wrap {
		position: relative;
		flex: none;
	}
	.more-button {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 6px;
		color: #9ca3af;
		background: transparent;
		border-radius: 8px;
		transition:
			color 0.15s,
			background 0.15s;
	}
	.more-button svg {
		width: 16px;
		height: 16px;
	}
	.more-button:hover {
		color: #e5e7eb;
		background: rgb(255 255 255 / 5%);
	}
	.more-backdrop {
		position: fixed;
		inset: 0;
		z-index: 40;
	}
	.more-menu {
		position: absolute;
		top: calc(100% + 4px);
		right: 0;
		z-index: 50;
		display: flex;
		min-width: 140px;
		flex-direction: column;
		padding: 4px;
		background: #22262b;
		border: 1px solid rgb(255 255 255 / 10%);
		border-radius: 12px;
		box-shadow: 0 12px 32px rgb(0 0 0 / 45%);
	}
	.more-menu button {
		padding: 7px 10px;
		color: #e5e7eb;
		background: transparent;
		border-radius: 8px;
		text-align: left;
		font-size: 13px;
	}
	.more-menu button:hover {
		background: rgb(255 255 255 / 6%);
	}
	.system-content {
		flex: none;
		padding: 5px 7px 2px;
	}
	.system-content textarea {
		display: block;
		width: 100%;
		min-height: 72px;
		max-height: 555px;
		resize: none;
		color: inherit;
		background: transparent;
		border: 0;
		outline: none;
		font-size: 14px;
	}
	.messages-container {
		display: flex;
		width: 98%;
		min-height: 0;
		flex: 1;
		flex-direction: column;
		align-self: center;
		overflow-x: hidden !important;
		overflow-y: auto;
		padding: 6px 0 10px;
		scrollbar-width: none;
	}
	.messages-container::-webkit-scrollbar {
		display: none;
		width: 0;
		height: 0;
	}
	.messages-list {
		width: 100%;
		flex: 1;
		padding: 12px 4px;
	}
	.conversation-message {
		position: relative;
		display: flex;
		width: 100%;
		align-items: flex-start;
		gap: 12px;
		max-width: none;
		margin: 0 0 22px;
		padding: 2px 8px;
		overflow: hidden;
	}
	.conversation-avatar {
		display: grid;
		width: 30px;
		height: 30px;
		flex: none;
		place-items: center;
		color: #f3f4f6;
		background: #3b82f6;
		border-radius: 50%;
		font-size: 11px;
		font-weight: 600;
	}
	.conversation-avatar.assistant-avatar {
		color: #171717;
		background: #f3f4f4;
	}
	.conversation-content {
		min-width: 0;
		flex: 1;
	}
	.conversation-author {
		margin: 3px 0 5px;
		color: #d1d5db;
		font-size: 13px;
		font-weight: 600;
	}
	.conversation-textarea {
		display: block;
		width: 100%;
		min-height: 28px;
		padding: 0;
		resize: vertical;
		color: #e5e7eb;
		background: transparent;
		border: 0;
		outline: none;
		font-size: 14px;
		line-height: 1.7;
		white-space: pre-wrap;
	}
	.conversation-textarea:focus {
		background: rgb(255 255 255 / 3%);
	}
	.conversation-message .delete-message {
		position: absolute;
		top: 1px;
		right: -12px;
	}
	.delete-message {
		display: flex;
		flex: none;
		align-items: flex-start;
		padding: 7px 2px;
		color: #6b7280;
		background: transparent;
		opacity: 0;
		transition:
			color 0.15s,
			opacity 0.15s;
	}
	.delete-message svg {
		width: 20px;
		height: 20px;
	}
	.delete-message:focus-visible {
		opacity: 1;
	}
	.delete-message:hover {
		color: #d1d5db;
	}
	.input-area {
		flex: none;
		padding-bottom: 12px;
		min-width: 0;
		overflow: hidden;
	}
	.input-box {
		width: 100%;
		min-width: 0;
		overflow: hidden;
		padding: 10px 12px;
		border: 1px solid rgb(255 255 255 / 12%);
		border-radius: 12px;
	}
	.message-input {
		display: block;
		width: 100%;
		min-width: 0;
		min-height: 48px;
		max-height: 150px;
		padding: 3px 1px;
		resize: none;
		overflow-x: hidden !important;
		overflow-y: auto;
		white-space: pre-wrap;
		word-break: break-word;
		overflow-wrap: anywhere;
		color: inherit;
		background: transparent;
		border: 0;
		outline: none;
		font-size: 14px;
		line-height: 1.5;
		scrollbar-width: none;
	}
	.message-input::-webkit-scrollbar {
		display: none;
		width: 0;
		height: 0;
	}
	textarea::placeholder {
		color: #6b7280;
	}
	.composer-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		margin-top: 8px;
	}
	.composer-right {
		display: flex;
		min-width: 0;
		flex: 1;
		align-items: center;
		justify-content: flex-end;
		gap: 8px;
	}
	.role-button,
	.add-button,
	.secondary-button,
	.run-button,
	.cancel-button {
		flex: none;
		padding: 6px 14px;
		border: 0;
		border-radius: 8px;
		font-size: 14px;
		font-weight: 500;
		transition: background 0.15s;
	}
	.role-button,
	.add-button,
	.secondary-button {
		color: #d1d5db;
		background: #262a2f;
	}
	.role-button:hover,
	.add-button:hover:not(:disabled),
	.secondary-button:hover:not(:disabled) {
		background: #2f343a;
	}
	.add-button:disabled,
	.secondary-button:disabled,
	.run-button:disabled {
		cursor: not-allowed;
		opacity: 0.6;
	}
	.composer-right select {
		max-width: 180px;
		min-width: 0;
		flex: 0 1 180px;
		padding: 6px 8px;
		color: inherit;
		background: transparent;
		border: 1px solid rgb(255 255 255 / 10%);
		border-radius: 8px;
		outline: none;
		font-size: 13px;
	}
	.composer-right select option {
		color: #111827;
		background: #f9fafb;
	}
	.run-button {
		color: #000;
		background: #fff;
	}
	.run-button:hover:not(:disabled) {
		background: #e5e7eb;
	}
	.cancel-button {
		color: #111827;
		background: #d1d5db;
	}
	.cancel-button:hover {
		background: #e5e7eb;
	}
	.completion-panel {
		display: flex;
		width: 100%;
		min-height: 0;
		flex: 1;
		flex-direction: column;
		padding: 0 10px 8px;
	}
	.completion-model {
		position: relative;
		z-index: 10;
		display: flex;
		flex: none;
		align-items: center;
		margin: 0 0 2px;
	}
	.model-trigger {
		display: flex;
		width: 100%;
		align-items: center;
		justify-content: space-between;
		padding: 3px 2px;
		color: #e5e7eb;
		background: transparent;
		border: 0;
		font-size: 13px;
		text-align: left;
	}
	.model-trigger svg {
		flex: none;
		color: #9ca3af;
	}
	.model-backdrop {
		position: fixed;
		inset: 0;
		z-index: 20;
		background: transparent;
	}
	.model-popover {
		position: absolute;
		top: calc(100% + 12px);
		left: -10px;
		z-index: 30;
		width: min(420px, calc(100vw - 24px));
		max-height: min(370px, calc(100dvh - 100px));
		overflow: auto;
		padding: 8px;
		background: #242424;
		border: 1px solid rgb(255 255 255 / 8%);
		border-radius: 18px;
		box-shadow: 0 16px 36px rgb(0 0 0 / 45%);
	}
	.model-search {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 9px;
		color: #f3f4f6;
	}
	.model-search input {
		width: 100%;
		color: #e5e7eb;
		background: transparent;
		border: 0;
		outline: none;
		font-size: 14px;
	}
	.model-search input::placeholder {
		color: #9ca3af;
	}
	.model-options {
		padding: 0 1px 2px;
	}
	.model-option {
		display: flex;
		width: 100%;
		min-height: 44px;
		align-items: center;
		gap: 9px;
		padding: 7px 10px;
		color: #e5e7eb;
		background: transparent;
		border: 0;
		border-radius: 13px;
		font-size: 14px;
		text-align: left;
	}
	.model-option:hover,
	.model-option.highlighted {
		background: #343434;
	}
	.model-logo {
		display: grid;
		width: 26px;
		height: 26px;
		flex: none;
		place-items: center;
		color: #111;
		background: #f5f5f5;
		border-radius: 50%;
		font-size: 9px;
		font-weight: 800;
	}
	.model-empty {
		margin: 0;
		padding: 14px 10px;
		color: #9ca3af;
		font-size: 13px;
	}
	.completion-area {
		display: flex;
		min-height: 0;
		flex: 1;
	}
	.completion-area textarea {
		width: 100%;
		height: 100%;
		min-height: 120px;
		padding: 9px 8px;
		resize: none;
		color: inherit;
		background: transparent;
		border: 1px solid rgb(255 255 255 / 5%);
		border-radius: 8px;
		outline: none;
		font-size: 14px;
	}
	.completion-area textarea::placeholder {
		color: #8a8a8a;
	}
	.completion-actions {
		display: flex;
		flex: none;
		justify-content: flex-end;
		align-items: center;
		gap: 12px;
		padding: 6px 0 0;
	}
	.completion-actions .run-error {
		margin: 0 auto 0 0;
	}
	.completion-actions .run-button {
		padding: 6px 11px;
		font-size: 12px;
	}
	.image-panel {
		padding-top: 1px;
	}
	.input-actions {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		margin-top: 8px;
	}
	.image-results {
		min-height: 0;
		flex: 1;
		overflow: auto;
		padding: 5px 0 10px;
	}
	.image-empty {
		display: flex;
		flex-direction: column;
		gap: 4px;
		height: 100%;
		min-height: 160px;
		align-items: center;
		justify-content: center;
		text-align: center;
		color: #6b7280;
		font-size: 14px;
	}
	.image-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 12px;
	}
	.image-grid img {
		width: 100%;
		aspect-ratio: 1;
		border: 1px solid rgb(255 255 255 / 10%);
		border-radius: 9px;
		object-fit: cover;
	}
	.file-input {
		display: none;
	}
	.image-item {
		position: relative;
		min-width: 0;
	}
	.remove-image {
		position: absolute;
		top: 6px;
		right: 6px;
		width: 24px;
		height: 24px;
		color: white;
		background: rgb(0 0 0 / 65%);
		border-radius: 50%;
		font-size: 18px;
		line-height: 1;
	}
	@media (min-width: 768px) {
		.chat-panel,
		.image-panel {
			padding-right: 14px;
			padding-left: 14px;
		}
		.image-grid {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}
	@media (max-width: 480px) {
		.composer-right select {
			flex-basis: 96px;
			max-width: 96px;
		}
		.role-button,
		.add-button,
		.secondary-button,
		.run-button,
		.cancel-button {
			padding-right: 10px;
			padding-left: 10px;
		}
	}
</style>
