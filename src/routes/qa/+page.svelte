<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onDestroy, onMount, tick } from 'svelte';

	import { getAgentModels, streamAgentChat } from '$lib/apis/agent';
	import {
		getSourceText,
		listNotebookKnowledge,
		listNotebooks,
		searchKnowledge,
		type NotebookSummary
	} from '$lib/apis/opennotebook';
	import MockMessageInput from '$lib/components/chat/MockMessageInput.svelte';
	import PaperTaskCard from '$lib/components/chat/PaperTaskCard.svelte';
	import MockMessages, { type MockMessage } from '$lib/components/chat/MockMessages.svelte';
	import ChatControlsPanel from '$lib/components/chat/ChatControlsPanel.svelte';
	import MockNavbar from '$lib/components/chat/MockNavbar.svelte';
	import MockPlaceholder from '$lib/components/chat/MockPlaceholder.svelte';
	import MockSidebar from '$lib/components/chat/MockSidebar.svelte';
	import ArchivedChatsModal from '$lib/components/layout/ArchivedChatsModal.svelte';
	import SaveToNotebookDialog from '$lib/components/chat/SaveToNotebookDialog.svelte';
	import SettingsModal from '$lib/components/chat/SettingsModal.svelte';
	import DataControls from '$lib/components/chat/Settings/DataControls.svelte';
	import ShortcutsModal from '$lib/components/chat/ShortcutsModal.svelte';
	import { buildQaCitations, enrichCitationsWithPages } from '$lib/data/citations';
	import {
		loadChatControls,
		saveChatControls,
		toAgentOptions,
		type ChatControlParams
	} from '$lib/data/chatControls';
	import type { KnowledgeCollection } from '$lib/data/knowledge';
	import { loadQaChats, saveQaChats, type QaChat } from '$lib/data/qaConversations';
	import {
		buildPaperPrompt,
		DEFAULT_PAPER_CONTEXT,
		DEFAULT_PAPER_TASK,
		paperIntentDisplay,
		paperIntentFromPrompt,
		paperChatTitle,
		type PaperIntent,
		type PaperContext,
		type PaperSection,
		type PaperTask
	} from '$lib/data/paperWorkflow';
	import {
		collectFolderTreeIds,
		createQaFolder,
		loadQaFolders,
		saveQaFolders,
		wouldCreateCycle,
		type QaFolder
	} from '$lib/data/qaFolders';
	import type { FolderFormValue } from '$lib/components/chat/FolderModal.svelte';
	import {
		applyHighContrast,
		applyTextScale,
		applyTheme,
		loadUserSettings,
		playNotificationSound,
		saveUserSettings,
		type UserSettings
	} from '$lib/data/userSettings';

	type AssistMode = 'qa' | 'paper';
	type QueuedPrompt = { requestContent: string; displayContent: string };

	let sidebarOpen = $state(true);
	let activeChatId = $state<string | null>(null);
	let selectedFolderId = $state<string | null>(null);
	let folders = $state<QaFolder[]>([]);
	let selectedModelId = $state($page.url.searchParams.get('model') ?? '');
	let assistMode = $state<AssistMode>(
		$page.url.searchParams.get('mode') === 'paper' ? 'paper' : 'qa'
	);
	let temporaryChat = $state($page.url.searchParams.get('temporary-chat') === 'true');
	let messageQueue = $state<QueuedPrompt[]>([]);
	let changelogOpen = $state(false);
	let dictationEnabled = $state(false);
	let controlsOpen = $state(false);
	let chatControls = $state<ChatControlParams>(loadChatControls());
	let prompt = $state('');
	let generating = $state(false);
	let messages = $state<MockMessage[]>([]);
	let messagesContainer = $state<HTMLDivElement | null>(null);
	let modelOptions = $state<{ id: string; name: string }[]>([]);
	let collectionId = $state($page.url.searchParams.get('notebook') ?? '');
	let notebooks = $state<NotebookSummary[]>([]);
	let collections = $state<KnowledgeCollection[]>([]);
	let notebooksLoading = $state(true);
	let paperTaskSyncTimer: number | null = null;
	let generationSeq = 0;
	let abortController: AbortController | null = null;
	let saveOpen = $state(false);
	let saveTitle = $state('答疑摘录');
	let saveContent = $state('');
	let saveToast = $state('');
	let chats = $state<QaChat[]>([]);
	let paperTitle = $state($page.url.searchParams.get('paper_title') ?? '');
	let paperKeywords = $state($page.url.searchParams.get('paper_keywords') ?? '');
	let paperSection = $state<PaperSection>(
		($page.url.searchParams.get('paper_section') as PaperSection) || DEFAULT_PAPER_TASK.section
	);
	let paperContext = $state<PaperContext>({ ...DEFAULT_PAPER_CONTEXT });
	let settingsOpen = $state(false);
	let dataOpen = $state(false);
	let archivedOpen = $state(false);
	let shortcutsOpen = $state(false);
	let userSettings = $state<UserSettings>(loadUserSettings());

	// 两种助手模式使用独立的会话空间。旧数据没有 mode 时按课程答疑处理，
	// 这样升级前已有的普通对话仍然可以正常显示。
	const modeChats = $derived(
		chats.filter((chat) => (chat.mode ?? 'qa') === assistMode)
	);

	const sidebarChats = $derived(
		modeChats
			.filter((chat) => !chat.archived)
			.map((chat) => ({
				id: chat.id,
				title: chat.title,
				updatedAt: chat.updatedAt,
				folderId: chat.folderId ?? null
			}))
	);

	const archivedChats = $derived(
		modeChats
			.filter((chat) => chat.archived)
			.map((chat) => ({
				id: chat.id,
				title: chat.title,
				updatedAt: chat.updatedAt,
				archived: true
			}))
			.sort((a, b) => b.updatedAt - a.updatedAt)
	);

	const currentModelName = $derived(
		modelOptions.find((model) => model.id === selectedModelId)?.name ?? selectedModelId
	);

	const paperSourceName = $derived(
		collectionId
			? (notebooks.find((item) => item.id === collectionId)?.name ?? '当前笔记本')
			: notebooksLoading
				? '正在读取笔记本…'
				: notebooks.length > 0
					? '全部笔记本'
					: '未绑定知识库'
	);

	const paperTask = $derived<PaperTask>({
		title: paperTitle,
		keywords: paperKeywords,
		section: paperSection,
		context: paperContext
	});

	const attachedPaperNotebookIds = $derived(
		assistMode === 'paper'
			? Object.values(paperContext.attachedNotes ?? {})
					.flatMap((notes) => notes ?? [])
					.map((note) => note.notebookId)
					.filter(Boolean)
			: []
	);

	const pageTitle = $derived.by(() => {
		if (!userSettings.showChatTitleInTab) {
			return '答疑智能体 | TAgent';
		}
		const chatTitle = chats.find((c) => c.id === activeChatId)?.title;
		return chatTitle || (assistMode === 'paper' ? '论文助写' : '课程答疑');
	});

	const lastUserMessage = $derived(
		[...messages].reverse().find((m) => m.role === 'user')?.content ?? ''
	);

	const selectedFolderName = $derived(
		folders.find((folder) => folder.id === selectedFolderId)?.name ?? ''
	);

	const selectedFolder = $derived(folders.find((folder) => folder.id === selectedFolderId) ?? null);

	const effectiveBackgroundUrl = $derived(
		selectedFolder?.backgroundImageUrl || userSettings.backgroundImageUrl
	);

	const inputKnowledgeOptions = $derived(
		collections.map((item) => ({
			id: item.id,
			name: item.name,
			description: item.description,
			files: item.files.map((f) => ({ id: f.id, name: f.title }))
		}))
	);

	const inputNoteOptions = $derived(
		collections.flatMap((nb) =>
			nb.files.filter((f) => f.kind === 'note').map((f) => ({ id: f.id, name: f.title }))
		)
	);

	const inputChatOptions = $derived(
		chats
			.filter((c) => !c.archived && c.id !== activeChatId)
			.map((c) => ({ id: c.id, name: c.title }))
	);

	const toast = (message: string, ms = 2800) => {
		saveToast = message;
		window.setTimeout(() => {
			if (saveToast === message) saveToast = '';
		}, ms);
	};

	const matchShortcut = (event: KeyboardEvent, keys: string[]) => {
		const normalized = keys.map((k) => k.toLowerCase());
		const needCtrl = normalized.includes('ctrl') || normalized.includes('mod');
		const needShift = normalized.includes('shift');
		const needAlt = normalized.includes('alt');
		const mainKeys = normalized.filter((k) => !['ctrl', 'shift', 'alt', 'mod'].includes(k));

		if (needShift !== event.shiftKey) return false;
		if (needCtrl !== (event.ctrlKey || event.metaKey)) return false;
		if (needAlt !== event.altKey) return false;

		const pressed = event.key.toLowerCase();
		const code = event.code.toLowerCase();

		return mainKeys.some((key) => {
			if (key === 'escape') return pressed === 'escape';
			if (key === 'enter') return pressed === 'enter';
			if (key === 'tab') return pressed === 'tab';
			if (key === 'arrowup') return pressed === 'arrowup';
			if (key === 'backspace' || key === 'delete') {
				return pressed === 'backspace' || pressed === 'delete';
			}
			if (key === 'quote' || key === "'") {
				return pressed === "'" || code === 'quote';
			}
			if (key === 'period' || key === '.') {
				return pressed === '.' || code === 'period';
			}
			if (key === 'slash' || key === '/') {
				return pressed === '/' || code === 'slash';
			}
			if (key === 'semicolon' || key === ';') {
				return pressed === ';' || code === 'semicolon';
			}
			return pressed === key || code === `key${key}` || code === `digit${key}`;
		});
	};

	const deleteActiveChat = () => {
		if (isTemporarySession()) {
			temporaryChat = false;
			activeChatId = null;
			messages = [];
			prompt = '';
			syncUrl();
			toast('已删除临时对话');
			return;
		}
		if (!activeChatId) {
			toast('当前没有可删除的对话');
			return;
		}
		const id = activeChatId;
		chats = chats.filter((chat) => chat.id !== id);
		activeChatId = null;
		messages = [];
		prompt = '';
		persistChats(null);
		syncUrl();
		toast('已删除对话');
	};

	const copyLastResponse = async () => {
		const last = [...messages].reverse().find((m) => m.role === 'assistant' && !m.streaming);
		if (!last?.content) {
			toast('没有可复制的回答');
			return;
		}
		try {
			await navigator.clipboard.writeText(last.content);
			toast('已复制最后一个回答');
		} catch {
			toast('复制失败');
		}
	};

	const copyLastCodeBlock = async () => {
		const last = [...messages].reverse().find((m) => m.role === 'assistant' && !m.streaming);
		const match = last?.content?.match(/```[\w-]*\n([\s\S]*?)```/);
		if (!match?.[1]) {
			toast('没有可复制的代码块');
			return;
		}
		try {
			await navigator.clipboard.writeText(match[1]);
			toast('已复制最后一个代码块');
		} catch {
			toast('复制失败');
		}
	};

	const regenerateLastResponse = () => {
		const last = [...messages].reverse().find((m) => m.role === 'assistant' && !m.streaming);
		if (!last) {
			toast('没有可重新生成的回答');
			return;
		}
		regenerateResponse(last.id);
	};

	const toggleDictation = () => {
		dictationEnabled = !dictationEnabled;
		toast(dictationEnabled ? '听写模式已开启（需浏览器语音权限）' : '听写模式已关闭');
		if (!dictationEnabled) return;
		const SpeechRecognition =
			(window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
		if (!SpeechRecognition) {
			toast('当前浏览器不支持语音听写');
			dictationEnabled = false;
			return;
		}
		try {
			const recognition = new SpeechRecognition();
			recognition.lang = 'zh-CN';
			recognition.interimResults = false;
			recognition.onresult = (event: any) => {
				const text = event.results?.[0]?.[0]?.transcript ?? '';
				if (text) {
					prompt = `${prompt}${prompt ? ' ' : ''}${text}`;
					document.getElementById('chat-input')?.focus();
				}
			};
			recognition.onerror = () => {
				dictationEnabled = false;
			};
			recognition.onend = () => {
				dictationEnabled = false;
			};
			recognition.start();
		} catch {
			dictationEnabled = false;
			toast('无法启动听写');
		}
	};

	const buildFollowUps = (question: string, _answer: string): string[] => {
		const base = question.replace(/\s+/g, ' ').slice(0, 24);
		return [`请更详细地解释「${base}」`, '用例子说明一下', '相关还有哪些知识点？'].filter(Boolean);
	};

	const buildTags = (question: string): string[] => {
		const words = question
			.replace(/[^\u4e00-\u9fa5a-zA-Z0-9\s]/g, ' ')
			.split(/\s+/)
			.filter((w) => w.length >= 2)
			.slice(0, 3);
		return words.length ? words : ['答疑'];
	};

	onMount(() => {
		userSettings = loadUserSettings();
		const sidebarAction = $page.url.searchParams.get('sidebar-action');
		settingsOpen = sidebarAction === 'settings';
		archivedOpen = sidebarAction === 'archived';
		shortcutsOpen = sidebarAction === 'shortcuts';
		folders = loadQaFolders();
		applyTheme(userSettings.theme);
		applyTextScale(userSettings.textScale);
		applyHighContrast(userSettings.highContrastMode);
		if (userSettings.temporaryChatByDefault && !$page.url.searchParams.has('temporary-chat')) {
			temporaryChat = true;
		}
		if (userSettings.system || Object.keys(userSettings.params ?? {}).length) {
			chatControls = {
				...chatControls,
				system: userSettings.system || chatControls.system,
				...userSettings.params
			};
		}

		const stored = loadQaChats();
		chats = stored.chats;
		if (!temporaryChat) {
			// 仅当 URL 显式带 chat= 时恢复；从智能体入口进入应是全新空对话画面
			const urlChat = $page.url.searchParams.get('chat');
			const requestedMode = $page.url.searchParams.has('mode') ? assistMode : null;
			const restoreId =
				urlChat &&
				stored.chats.some(
					(chat) =>
						chat.id === urlChat &&
						(requestedMode === null || (chat.mode ?? 'qa') === requestedMode)
				)
					? urlChat
					: null;
			if (restoreId) {
				const chat = stored.chats.find((item) => item.id === restoreId);
				activeChatId = restoreId;
				messages = restoreChatMessages(chat);
				if (!$page.url.searchParams.has('mode') && chat?.mode) {
					assistMode = chat.mode;
				}
				if (chat?.paperTask && !$page.url.searchParams.has('paper_title')) {
					paperTitle = chat.paperTask.title;
					paperKeywords = chat.paperTask.keywords;
					paperSection = chat.paperTask.section;
				}
				if (chat?.paperTask?.context) {
					paperContext = { ...DEFAULT_PAPER_CONTEXT, ...chat.paperTask.context };
				}
				if (!collectionId && chat?.collectionId) {
					collectionId = chat.collectionId;
				}
				if (chat?.folderId) {
					selectedFolderId = chat.folderId;
				}
			} else {
				activeChatId = null;
				messages = [];
				persistChats(null);
			}
		} else {
			activeChatId = null;
			messages = [];
			persistChats(null);
		}

		void getAgentModels()
			.then((list) => {
				modelOptions = list.data.map((model) => ({
					id: model.id,
					name: model.name || model.id
				}));
				const ids = modelOptions.map((model) => model.id);
				if (ids.length > 0 && !ids.includes(selectedModelId)) {
					selectedModelId = ids[0];
				}
			})
			.catch(() => {
				// basic-agent 没起来。留空列表，让顶栏显示"选择模型"而不是抛未捕获异常。
				modelOptions = [];
				selectedModelId = '';
			});
		void listNotebooks()
			.then((items) => {
				notebooks = items;
				if (collectionId && !items.some((item) => item.id === collectionId)) {
					collectionId = '';
				}
			})
			.catch(() => {
				notebooks = [];
			})
			.finally(() => {
				notebooksLoading = false;
			});
		void listNotebookKnowledge()
			.then((items) => {
				collections = items;
			})
			.catch(() => {
				collections = [];
			});

		if (userSettings.showUpdateToast) {
			const key = 'tagentnote.update.toast.seen';
			if (!localStorage.getItem(key)) {
				saveToast = '已同步最新界面设置';
				localStorage.setItem(key, '1');
				window.setTimeout(() => {
					saveToast = '';
				}, 3200);
			}
		}
		if (userSettings.showChangelog) {
			const key = 'tagentnote.changelog.seen';
			if (!localStorage.getItem(key)) {
				changelogOpen = true;
				localStorage.setItem(key, '1');
			}
		}

		const onGlobalKeydown = (event: KeyboardEvent) => {
			const target = event.target as HTMLElement | null;
			const tag = target?.tagName?.toLowerCase() ?? '';
			const inEditable =
				tag === 'input' || tag === 'textarea' || Boolean(target?.isContentEditable);

			if (matchShortcut(event, ['mod', 'slash'])) {
				event.preventDefault();
				shortcutsOpen = !shortcutsOpen;
				return;
			}

			if (matchShortcut(event, ['mod', 'period'])) {
				event.preventDefault();
				settingsOpen = !settingsOpen;
				return;
			}

			if (matchShortcut(event, ['mod', 'shift', 's'])) {
				event.preventDefault();
				sidebarOpen = !sidebarOpen;
				return;
			}

			if (matchShortcut(event, ['mod', 'k'])) {
				event.preventDefault();
				if (!sidebarOpen) sidebarOpen = true;
				queueMicrotask(() => {
					const btn = document.getElementById('sidebar-search-button');
					btn?.click();
				});
				return;
			}

			if (matchShortcut(event, ['mod', 'shift', 'o'])) {
				event.preventDefault();
				createEmptyChat();
				return;
			}

			if (
				matchShortcut(event, ['mod', 'shift', 'quote']) ||
				matchShortcut(event, ['mod', 'shift', "'"])
			) {
				event.preventDefault();
				toggleTemporaryChat();
				return;
			}

			if (
				matchShortcut(event, ['mod', 'shift', 'backspace']) ||
				matchShortcut(event, ['mod', 'shift', 'delete'])
			) {
				event.preventDefault();
				deleteActiveChat();
				return;
			}

			if (matchShortcut(event, ['mod', 'shift', 'm'])) {
				event.preventDefault();
				document.getElementById('model-selector-0-button')?.click();
				return;
			}

			if (matchShortcut(event, ['mod', 'shift', 'l'])) {
				event.preventDefault();
				toggleDictation();
				return;
			}

			if (matchShortcut(event, ['mod', 'shift', 'c'])) {
				event.preventDefault();
				void copyLastResponse();
				return;
			}

			if (
				matchShortcut(event, ['mod', 'shift', 'semicolon']) ||
				matchShortcut(event, ['mod', 'shift', ';'])
			) {
				event.preventDefault();
				void copyLastCodeBlock();
				return;
			}

			if (matchShortcut(event, ['mod', 'r']) && document.activeElement?.id === 'chat-input') {
				event.preventDefault();
				regenerateLastResponse();
				return;
			}

			if (matchShortcut(event, ['shift', 'escape'])) {
				event.preventDefault();
				document.getElementById('chat-input')?.focus();
				return;
			}

			if (matchShortcut(event, ['mod', 'shift', 'v']) && inEditable) {
				// 交给输入框粘贴逻辑：不转成文件；这里主动插入剪贴板纯文本
				event.preventDefault();
				void navigator.clipboard
					.readText()
					.then((text) => {
						prompt = `${prompt}${text}`;
						document.getElementById('chat-input')?.focus();
					})
					.catch(() => {
						toast('无法读取剪贴板');
					});
				return;
			}

			if (event.key === 'Escape') {
				if (settingsOpen || shortcutsOpen || changelogOpen || archivedOpen || saveOpen || dataOpen) {
					event.preventDefault();
					settingsOpen = false;
					shortcutsOpen = false;
					changelogOpen = false;
					archivedOpen = false;
					saveOpen = false;
					dataOpen = false;
					return;
				}
			}
		};

		document.addEventListener('keydown', onGlobalKeydown);
		return () => {
			document.removeEventListener('keydown', onGlobalKeydown);
		};
	});

	const scrollToBottom = async () => {
		await tick();

		if (messagesContainer) {
			messagesContainer.scrollTop = messagesContainer.scrollHeight;
		}
	};

	const finishStreamingMessages = () => {
		messages = messages.map((message) =>
			message.streaming ? { ...message, streaming: false } : message
		);
	};

	const bumpGeneration = () => {
		generationSeq += 1;
		abortController?.abort();
		abortController = null;
		return generationSeq;
	};

	const persistChats = (nextActive = activeChatId) => {
		saveQaChats(chats, nextActive);
	};

	const cloneMessages = (list: MockMessage[]) =>
		list.map((message) => ({
			...message,
			citations: message.citations?.map((citation) => ({ ...citation })),
			followUps: message.followUps?.slice(),
			tags: message.tags?.slice(),
			streaming: false
		}));

	const restoreChatMessages = (chat: QaChat | undefined) => {
		const task = chat?.paperTask ?? paperTask;

		return cloneMessages(chat?.messages ?? []).map((message) => {
			if (chat?.mode !== 'paper' || message.role !== 'user' || message.requestContent) {
				return message;
			}

			const intent = paperIntentFromPrompt(message.content);

			return intent
				? {
						...message,
						content: paperIntentDisplay(intent, task.section),
						requestContent: message.content
					}
				: message;
		});
	};

	const isTemporarySession = () =>
		temporaryChat || (typeof activeChatId === 'string' && activeChatId.startsWith('local:'));

	const commitActive = (nextMessages = messages, title?: string) => {
		const id = activeChatId;

		if (!id || isTemporarySession()) {
			return;
		}

		const snapshot = cloneMessages(nextMessages);
		chats = chats.map((chat) =>
			chat.id === id
				? {
						...chat,
						title: title || chat.title,
						updatedAt: Date.now(),
						collectionId: collectionId || chat.collectionId,
						mode: assistMode,
						paperTask: assistMode === 'paper' ? { ...paperTask } : chat.paperTask,
						messages: snapshot
					}
				: chat
		);
		persistChats(id);
	};

	const syncUrl = () => {
		const params = new URLSearchParams();

		if (selectedModelId) {
			params.set('model', selectedModelId);
		}
		if (collectionId) {
			params.set('notebook', collectionId);
		}
		if (assistMode === 'paper') {
			params.set('mode', 'paper');
			if (paperTitle.trim()) {
				params.set('paper_title', paperTitle.trim());
			}
			if (paperKeywords.trim()) {
				params.set('paper_keywords', paperKeywords.trim());
			}
			params.set('paper_section', paperSection);
		}
		if (temporaryChat) {
			params.set('temporary-chat', 'true');
		} else if (activeChatId && !activeChatId.startsWith('local:')) {
			params.set('chat', activeChatId);
		}

		const search = params.toString();
		const next = search ? `/qa?${search}` : '/qa';
		const current = `${$page.url.pathname}${$page.url.search}`;

		if (current === next) {
			return;
		}

		void goto(next, {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	};

	const setAssistMode = (mode: AssistMode) => {
		if (assistMode === mode) {
			return;
		}

		bumpGeneration();
		finishStreamingMessages();
		generating = false;
		commitActive();
		// 切换模式即进入另一套会话空间，避免把论文内容继续留在课程答疑里。
		activeChatId = null;
		messages = [];
		prompt = '';
		selectedFolderId = null;
		assistMode = mode;
		if (mode === 'paper' && !paperSection) {
			paperSection = DEFAULT_PAPER_TASK.section;
		}
		persistChats(null);
		syncUrl();
	};

	const handlePaperTaskChange = (next: PaperTask) => {
		paperTitle = next.title;
		paperKeywords = next.keywords;
		paperSection = next.section;
		paperContext = { ...DEFAULT_PAPER_CONTEXT, ...(next.context ?? {}) };
		if (assistMode === 'paper') {
			if (paperTaskSyncTimer !== null) {
				window.clearTimeout(paperTaskSyncTimer);
			}
			paperTaskSyncTimer = window.setTimeout(() => {
				commitActive();
				syncUrl();
				paperTaskSyncTimer = null;
			}, 250);
		}
	};

	const runPaperIntent = (intent: PaperIntent) => {
		if (assistMode !== 'paper') {
			return;
		}
		submitPrompt(
			buildPaperPrompt(intent, paperTask),
			paperIntentDisplay(intent, paperTask.section)
		);
	};

	const returnToSelect = () => {
		bumpGeneration();
		generating = false;
		commitActive();
		void goto('/agent-select');
	};

	const openSettings = () => {
		settingsOpen = true;
	};

	const openDataPanel = () => {
		dataOpen = true;
	};

	const handleSettingsChange = (next: UserSettings) => {
		userSettings = next;
		saveUserSettings(next);
		applyTheme(next.theme);
		applyTextScale(next.textScale);
		applyHighContrast(next.highContrastMode);
		if (next.showChatTitleInTab && typeof document !== 'undefined') {
			const title =
				chats.find((c) => c.id === activeChatId)?.title ||
				(assistMode === 'paper' ? '论文助写' : '课程答疑');
			document.title = title;
		}
		chatControls = {
			...chatControls,
			system: next.system ?? '',
			...((next.params as ChatControlParams) ?? {})
		};
		saveChatControls(chatControls);
	};

	const exportAllChats = () => {
		const blob = new Blob([JSON.stringify(chats, null, 2)], { type: 'application/json' });
		const href = URL.createObjectURL(blob);
		const anchor = document.createElement('a');
		anchor.href = href;
		anchor.download = `tagentnote-chats-${Date.now()}.json`;
		anchor.click();
		URL.revokeObjectURL(href);
		saveToast = '已导出对话';
		window.setTimeout(() => {
			saveToast = '';
		}, 2800);
	};

	const importChatsFromFile = async (file: File) => {
		try {
			const text = await file.text();
			const parsed = JSON.parse(text) as QaChat[] | { chats?: QaChat[] };
			const incoming = Array.isArray(parsed) ? parsed : (parsed.chats ?? []);
			if (!Array.isArray(incoming) || incoming.length === 0) {
				saveToast = '导入文件里没有可用对话';
				window.setTimeout(() => {
					saveToast = '';
				}, 2800);
				return;
			}
			const merged = [
				...incoming.map((chat) => ({ ...chat, archived: chat.archived ?? false })),
				...chats
			];
			const seen = new Set<string>();
			chats = merged.filter((chat) => {
				if (!chat?.id || seen.has(chat.id)) return false;
				seen.add(chat.id);
				return true;
			});
			persistChats();
			saveToast = `已导入 ${incoming.length} 条对话`;
		} catch {
			saveToast = '导入失败，请检查 JSON 文件';
		}
		window.setTimeout(() => {
			saveToast = '';
		}, 3200);
	};

	const archiveAllChats = () => {
		chats = chats.map((chat) => ({ ...chat, archived: true }));
		activeChatId = null;
		messages = [];
		persistChats(null);
		syncUrl();
		saveToast = '已归档全部对话';
		window.setTimeout(() => {
			saveToast = '';
		}, 2800);
	};

	const deleteAllChats = () => {
		chats = [];
		activeChatId = null;
		messages = [];
		persistChats(null);
		syncUrl();
		saveToast = '已删除全部对话';
		window.setTimeout(() => {
			saveToast = '';
		}, 2800);
	};

	const openArchivedChats = () => {
		archivedOpen = true;
	};

	const openShortcuts = () => {
		shortcutsOpen = true;
	};

	const openPlayground = () => {
		void goto('/playground');
	};

	const openAdmin = () => {
		void goto('/admin');
	};

	const signOut = () => {
		bumpGeneration();
		generating = false;
		commitActive();
		void goto('/welcome');
	};

	const unarchiveChat = (chatId: string) => {
		chats = chats.map((chat) => (chat.id === chatId ? { ...chat, archived: false } : chat));
		persistChats();
		saveToast = '已取消归档';
		window.setTimeout(() => {
			saveToast = '';
		}, 2800);
	};

	const openArchivedChat = (chatId: string) => {
		chats = chats.map((chat) => (chat.id === chatId ? { ...chat, archived: false } : chat));
		persistChats();
		archivedOpen = false;
		selectChat(chatId);
	};

	const createEmptyChat = () => {
		bumpGeneration();
		finishStreamingMessages();
		commitActive();
		temporaryChat = false;
		activeChatId = null;
		selectedFolderId = null;
		messages = [];
		messageQueue = [];
		prompt = '';
		generating = false;
		controlsOpen = false;
		persistChats(null);
		syncUrl();
		queueMicrotask(() => {
			document.getElementById('chat-input')?.focus();
		});
	};

	const persistFolders = (next = folders) => {
		folders = next;
		saveQaFolders(next);
	};

	const handleCreateFolder = (value: FolderFormValue, parentId: string | null = null) => {
		const folder = createQaFolder(value.name, parentId, {
			systemPrompt: value.systemPrompt,
			backgroundImageUrl: value.backgroundImageUrl,
			knowledgeItems: value.knowledgeItems
		});
		persistFolders([folder, ...folders]);
		selectedFolderId = folder.id;
		toast(`已创建分组「${folder.name}」`);
	};

	const handleUpdateFolder = (folderId: string, value: FolderFormValue) => {
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
		toast('分组已更新');
	};

	const handleDeleteFolder = (folderId: string, deleteContents = true) => {
		const ids = collectFolderTreeIds(folders, folderId);
		persistFolders(folders.filter((folder) => !ids.has(folder.id)));
		if (deleteContents) {
			chats = chats.filter((chat) => !(chat.folderId && ids.has(chat.folderId)));
		} else {
			chats = chats.map((chat) =>
				chat.folderId && ids.has(chat.folderId) ? { ...chat, folderId: null } : chat
			);
		}
		persistChats();
		if (selectedFolderId && ids.has(selectedFolderId)) {
			selectedFolderId = null;
		}
		toast(deleteContents ? '分组及内容已删除' : '分组已删除，对话已移回列表');
	};

	const handleToggleFolderExpanded = (folderId: string) => {
		persistFolders(
			folders.map((folder) =>
				folder.id === folderId ? { ...folder, expanded: !(folder.expanded ?? true) } : folder
			)
		);
	};

	const handleMoveChatToFolder = (chatId: string, folderId: string | null) => {
		chats = chats.map((chat) =>
			chat.id === chatId ? { ...chat, folderId, updatedAt: Date.now() } : chat
		);
		persistChats();
		toast(folderId ? '已移至分组' : '已移出分组');
	};

	const handleMoveFolder = (folderId: string, parentId: string | null) => {
		if (wouldCreateCycle(folders, folderId, parentId)) {
			toast('无法将分组移入其子分组');
			return;
		}
		persistFolders(
			folders.map((folder) =>
				folder.id === folderId ? { ...folder, parentId, updatedAt: Date.now() } : folder
			)
		);
		toast('分组已移动');
	};

	const handleExportFolder = (folderId: string) => {
		const ids = collectFolderTreeIds(folders, folderId);
		const folder = folders.find((item) => item.id === folderId);
		const exported = {
			folder,
			folders: folders.filter((item) => ids.has(item.id)),
			chats: chats.filter((chat) => chat.folderId && ids.has(chat.folderId))
		};
		const blob = new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json' });
		const href = URL.createObjectURL(blob);
		const anchor = document.createElement('a');
		anchor.href = href;
		anchor.download = `folder-${folder?.name || 'export'}-${Date.now()}.json`;
		anchor.click();
		URL.revokeObjectURL(href);
		toast('分组已导出');
	};

	const handleSelectFolder = (folderId: string | null) => {
		selectedFolderId = folderId;
	};

	const selectChat = (chatId: string) => {
		bumpGeneration();
		if (activeChatId && activeChatId !== chatId && !isTemporarySession()) {
			commitActive();
		}
		temporaryChat = false;
		const chat = chats.find((item) => item.id === chatId);
		activeChatId = chatId;
		messages = restoreChatMessages(chat);
		if (chat?.mode) {
			assistMode = chat.mode;
		}
		if (chat?.paperTask) {
			paperTitle = chat.paperTask.title;
			paperKeywords = chat.paperTask.keywords;
			paperSection = chat.paperTask.section;
			paperContext = { ...DEFAULT_PAPER_CONTEXT, ...(chat.paperTask.context ?? {}) };
		}
		if (chat?.collectionId) {
			collectionId = chat.collectionId;
		}
		if (chat?.folderId) {
			selectedFolderId = chat.folderId;
		}
		prompt = '';
		generating = false;
		persistChats(chatId);
		syncUrl();
		void scrollToBottom();
	};

	const toggleTemporaryChat = () => {
		bumpGeneration();
		finishStreamingMessages();
		generating = false;

		if (temporaryChat) {
			temporaryChat = false;
			activeChatId = null;
			messages = [];
			prompt = '';
			persistChats(null);
		} else {
			commitActive();
			temporaryChat = true;
			activeChatId = null;
			messages = [];
			prompt = '';
			persistChats(null);
		}

		syncUrl();
	};

	const saveTemporaryChat = () => {
		if (!temporaryChat || messages.length === 0) {
			return;
		}

		const id = `chat-${Date.now()}`;
		const firstUser = messages.find((message) => message.role === 'user');
		const chat: QaChat = {
			id,
			title:
				assistMode === 'paper'
					? paperChatTitle(paperTask, clipTitle(firstUser?.content ?? '论文辅助'))
					: clipTitle(firstUser?.content ?? '临时对话'),
			updatedAt: Date.now(),
			collectionId,
			mode: assistMode,
			paperTask: assistMode === 'paper' ? { ...paperTask } : undefined,
			messages: cloneMessages(messages)
		};

		temporaryChat = false;
		activeChatId = id;
		chats = [chat, ...chats];
		persistChats(id);
		syncUrl();
		saveToast = '临时对话已保存到历史';
		window.setTimeout(() => {
			saveToast = '';
		}, 2800);
	};

	const openExam = () => {
		void goto(
			`/exam?model=${encodeURIComponent(selectedModelId)}&from=qa&topic=${encodeURIComponent(collectionId)}`
		);
	};

	const openNotes = () => {
		commitActive();
		const params = new URLSearchParams();
		params.set('from', 'qa');
		if (selectedModelId) params.set('model', selectedModelId);
		if (collectionId) {
			params.set('notebook', collectionId);
			params.set('collection', collectionId);
		}
		if (activeChatId) params.set('chat', activeChatId);
		void goto(`/notebook?${params.toString()}`);
	};

	const openWorkspace = () => {
		commitActive();
		const params = new URLSearchParams();
		if (selectedModelId) params.set('model', selectedModelId);
		if (activeChatId) params.set('chat', activeChatId);
		const search = params.toString();
		void goto(search ? `/workspace/models?${search}` : '/workspace/models');
	};

	const chatPlainText = () =>
		messages
			.map((message) => `### ${message.role.toUpperCase()}\n${message.content}`)
			.join('\n\n')
			.trim();

	const shareActiveChat = async () => {
		if (isTemporarySession()) {
			saveToast = '临时对话不能分享，请先保存';
			window.setTimeout(() => {
				saveToast = '';
			}, 2800);
			return;
		}

		const url = window.location.href;
		try {
			await navigator.clipboard.writeText(url);
			saveToast = '已复制分享链接';
		} catch {
			saveToast = '复制链接失败';
		}
		window.setTimeout(() => {
			saveToast = '';
		}, 2800);
	};

	const downloadActiveChat = () => {
		const text = chatPlainText();
		if (!text) {
			saveToast = '当前没有可下载的对话';
			window.setTimeout(() => {
				saveToast = '';
			}, 2800);
			return;
		}

		const title =
			chats.find((chat) => chat.id === activeChatId)?.title?.replace(/[\\/:*?"<>|]/g, '_') ||
			'chat';
		const mime = userSettings.stylizedPdfExport
			? 'text/markdown;charset=utf-8'
			: 'text/plain;charset=utf-8';
		const ext = userSettings.stylizedPdfExport ? 'md' : 'txt';
		const body = userSettings.stylizedPdfExport
			? `# ${title}\n\n${text
					.split('\n')
					.map((line) => line)
					.join('\n\n')}`
			: text;
		const blob = new Blob([body], { type: mime });
		const href = URL.createObjectURL(blob);
		const anchor = document.createElement('a');
		anchor.href = href;
		anchor.download = `${title}.${ext}`;
		anchor.click();
		URL.revokeObjectURL(href);
	};

	const copyActiveChat = async () => {
		const text = chatPlainText();
		if (!text) {
			saveToast = '当前没有可复制的对话';
			window.setTimeout(() => {
				saveToast = '';
			}, 2800);
			return;
		}

		try {
			await navigator.clipboard.writeText(text);
			saveToast = '已复制对话内容';
		} catch {
			saveToast = '复制失败';
		}
		window.setTimeout(() => {
			saveToast = '';
		}, 2800);
	};

	const archiveActiveChat = () => {
		if (isTemporarySession()) {
			temporaryChat = false;
			activeChatId = null;
			messages = [];
			prompt = '';
			syncUrl();
			saveToast = '已丢弃临时对话';
			window.setTimeout(() => {
				saveToast = '';
			}, 2800);
			return;
		}

		if (!activeChatId) {
			return;
		}

		const id = activeChatId;
		chats = chats.map((chat) => (chat.id === id ? { ...chat, archived: true } : chat));
		persistChats(null);
		activeChatId = null;
		messages = [];
		prompt = '';
		syncUrl();
		saveToast = '对话已归档';
		window.setTimeout(() => {
			saveToast = '';
		}, 2800);
	};

	const addTagToActiveChat = (tag: string) => {
		if (isTemporarySession() || !activeChatId) {
			saveToast = isTemporarySession() ? '临时对话请先保存再添加标签' : '请先开始对话';
			window.setTimeout(() => {
				saveToast = '';
			}, 2800);
			return;
		}

		chats = chats.map((chat) => {
			if (chat.id !== activeChatId) {
				return chat;
			}
			const tags = chat.tags ?? [];
			if (tags.includes(tag)) {
				return chat;
			}
			return { ...chat, tags: [...tags, tag], updatedAt: Date.now() };
		});
		persistChats();
		saveToast = `已添加标签「${tag}」`;
		window.setTimeout(() => {
			saveToast = '';
		}, 2800);
	};

	const clipTitle = (text: string) => {
		const trimmed = text.trim().replace(/\s+/g, ' ');

		return trimmed.length > 40 ? `${trimmed.slice(0, 40)}…` : trimmed || '答疑摘录';
	};

	const openSaveToNotebook = (messageId: string) => {
		const index = messages.findIndex((message) => message.id === messageId);
		const assistant = index >= 0 ? messages[index] : null;

		if (!assistant || assistant.role !== 'assistant') {
			return;
		}

		let question = '';

		for (let i = index - 1; i >= 0; i -= 1) {
			if (messages[i].role === 'user') {
				question = messages[i].content;
				break;
			}
		}

		const citations = (assistant.citations ?? [])
			.map((citation) => {
				const locator = citation.locator ? ` · ${citation.locator}` : '';
				return `- ${citation.collectionName} · ${citation.title}${locator}`;
			})
			.join('\n');

		if (assistMode === 'paper') {
			saveTitle = `${paperChatTitle(paperTask, '论文草稿')}·${paperTask.section}`;
			saveContent = [
				`# ${paperTask.title.trim() || '课程论文草稿'}`,
				'',
				`> 当前章节：${paperTask.section}`,
				paperTask.keywords.trim() ? `> 关键词：${paperTask.keywords.trim()}` : '',
				'',
				`## ${paperTask.section}`,
				'',
				assistant.content,
				citations ? `\n## 参考资料\n\n${citations}` : '',
				'',
				'<!-- 由 TAgentNote 论文辅助模式生成，请结合课程资料和实验数据继续修改。 -->'
			]
				.filter(Boolean)
				.join('\n')
				.trim();
		} else {
			saveTitle = clipTitle(question);
			saveContent = [
				'## 问',
				'',
				question || '（无对应提问）',
				'',
				'## 答',
				'',
				assistant.content,
				citations ? `\n## 引用\n\n${citations}` : ''
			]
				.join('\n')
				.trim();
		}
		saveOpen = true;
	};

	const ask = async (question: string, seq: number) => {
		const controller = new AbortController();
		abortController = controller;
		const assistantId = `assistant-${Date.now()}`;
		let created = false;
		const searchController = new AbortController();
		const searchTimer = window.setTimeout(() => searchController.abort(), 4000);
		const citationQuery =
			assistMode === 'paper'
				? [
						paperTask.title,
						paperTask.keywords,
						paperTask.section,
						...Object.values(paperTask.context ?? {})
					]
						.filter(Boolean)
						.join(' ')
				: question;
		const hitsPromise = searchKnowledge(citationQuery, {
			limit: 8,
			signal: searchController.signal
		})
			.catch(() => [])
			.finally(() => window.clearTimeout(searchTimer));

		const writeDelta = (content: string, streaming = true) => {
			if (seq !== generationSeq) {
				return;
			}

			if (!created) {
				messages = [
					...messages,
					{
						id: assistantId,
						role: 'assistant',
						model: selectedModelId,
						content,
						streaming
					}
				];
				created = true;
			} else {
				messages = messages.map((message) =>
					message.id === assistantId ? { ...message, content, streaming } : message
				);
			}

			void scrollToBottom();
		};

		try {
			const folderPrompt = selectedFolder?.systemPrompt?.trim() ?? '';
			const baseOptions = toAgentOptions(chatControls);
			const mergedSystem = [folderPrompt, baseOptions.system].filter(Boolean).join('\n\n');
			const folderNotebookIds = (selectedFolder?.knowledgeItems ?? [])
				.filter((item) => item.type === 'collection')
				.map((item) => item.id);
			const notebookIds = Array.from(
				new Set([
					...folderNotebookIds,
					...(collectionId ? [collectionId] : []),
					...attachedPaperNotebookIds
				])
			);

			const result = await streamAgentChat(
				question,
				selectedModelId,
				writeDelta,
				controller.signal,
				{
					notebookIds,
					mode: assistMode,
					...baseOptions,
					...(mergedSystem ? { system: mergedSystem } : {})
				}
			);

			if (seq !== generationSeq) {
				return;
			}

			if (!result.content.trim()) {
				writeDelta('没有生成回答，请重试。', false);
			} else {
				writeDelta(result.content, false);
				if (result.retrievedContext || (result.citations && result.citations.length > 0)) {
					searchController.abort();
				}
				const notebook = notebooks.find((item) => item.id === collectionId) ?? null;
				const hits = await hitsPromise;
				let citations = buildQaCitations({
					agentCitations: result.citations,
					retrievedContext: result.retrievedContext,
					searchHits: hits,
					question: citationQuery,
					answer: result.content,
					collections,
					notebook
				});
				citations = await enrichCitationsWithPages(citations, question, (fileId) =>
					getSourceText(fileId, controller.signal)
				);

				if (seq !== generationSeq) {
					return;
				}

				messages = messages.map((message) =>
					message.id === assistantId
						? {
								...message,
								model: result.model || selectedModelId,
								citations,
								followUps: userSettings.autoFollowUps
									? buildFollowUps(question, result.content)
									: undefined,
								tags: userSettings.autoTags ? buildTags(question) : undefined
							}
						: message
				);
			}

			generating = false;
			commitActive();
			void scrollToBottom();

			const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
			if (lastAssistant?.content) {
				if (userSettings.responseAutoCopy) {
					void navigator.clipboard.writeText(lastAssistant.content).catch(() => {});
				}
				if (userSettings.notificationSound) {
					const hidden = typeof document !== 'undefined' && document.hidden;
					if (userSettings.notificationSoundAlways || hidden) {
						playNotificationSound();
					}
				}
				if (
					userSettings.notificationEnabled &&
					typeof Notification !== 'undefined' &&
					Notification.permission === 'granted'
				) {
					try {
						new Notification('TAgentNote', { body: '回复已生成' });
					} catch {
						// ignore
					}
				}
			}

			if (messageQueue.length > 0) {
				const next = messageQueue[0];
				messageQueue = messageQueue.slice(1);
				void tick().then(() => submitPrompt(next.requestContent, next.displayContent));
			}
		} finally {
			searchController.abort();
			if (abortController === controller) {
				abortController = null;
			}
		}
	};

	const submitPrompt = (content: string, displayContent = content) => {
		const trimmedContent = content.trim();
		const trimmedDisplayContent = displayContent.trim() || trimmedContent;

		if (!trimmedContent) {
			return;
		}

		if (generating) {
			if (!userSettings.enableMessageQueue) {
				return;
			}
			messageQueue = [
				...messageQueue,
				{ requestContent: trimmedContent, displayContent: trimmedDisplayContent }
			];
			prompt = '';
			saveToast = `已加入队列（${messageQueue.length}）`;
			window.setTimeout(() => {
				saveToast = '';
			}, 1800);
			return;
		}

		if (userSettings.hapticFeedback && typeof navigator !== 'undefined' && 'vibrate' in navigator) {
			try {
				navigator.vibrate?.(12);
			} catch {
				// ignore
			}
		}

		const seq = bumpGeneration();
		const userMessage: MockMessage = {
			id: `user-${Date.now()}`,
			role: 'user',
			content: trimmedDisplayContent,
			requestContent: trimmedContent
		};

		messages = [...messages, userMessage];
		prompt = '';
		generating = true;

		if (!activeChatId) {
			if (temporaryChat) {
				activeChatId = `local:${Date.now()}`;
				syncUrl();
			} else {
				activeChatId = `chat-${Date.now()}`;
				chats = [
					{
						id: activeChatId,
						title:
							assistMode === 'paper'
								? paperChatTitle(
										paperTask,
										userSettings.titleAutoGenerate ? clipTitle(trimmedContent) : '论文辅助'
									)
								: userSettings.titleAutoGenerate
									? clipTitle(trimmedContent)
									: '新对话',
						updatedAt: Date.now(),
						collectionId,
						folderId: selectedFolderId,
						mode: assistMode,
						paperTask: assistMode === 'paper' ? { ...paperTask } : undefined,
						messages: [userMessage]
					},
					...chats
				];
				persistChats(activeChatId);
				syncUrl();
			}
		} else if (!isTemporarySession()) {
			commitActive(messages);
		}

		void scrollToBottom();
		void ask(trimmedContent, seq).catch((error: unknown) => {
			if (seq !== generationSeq || (error instanceof DOMException && error.name === 'AbortError')) {
				return;
			}

			messages = [
				...messages,
				{
					id: `assistant-${Date.now()}`,
					role: 'assistant',
					model: selectedModelId,
					content: error instanceof Error ? error.message : '回答生成失败，请重试。'
				}
			];
			generating = false;
			commitActive();
		});
	};

	const stopResponse = () => {
		bumpGeneration();
		finishStreamingMessages();
		generating = false;
		commitActive();
	};

	const regenerateResponse = (messageId: string) => {
		if (generating) {
			return;
		}

		const messageIndex = messages.findIndex((message) => message.id === messageId);

		if (messageIndex < 0) {
			return;
		}

		let lastUserQuestion = '';

		for (let index = messageIndex - 1; index >= 0; index -= 1) {
			if (messages[index].role === 'user') {
				lastUserQuestion = messages[index].requestContent || messages[index].content;
				break;
			}
		}

		if (!lastUserQuestion) {
			return;
		}

		const seq = bumpGeneration();
		messages = messages.filter((message) => message.id !== messageId);
		generating = true;
		commitActive(messages);
		void scrollToBottom();
		void ask(lastUserQuestion, seq).catch((error: unknown) => {
			if (seq !== generationSeq || (error instanceof DOMException && error.name === 'AbortError')) {
				return;
			}

			generating = false;
			commitActive();
		});
	};

	const editMessage = (messageId: string, content: string) => {
		const next = content.trim();
		if (!next) {
			toast('内容不能为空');
			return;
		}
		messages = messages.map((message) =>
			message.id === messageId ? { ...message, content: next, streaming: false } : message
		);
		commitActive();
		toast('已保存编辑');
	};

	const continueResponse = (messageId: string) => {
		if (generating) {
			return;
		}

		const messageIndex = messages.findIndex((message) => message.id === messageId);
		if (messageIndex < 0) {
			return;
		}

		const target = messages[messageIndex];
		if (target.role !== 'assistant' || !target.content.trim()) {
			return;
		}

		let lastUserQuestion = '';
		for (let index = messageIndex - 1; index >= 0; index -= 1) {
			if (messages[index].role === 'user') {
				lastUserQuestion = messages[index].requestContent || messages[index].content;
				break;
			}
		}

		const seq = bumpGeneration();
		const existing = target.content;
		generating = true;
		messages = messages.map((message) =>
			message.id === messageId ? { ...message, streaming: true } : message
		);
		commitActive();
		void scrollToBottom();

		const controller = new AbortController();
		abortController = controller;

		const writeDelta = (delta: string) => {
			if (seq !== generationSeq) {
				return;
			}
			const joined = delta ? `${existing}\n${delta}` : existing;
			messages = messages.map((message) =>
				message.id === messageId ? { ...message, content: joined, streaming: true } : message
			);
			void scrollToBottom();
		};

		const continueLines: string[] =
			assistMode === 'paper'
				? [
						`请继续撰写论文的“${paperSection}”章节，不要切换到其他章节。`,
						`【论文任务】\n${paperTask.title || '未命名论文'}\n关键词：${paperTask.keywords || '未填写'}`,
						lastUserQuestion ? `【本次写作要求】\n${lastUserQuestion}` : '',
						`【已有章节内容】\n${existing}`,
						'【要求】从已有内容的断点继续，保持论文语气和 Markdown 结构，不要重复已经写过的段落；缺少数据时标记“待补充”。'
					]
				: [
						'请在不重复已有内容的前提下，继续完成下面的回答。',
						'',
						lastUserQuestion ? `【用户问题】\n${lastUserQuestion}` : '',
						`【已有回答】\n${existing}`,
						'',
						'【要求】直接从断点继续写，不要复述开头或重复已有段落。'
					];
		const continuePrompt = continueLines.filter(Boolean).join('\n');

		void (async () => {
			try {
				const folderPrompt = selectedFolder?.systemPrompt?.trim() ?? '';
				const baseOptions = toAgentOptions(chatControls);
				const mergedSystem = [folderPrompt, baseOptions.system].filter(Boolean).join('\n\n');
				const folderNotebookIds = (selectedFolder?.knowledgeItems ?? [])
					.filter((item) => item.type === 'collection')
					.map((item) => item.id);
				const notebookIds = Array.from(
					new Set([
						...folderNotebookIds,
						...(collectionId ? [collectionId] : []),
						...attachedPaperNotebookIds
					])
				);

				const result = await streamAgentChat(
					continuePrompt,
					selectedModelId,
					writeDelta,
					controller.signal,
					{
						notebookIds,
						mode: assistMode,
						...baseOptions,
						...(mergedSystem ? { system: mergedSystem } : {})
					}
				);

				if (seq !== generationSeq) {
					return;
				}

				const finalContent = result.content.trim()
					? `${existing}\n${result.content.trim()}`
					: existing;
				messages = messages.map((message) =>
					message.id === messageId
						? {
								...message,
								content: finalContent,
								streaming: false,
								model: result.model || selectedModelId
							}
						: message
				);
				generating = false;
				commitActive();
				void scrollToBottom();
			} catch (error: unknown) {
				if (
					seq !== generationSeq ||
					(error instanceof DOMException && error.name === 'AbortError')
				) {
					return;
				}
				messages = messages.map((message) =>
					message.id === messageId ? { ...message, streaming: false } : message
				);
				generating = false;
				commitActive();
				toast(error instanceof Error ? error.message : '继续生成失败，请重试');
			} finally {
				if (abortController === controller) {
					abortController = null;
				}
			}
		})();
	};

	onDestroy(() => {
		if (paperTaskSyncTimer !== null) {
			window.clearTimeout(paperTaskSyncTimer);
		}
		if (!isTemporarySession()) {
			commitActive();
		}
		bumpGeneration();
	});
</script>

<svelte:head>
	<title>{pageTitle}</title>
</svelte:head>

<main class="flex h-screen overflow-hidden bg-gray-900 text-white">
	{#if sidebarOpen}
		<MockSidebar
			{activeChatId}
			{selectedFolderId}
			chats={sidebarChats}
			searchChats={modeChats}
			{folders}
			modelId={selectedModelId}
			userName={userSettings.displayName}
			avatarText={userSettings.avatarText}
			statusEmoji={userSettings.statusEmoji}
			statusMessage={userSettings.statusMessage}
			activeNav="chats"
			onHome={returnToSelect}
			onNewChat={createEmptyChat}
			onSelectChat={selectChat}
			onSelectFolder={handleSelectFolder}
			onOpenNotes={openNotes}
			onOpenWorkspace={openWorkspace}
			onSettings={openSettings}
			onArchivedChats={openArchivedChats}
			onPlayground={openPlayground}
			onAdmin={openAdmin}
			onShortcuts={openShortcuts}
			onSignOut={signOut}
			onStatusSave={(value) => {
				userSettings = {
					...userSettings,
					statusEmoji: value.emoji,
					statusMessage: value.message
				};
				saveUserSettings(userSettings);
			}}
			onToast={toast}
			onCreateFolder={handleCreateFolder}
			onUpdateFolder={handleUpdateFolder}
			onDeleteFolder={handleDeleteFolder}
			onToggleFolderExpanded={handleToggleFolderExpanded}
			onMoveChatToFolder={handleMoveChatToFolder}
			onMoveFolder={handleMoveFolder}
			onExportFolder={handleExportFolder}
			knowledgeOptions={notebooks.map((item) => ({ id: item.id, name: item.name }))}
			onOpenWorkspaceKnowledge={() => {
				void goto('/workspace/knowledge');
			}}
			onClose={() => {
				sidebarOpen = false;
			}}
		/>
	{/if}

	<section class="relative flex min-h-0 min-w-0 flex-1 overflow-hidden bg-gray-900">
		<div class="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
			<MockNavbar
				{sidebarOpen}
				models={modelOptions}
				bind:selectedModelId
				{collectionId}
				{notebooks}
				{notebooksLoading}
				{assistMode}
				{temporaryChat}
				hasMessages={messages.length > 0}
				{controlsOpen}
				userName={userSettings.displayName}
				avatarText={userSettings.avatarText}
				onOpenSidebar={() => {
					sidebarOpen = true;
				}}
				onNewChat={createEmptyChat}
				onOpenExam={openExam}
				onHome={returnToSelect}
				onModelChange={syncUrl}
				onCollectionChange={(id) => {
					collectionId = id;
					syncUrl();
				}}
				onAssistModeChange={setAssistMode}
				onToggleTemporaryChat={toggleTemporaryChat}
				onSaveTemporaryChat={saveTemporaryChat}
				onToggleControls={() => {
					controlsOpen = !controlsOpen;
				}}
				onSettings={openSettings}
				onOpenData={openDataPanel}
				onArchivedChats={openArchivedChats}
				onPlayground={openPlayground}
				onAdmin={openAdmin}
				onShortcuts={openShortcuts}
				onSignOut={signOut}
				onShareChat={() => {
					void shareActiveChat();
				}}
				onDownloadChat={downloadActiveChat}
				onCopyChat={() => {
					void copyActiveChat();
				}}
				onArchiveChat={archiveActiveChat}
				onAddChatTag={addTagToActiveChat}
				folders={folders.map((f) => ({ id: f.id, name: f.name }))}
				onMoveChatToFolder={(folderId) => {
					if (!activeChatId || isTemporarySession()) {
						toast('当前没有可移动的对话');
						return;
					}
					handleMoveChatToFolder(activeChatId, folderId);
				}}
			/>

			{#if assistMode === 'paper'}
				<div
					class="min-h-0 max-h-[calc(100vh-4rem)] shrink-0 overflow-y-auto overscroll-contain border-b border-white/[0.06] bg-gray-900 px-3 py-2 md:px-5"
				>
					<PaperTaskCard
						bind:title={paperTitle}
						bind:keywords={paperKeywords}
						bind:section={paperSection}
						bind:context={paperContext}
						sourceName={paperSourceName}
						{collections}
						compact={messages.length > 0}
						onChange={handlePaperTaskChange}
						onIntent={runPaperIntent}
					/>
				</div>
			{/if}

			<div
				class="relative flex min-h-0 flex-1 flex-col overflow-hidden"
				dir={userSettings.chatDirection === 'auto'
					? undefined
					: (userSettings.chatDirection.toLowerCase() as 'ltr' | 'rtl')}
				style={effectiveBackgroundUrl
					? `background-image:url(${effectiveBackgroundUrl});background-size:cover;background-position:center;`
					: undefined}
			>
				{#if messages.length === 0}
					<div class="flex h-full min-h-0 w-full flex-col">
						{#if selectedFolderId && selectedFolderName}
							<div class="relative z-20 flex w-full justify-center pt-3">
								<div
									class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-gray-900/90 px-3 py-1 text-xs text-gray-300 backdrop-blur"
								>
									分组 · {selectedFolderName}
									<button
										type="button"
										class="text-gray-500 underline hover:text-gray-300"
										onclick={() => {
											selectedFolderId = null;
										}}
									>
										退出
									</button>
								</div>
							</div>
						{/if}
						<div class="flex min-h-0 w-full flex-1 items-center">
							<MockPlaceholder
								modelName={currentModelName}
								bind:prompt
								{generating}
								mode={assistMode}
								{temporaryChat}
								landingPageMode={userSettings.landingPageMode}
								ctrlEnterToSend={userSettings.ctrlEnterToSend}
								largeTextAsFile={userSettings.largeTextAsFile}
								enableMessageQueue={userSettings.enableMessageQueue}
								showFormattingToolbar={userSettings.showFormattingToolbar}
								richTextInput={userSettings.richTextInput}
								promptAutocomplete={userSettings.promptAutocomplete}
								imageCompression={userSettings.imageCompression}
								imageCompressionSize={userSettings.imageCompressionSize}
								insertSuggestionPrompt={userSettings.insertSuggestionPrompt}
								{lastUserMessage}
								speechAutoSend={userSettings.speechAutoSend}
								webSearchAlways={userSettings.webSearchAlways}
								knowledgeOptions={inputKnowledgeOptions}
								noteOptions={inputNoteOptions}
								chatOptions={inputChatOptions}
								onSubmit={submitPrompt}
								onStop={stopResponse}
								onToast={toast}
							/>
						</div>
					</div>
				{:else}
					{#if temporaryChat}
						<div class="relative z-20 flex justify-center pt-3">
							<div
								class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-gray-900/90 px-3 py-1 text-xs text-gray-400 backdrop-blur"
								title="此对话不会出现在历史记录中，消息也不会被保存。"
							>
								临时对话 · 不会写入历史
							</div>
						</div>
					{/if}
					<div
						bind:this={messagesContainer}
						id="messages-container"
						class="min-h-0 flex-1 overflow-y-auto"
					>
						<MockMessages
							{messages}
							{generating}
							modelName={currentModelName}
							userName={userSettings.displayName}
							chatBubble={userSettings.chatBubble}
							widescreenMode={userSettings.widescreenMode}
							showUsername={userSettings.showUsername}
							regenerateMenu={userSettings.regenerateMenu}
							collapseCodeBlocks={userSettings.collapseCodeBlocks}
							fadeStreaming={userSettings.chatFadeStreamingText}
							expandDetails={userSettings.expandDetails}
							detectArtifacts={userSettings.detectArtifacts}
							iframeSandboxAllowSameOrigin={userSettings.iframeSandboxAllowSameOrigin}
							iframeSandboxAllowForms={userSettings.iframeSandboxAllowForms}
							showFloatingActionButtons={userSettings.showFloatingActionButtons}
							floatingActionButtons={userSettings.floatingActionButtons}
							copyFormatted={userSettings.copyFormatted}
							keepFollowUpPrompts={userSettings.keepFollowUpPrompts}
							insertFollowUpPrompt={userSettings.insertFollowUpPrompt}
							onRegenerate={regenerateResponse}
							onContinue={continueResponse}
							continueLabel={assistMode === 'paper' ? `继续写${paperSection}` : '继续回答'}
							onEditMessage={editMessage}
							onSaveToNotebook={openSaveToNotebook}
							onToast={toast}
							onQuickAction={(content) => {
								prompt = content;
								submitPrompt(content);
							}}
							onFollowUp={(content, insertOnly) => {
								if (insertOnly) {
									prompt = content;
									return;
								}
								submitPrompt(content);
							}}
						/>
					</div>

					{#if messageQueue.length > 0}
						<div class="px-4 pb-1 text-center text-[11px] text-gray-500">
							队列中还有 {messageQueue.length} 条消息
							<button
								type="button"
								class="ml-2 underline hover:text-gray-300"
								onclick={() => {
									messageQueue = [];
								}}
							>
								清空
							</button>
						</div>
					{/if}

					{#if userSettings.webSearchAlways}
						<div class="px-4 pb-1 text-center text-[11px] text-sky-400/80">联网搜索：始终开启</div>
					{/if}

				<div
						class="relative z-10 shrink-0 px-4 pt-4 pb-2"
					>
						<div
							class={`mx-auto w-full ${userSettings.widescreenMode ? 'max-w-full' : 'max-w-3xl'}`}
						>
							<MockMessageInput
								bind:prompt
								placeholder="有什么我能帮您的吗？"
								{generating}
								ctrlEnterToSend={userSettings.ctrlEnterToSend}
								largeTextAsFile={userSettings.largeTextAsFile}
								enableMessageQueue={userSettings.enableMessageQueue}
								showFormattingToolbar={userSettings.showFormattingToolbar}
								richTextInput={userSettings.richTextInput}
								promptAutocomplete={userSettings.promptAutocomplete}
								imageCompression={userSettings.imageCompression}
								imageCompressionSize={userSettings.imageCompressionSize}
								{lastUserMessage}
								speechAutoSend={userSettings.speechAutoSend}
								webSearchAlways={userSettings.webSearchAlways}
								knowledgeOptions={inputKnowledgeOptions}
								noteOptions={inputNoteOptions}
								chatOptions={inputChatOptions}
								modelName={currentModelName}
								onSubmit={submitPrompt}
								onStop={stopResponse}
								onPasteAsFile={() => {
									toast('内容已转为本地文件引用');
								}}
								onToast={toast}
							/>
						</div>

						<p class="mt-2 text-center text-[11px] text-gray-600">
							回答来自 basic-agent 检索的教材与笔记，请核实重要内容。
						</p>
					</div>
				{/if}
			</div>
		</div>

		<ChatControlsPanel
			open={controlsOpen}
			bind:params={chatControls}
			{messages}
			modelName={currentModelName}
			onClose={() => {
				controlsOpen = false;
			}}
			onChange={(next) => {
				saveChatControls(next);
			}}
			onSelectMessage={(messageId) => {
				const el =
					document.getElementById(`message-${messageId}`) ??
					document.querySelector(`[data-message-id="${messageId}"]`);
				el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
			}}
		/>
	</section>
</main>

<SaveToNotebookDialog
	open={saveOpen}
	title={saveTitle}
	content={saveContent}
	onClose={() => {
		saveOpen = false;
	}}
	onSaved={(notebookName) => {
		saveToast = `已加入笔记本「${notebookName}」`;
		window.setTimeout(() => {
			saveToast = '';
		}, 3200);
	}}
/>

<SettingsModal
	open={settingsOpen}
	userRole="admin"
	onClose={() => {
		settingsOpen = false;
	}}
	onSettingsChange={handleSettingsChange}
	onImportChats={importChatsFromFile}
	onExportChats={exportAllChats}
	onArchiveAllChats={archiveAllChats}
	onDeleteAllChats={deleteAllChats}
	onOpenArchived={openArchivedChats}
	onToast={(message) => {
		saveToast = message;
		window.setTimeout(() => {
			saveToast = '';
		}, 2800);
	}}
/>

<DataControls
	allChats={[
		...chats.map((chat) => ({
			id: chat.id,
			title: chat.title,
			updatedAt: chat.updatedAt,
			archived: chat.archived
		}))
	]}
	files={[]}
	onImport={importChatsFromFile}
	onExport={exportAllChats}
	onArchiveAll={archiveAllChats}
	onDeleteAll={deleteAllChats}
	onUnarchive={(id) => {
		chats = chats.map((chat) => (chat.id === id ? { ...chat, archived: false } : chat));
		persistChats();
	}}
	onUnshare={() => {
		toast('该对话当前未生成分享链接');
	}}
	onDeleteChat={(id) => {
		chats = chats.filter((chat) => chat.id !== id);
		persistChats();
	}}
	onDeleteFile={() => {
		/* mock：FilesModal 中删除文件暂无 mock 数据 */
	}}
	canExport={true}
/>

<ArchivedChatsModal
	bind:show={archivedOpen}
	chats={[
		...chats.map((chat) => ({
			id: chat.id,
			title: chat.title,
			updatedAt: chat.updatedAt,
			archived: !!chat.archived
		}))
	]}
	onUpdate={() => {
		persistChats();
	}}
	onDelete={(id) => {
		chats = chats.filter((chat) => chat.id !== id);
		persistChats();
	}}
/>

<ShortcutsModal
	open={shortcutsOpen}
	onClose={() => {
		shortcutsOpen = false;
	}}
/>

{#if changelogOpen}
	<div class="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4">
		<div
			class="w-full max-w-md rounded-2xl border border-white/10 bg-gray-900 p-5 text-left shadow-xl"
		>
			<h2 class="text-lg font-semibold text-white">新功能介绍</h2>
			<p class="mt-2 text-sm leading-6 text-gray-400">
				界面设置已对齐 Open
				WebUI：支持消息队列、追问提示、产物预览、格式工具栏、图像压缩与通知音等。可在「设置 →
				界面」中逐项开关。
			</p>
			<button
				type="button"
				class="mt-4 rounded-xl bg-white px-4 py-2 text-sm font-medium text-black hover:bg-gray-200"
				onclick={() => {
					changelogOpen = false;
				}}
			>
				知道了
			</button>
		</div>
	</div>
{/if}

{#if saveToast}
	<div
		class="fixed bottom-6 left-1/2 z-[70] -translate-x-1/2 rounded-xl border border-white/10 bg-gray-900 px-4 py-2 text-sm text-gray-100 shadow-lg"
	>
		{saveToast}
	</div>
{/if}
