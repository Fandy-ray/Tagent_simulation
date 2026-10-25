<script lang="ts">
	import { SvelteSet, SvelteURLSearchParams } from 'svelte/reactivity';
	type SpeechRecognitionResultLike = { [index: number]: { transcript: string } };
	type SpeechRecognitionEventLike = { results: ArrayLike<SpeechRecognitionResultLike> };
	type SpeechRecognitionLike = {
		lang: string;
		interimResults: boolean;
		onresult: ((event: SpeechRecognitionEventLike) => void) | null;
		onerror: (() => void) | null;
		onend: (() => void) | null;
		start: () => void;
	};
	type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
	type SpeechWindow = Window & {
		SpeechRecognition?: SpeechRecognitionConstructor;
		webkitSpeechRecognition?: SpeechRecognitionConstructor;
	};
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/stores';
	import { onDestroy, onMount, tick } from 'svelte';

	import {
		generateEssayTopic,
		getAgentModels,
		reviewEssay,
		streamAgentChat
	} from '$lib/apis/agent';
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
	import { isNarrowScreen } from '$lib/utils/viewport';
	import { buildQaCitations, enrichCitationsWithPages } from '$lib/data/citations';
	import {
		countCharacters,
		ESSAY_CLIENT_TIMEOUT_MS,
		ESSAY_TOPIC_MAX,
		essayLengthGate,
		essayTopicMarkdown,
		paperReviewMarkdown,
		paperSubmissionLabel,
		pyStrip,
		type EssayTopic,
		type PaperCard
	} from '$lib/data/essay';
	import { essaySamples } from '$lib/data/samples';
	import {
		loadChatControls,
		saveChatControls,
		toAgentOptions,
		type ChatControlParams
	} from '$lib/data/chatControls';
	import type { KnowledgeCollection } from '$lib/data/knowledge';
	import {
		loadQaChats,
		saveQaChats,
		saveStreamingDraft,
		type QaChat
	} from '$lib/data/qaConversations';
	import { historyForRequest } from '$lib/data/chatHistory';
	import { buildFollowUps, buildTags } from '$lib/data/followUps';
	import { setRecordingPaused } from '$lib/data/learner';
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
	let settingsTab = $state<'general' | 'data_controls'>('general');
	let archivedOpen = $state(false);
	let shortcutsOpen = $state(false);
	let userSettings = $state<UserSettings>(loadUserSettings());

	// 两种助手模式使用独立的会话空间。旧数据没有 mode 时按课程答疑处理，
	// 这样升级前已有的普通对话仍然可以正常显示。
	const modeChats = $derived(chats.filter((chat) => (chat.mode ?? 'qa') === assistMode));

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

	// 输入框「+」菜单里引用笔记、引用其他对话（restored_frontend 放回来的输入框扩展）
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

	/**
	 * 把模型 id 换成登记时填的显示名。
	 *
	 * 回答头部原来直接显示后端返回的 served_model_id（小写的「deepseek」），
	 * 在中文界面里很突兀，而且登记页明明填了「DeepSeek」这样的名字。
	 * 认不出来的 id 就原样显示——历史消息可能来自已经删掉的模型。
	 */
	const modelDisplayName = (id: string | undefined) =>
		id ? (modelOptions.find((model) => model.id === id)?.name ?? id) : '';

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
		const speechWindow = window as SpeechWindow;
		const SpeechRecognition =
			speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
		if (!SpeechRecognition) {
			toast('当前浏览器不支持语音听写');
			dictationEnabled = false;
			return;
		}
		try {
			const recognition = new SpeechRecognition();
			recognition.lang = 'zh-CN';
			recognition.interimResults = false;
			recognition.onresult = (event: SpeechRecognitionEventLike) => {
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

	/** 窄屏上侧栏盖在对话上：选完对话、新建对话之后就收起来，别让它一直挡着 */
	const closeSidebarIfNarrow = () => {
		if (isNarrowScreen()) {
			sidebarOpen = false;
		}
	};

	onMount(() => {
		closeSidebarIfNarrow();
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
						chat.id === urlChat && (requestedMode === null || (chat.mode ?? 'qa') === requestedMode)
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
				if (settingsOpen || shortcutsOpen || archivedOpen || saveOpen) {
					event.preventDefault();
					settingsOpen = false;
					shortcutsOpen = false;
					archivedOpen = false;
					saveOpen = false;
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

	/**
	 * 整块出来的卡片（出题、批改）：尽量滚到底，但不能把卡片的开头滚出可视区。
	 * 一律滚到底的话，长卡片的标题和头像会落到可视区上方，紧贴着论文任务栏，
	 * 看着像被任务栏挡住了上沿。逐字输出的回答不走这里，照旧跟着往下滚。
	 */
	const revealMessageStart = async (messageId: string) => {
		await tick();
		if (!messagesContainer) {
			return;
		}
		const bottom = messagesContainer.scrollHeight - messagesContainer.clientHeight;
		const el = messagesContainer.querySelector<HTMLElement>(
			`[data-message-id="${CSS.escape(messageId)}"]`
		);
		if (!el) {
			messagesContainer.scrollTop = bottom;
			return;
		}
		const top =
			el.getBoundingClientRect().top -
			messagesContainer.getBoundingClientRect().top +
			messagesContainer.scrollTop;
		messagesContainer.scrollTop = Math.max(0, Math.min(bottom, top - 12));
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
			// 落盘那一刻还在吐字，就记成「被打断」：刷新后能看出这条没答完
			interrupted: message.streaming || message.interrupted ? true : undefined,
			streaming: false
		}));

	// 流式回答中途也落盘（每秒最多一次，刷新 / 关页时再完整存一次）：已经吐出来的部分不丢，
	// 刷新后标成「没有完成」、可以重新生成。以前只在答完时才存，刷新就只剩一个问题（压测 F2）。
	// 每秒这次只存正在吐字的那一条（$lib/data/qaConversations 的 saveStreamingDraft），
	// 不把整个会话库每秒重新序列化一遍——会话多、批改卡带全文时那样会卡住正在刷字的页面
	let streamingCommitTimer: number | null = null;
	const scheduleStreamingCommit = () => {
		if (streamingCommitTimer !== null) {
			return;
		}
		streamingCommitTimer = window.setTimeout(() => {
			streamingCommitTimer = null;
			if (!generating || !activeChatId || isTemporarySession()) {
				return;
			}
			for (let index = messages.length - 1; index >= 0; index -= 1) {
				if (messages[index].streaming) {
					saveStreamingDraft(activeChatId, messages[index]);
					return;
				}
			}
		}, 1000);
	};

	const restoreChatMessages = (chat: QaChat | undefined) => {
		const task = chat?.paperTask ?? paperTask;

		const restored: MockMessage[] = cloneMessages(chat?.messages ?? []).map((message) => {
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

		// 问题发出去、一个字还没回就刷新了：补一条空的「没有完成」，好让「重新生成」有处可点
		const last = restored.at(-1);
		if (last?.role === 'user') {
			restored.push({
				id: `assistant-interrupted-${last.id}`,
				role: 'assistant',
				content: '',
				interrupted: true
			});
		}

		return restored;
	};

	const isTemporarySession = () =>
		temporaryChat || (typeof activeChatId === 'string' && activeChatId.startsWith('local:'));

	// 临时对话：后端也不留学习记录（界面答应过「消息不会被保存」）
	$effect(() => {
		setRecordingPaused(isTemporarySession());
	});

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
		const params = new SvelteURLSearchParams();

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

		void goto(resolve(next), {
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
		const hadConversation = messages.length > 0;
		// commitActive 已经把当前这段存下了；它只是收在**另一套**历史里。
		// 不说一声的话，学生看到对话清空会以为聊没了（实测被当成 bug 报上来过）。
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
		if (hadConversation) {
			const from = mode === 'paper' ? '课程答疑' : '论文助手';
			toast(`刚才的对话已存进「${from}」的历史里，切回去就能看到`, 4200);
		}
	};

	// 输入框里 `#` 选知识库、`@` 选模型 —— 和顶栏那两个选择器效果一致
	const selectKnowledgeFromInput = (id: string, name: string) => {
		collectionId = id;
		syncUrl();
		toast(`已引用知识库「${name}」`);
	};

	const selectModelFromInput = (id: string, name: string) => {
		selectedModelId = id;
		syncUrl();
		toast(`已切换模型「${name}」`);
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
		void goto(resolve('/agent-select'));
	};

	const openSettings = () => {
		settingsTab = 'general';
		settingsOpen = true;
	};

	// 数据管理就在设置里（导入、导出、归档、清空）：直接打开到那一页
	const openDataPanel = () => {
		settingsTab = 'data_controls';
		settingsOpen = true;
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
			const seen = new SvelteSet<string>();
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

	const deleteChatById = (chatId: string) => {
		chats = chats.filter((chat) => chat.id !== chatId);
		if (activeChatId === chatId) {
			activeChatId = null;
			messages = [];
			syncUrl();
		}
		persistChats();
	};

	const openShortcuts = () => {
		shortcutsOpen = true;
	};

	const openPlayground = () => {
		void goto(resolve('/playground'));
	};

	const openAdmin = () => {
		void goto(resolve('/admin'));
	};

	const signOut = () => {
		bumpGeneration();
		generating = false;
		commitActive();
		void goto(resolve('/welcome'));
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
			resolve(
				`/exam?model=${encodeURIComponent(selectedModelId)}&from=qa&topic=${encodeURIComponent(collectionId)}`
			)
		);
	};

	const openNotes = () => {
		commitActive();
		const params = new SvelteURLSearchParams();
		params.set('from', 'qa');
		if (selectedModelId) params.set('model', selectedModelId);
		if (collectionId) {
			params.set('notebook', collectionId);
			params.set('collection', collectionId);
		}
		if (activeChatId) params.set('chat', activeChatId);
		void goto(resolve(`/notebook?${params.toString()}`));
	};

	// 侧栏「工作空间」（restored_frontend 放回来的入口）。10-02 隐藏时连同按钮一起删掉过
	const openWorkspace = () => {
		commitActive();
		const params = new SvelteURLSearchParams();
		if (selectedModelId) params.set('model', selectedModelId);
		if (activeChatId) params.set('chat', activeChatId);
		const search = params.toString();
		void goto(resolve(search ? `/workspace/models?${search}` : '/workspace/models'));
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
				// 论文附上期刊官网的地址，存进笔记本后还能找到原文
				const link = /^https?:\/\//i.test(citation.href) ? ` ${citation.href}` : '';
				// 教材的「笔记本名」和题目都是「课程教材」，别写两遍
				const head =
					citation.collectionName === citation.title
						? citation.title
						: `${citation.collectionName} · ${citation.title}`;
				return `- ${head}${locator}${link}`;
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

	/** 本次请求检索哪些笔记本：分组挂的 + 当前选中的 + 论文任务卡上挂了笔记的 */
	const currentNotebookIds = () => {
		const folderNotebookIds = (selectedFolder?.knowledgeItems ?? [])
			.filter((item) => item.type === 'collection')
			.map((item) => item.id);
		return Array.from(
			new Set([
				...folderNotebookIds,
				...(collectionId ? [collectionId] : []),
				...attachedPaperNotebookIds
			])
		);
	};

	/** 论文模式的问题是几千字的任务 prompt，拿它检索等于没检索；另给后端一句「题目 + 关键词」 */
	const paperRetrievalOptions = () => {
		if (assistMode !== 'paper') {
			return {};
		}
		const query = [paperTask.title, paperTask.keywords]
			.map((part) => part.trim())
			.filter(Boolean)
			.join(' ');
		return query ? { retrieval_query: query } : {};
	};

	const ask = async (question: string, seq: number) => {
		const controller = new AbortController();
		abortController = controller;
		const assistantId = `assistant-${Date.now()}`;
		let created = false;
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
		/**
		 * 出处的后备来源：直接问 OpenNotebook 要几条命中。
		 *
		 * **只在后端没给出处时才调**。这是后端还不会返回出处那阵留下的逻辑，
		 * 原来每次提问都提前发一次，等答案回来发现后端已经给了才 abort——
		 * 可那时请求早打出去了，白白多一次往返，还可能触发按量计费的嵌入服务。
		 */
		const fallbackHits = async () => {
			const searchController = new AbortController();
			const searchTimer = window.setTimeout(() => searchController.abort(), 4000);
			controller.signal.addEventListener('abort', () => searchController.abort(), {
				once: true
			});
			try {
				return await searchKnowledge(citationQuery, {
					limit: 8,
					signal: searchController.signal
				});
			} catch {
				return [];
			} finally {
				window.clearTimeout(searchTimer);
			}
		};

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
					message.id === assistantId
						? { ...message, content, streaming, interrupted: undefined }
						: message
				);
			}

			scheduleStreamingCommit();
			void scrollToBottom();
		};

		try {
			const folderPrompt = selectedFolder?.systemPrompt?.trim() ?? '';
			const baseOptions = toAgentOptions(chatControls);
			const mergedSystem = [folderPrompt, baseOptions.system].filter(Boolean).join('\n\n');
			const notebookIds = currentNotebookIds();

			const result = await streamAgentChat(
				question,
				selectedModelId,
				writeDelta,
				controller.signal,
				{
					notebookIds,
					mode: assistMode,
					history: historyForRequest(messages),
					...paperRetrievalOptions(),
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
				const notebook = notebooks.find((item) => item.id === collectionId) ?? null;
				const backendGaveSources =
					Boolean(result.retrievedContext) || (result.citations?.length ?? 0) > 0;
				const hits = backendGaveSources ? [] : await fallbackHits();
				let citations = buildQaCitations({
					agentCitations: result.citations,
					retrievedContext: result.retrievedContext,
					searchHits: hits,
					question: citationQuery,
					answer: result.content,
					collections,
					notebook
				});
				// 补页码要逐条去 OpenNotebook 取原文。它开着却卡住时，这一步没有上限就会一直挂着：
				// 回答早就显示完了，「停止生成」却一直在、下一个问题发不出去。给它和检索一样的 4 秒，
				// 超时的那条不补页码，照常收尾。
				const enrichController = new AbortController();
				const stopEnrich = () => enrichController.abort();
				controller.signal.addEventListener('abort', stopEnrich, { once: true });
				const enrichTimer = window.setTimeout(stopEnrich, 4000);
				try {
					citations = await enrichCitationsWithPages(citations, question, (fileId) =>
						getSourceText(fileId, enrichController.signal)
					);
				} finally {
					window.clearTimeout(enrichTimer);
					controller.signal.removeEventListener('abort', stopEnrich);
				}

				if (seq !== generationSeq) {
					return;
				}

				messages = messages.map((message) =>
					message.id === assistantId
						? {
								...message,
								model: result.model || selectedModelId,
								citations,
								followUps: userSettings.autoFollowUps ? buildFollowUps(question) : undefined,
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
			// 后备检索现在是按需发的，它自己绑了 controller.signal，这里不用再收一次
			if (abortController === controller) {
				abortController = null;
			}
		}
	};

	/** 还没有会话就新建一个（临时对话只给个本地 id）；已有会话就把当前消息落盘 */
	const ensureActiveChat = (firstMessage: MockMessage, titleSeed: string) => {
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
										userSettings.titleAutoGenerate ? clipTitle(titleSeed) : '论文辅助'
									)
								: userSettings.titleAutoGenerate
									? clipTitle(titleSeed)
									: '新对话',
						updatedAt: Date.now(),
						collectionId,
						folderId: selectedFolderId,
						mode: assistMode,
						paperTask: assistMode === 'paper' ? { ...paperTask } : undefined,
						messages: [firstMessage]
					},
					...chats
				];
				persistChats(activeChatId);
				syncUrl();
			}
		} else if (!isTemporarySession()) {
			commitActive(messages);
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
			// 连点同一个按钮（「解释」、追问建议……）：正在答的就是这一句、或队列里已经有这一句，
			// 就不再排一遍。实测「解释」连点 8 下排了 7 条一样的，上游被调 8 次。
			const answering = [...messages].reverse().find((message) => message.role === 'user');
			if (
				(answering?.requestContent ?? answering?.content ?? '').trim() === trimmedContent ||
				messageQueue.some((item) => item.requestContent === trimmedContent)
			) {
				saveToast = '这一条已经在回答或排队了';
				window.setTimeout(() => {
					saveToast = '';
				}, 1800);
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

		ensureActiveChat(userMessage, trimmedContent);

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

	// ====================== 论文模式：出题与交稿批改 ======================
	// 这两样都不是流式文本，而是一条带 paperCard 的助手消息：先插一张「进行中」的卡，
	// 请求回来后原地写回。停止、重新生成、刷新恢复都只看这张卡自己的状态。

	const samples = essaySamples();
	let sampleIndex = 0;

	const patchMessage = (id: string, patch: Partial<MockMessage>) => {
		messages = messages.map((message) => (message.id === id ? { ...message, ...patch } : message));
	};

	const pendingContent = (card: PaperCard) => (card.kind === 'topic' ? '正在出题……' : '正在批改……');

	/** 发出卡片对应的请求，把结果写回这条消息。卡片自带重跑所需的全部参数 */
	const runPaperCard = async (assistantId: string, card: PaperCard, seq: number) => {
		const controller = new AbortController();
		abortController = controller;
		// 后端有自己的预算；这里只防后端整个没了响应，免得卡片永远转圈
		let timedOut = false;
		const timer = window.setTimeout(() => {
			timedOut = true;
			controller.abort();
		}, ESSAY_CLIENT_TIMEOUT_MS);

		let next: PaperCard;
		let content: string;

		try {
			if (card.kind === 'topic') {
				const topic = await generateEssayTopic(
					selectedModelId,
					card.hint,
					currentNotebookIds(),
					controller.signal
				);
				next = { ...card, topic, error: undefined };
				content = essayTopicMarkdown(topic);
			} else {
				const review = await reviewEssay(
					selectedModelId,
					card.text,
					card.topic || undefined,
					currentNotebookIds(),
					controller.signal
				);
				next = { ...card, review, error: undefined };
				content = paperReviewMarkdown(review, card.topic, card.text);
			}
		} catch (error) {
			// 停止了、开了新一轮，或者页面正在刷新：卡片保持「没有完成」，不写错误
			// （刷新时浏览器掐断请求报的是 AbortError，见 $lib/apis/agent 的 pageUnloading）
			const aborted = error instanceof DOMException && error.name === 'AbortError';
			if (seq !== generationSeq || (aborted && !timedOut)) {
				return;
			}
			const message = timedOut
				? '等了太久还没有结果，后端可能卡住了，稍后再试。'
				: error instanceof Error
					? error.message
					: '请求失败，请重试。';
			next = { ...card, error: message };
			content = message;
		} finally {
			window.clearTimeout(timer);
			if (abortController === controller) {
				abortController = null;
			}
		}

		if (seq !== generationSeq) {
			return;
		}

		patchMessage(assistantId, {
			paperCard: next,
			content,
			streaming: false,
			model: selectedModelId
		});
		generating = false;
		commitActive();
		void revealMessageStart(assistantId);

		if (messageQueue.length > 0) {
			const queued = messageQueue[0];
			messageQueue = messageQueue.slice(1);
			void tick().then(() => submitPrompt(queued.requestContent, queued.displayContent));
		}
	};

	/** 追加「用户这一问 + 进行中的卡片」两条消息，然后发请求 */
	const startPaperCard = (userContent: string, card: PaperCard, titleSeed: string) => {
		const seq = bumpGeneration();
		const now = Date.now();
		const userMessage: MockMessage = { id: `user-${now}`, role: 'user', content: userContent };
		const assistantId = `assistant-${now}`;

		messages = [
			...messages,
			userMessage,
			{
				id: assistantId,
				role: 'assistant',
				model: selectedModelId,
				content: pendingContent(card),
				streaming: true,
				paperCard: card
			}
		];
		generating = true;
		ensureActiveChat(userMessage, titleSeed);
		void scrollToBottom();
		void runPaperCard(assistantId, card, seq);
	};

	const proposeTopic = () => {
		if (generating) {
			toast('正在生成，等这一轮结束再出题');
			return;
		}

		// 任务卡上的关键词当选题方向；后端对方向的长度上限与出卷主题相同
		const hint = Array.from(paperKeywords.trim()).slice(0, ESSAY_TOPIC_MAX).join('');
		startPaperCard(
			hint ? `请出一道小论文题（方向：${hint}）` : '请出一道小论文题',
			{ kind: 'topic', hint, topic: null },
			'小论文出题'
		);
	};

	const submitPaperForReview = (raw: string) => {
		if (generating) {
			toast('正在生成，等这一轮结束再交稿');
			return;
		}

		// 批注下标相对后端 strip 之后的正文算，所以发出去的、卡片里存的都是这一份
		const text = pyStrip(raw);
		const gate = essayLengthGate(countCharacters(text));
		if (!gate.ok) {
			toast(gate.message);
			return;
		}

		const topic = paperTitle.trim();
		if (Array.from(topic).length > ESSAY_TOPIC_MAX) {
			toast(`论文题目超过 ${ESSAY_TOPIC_MAX} 字，缩短一些再交`);
			return;
		}

		prompt = '';
		startPaperCard(
			paperSubmissionLabel(text),
			{ kind: 'review', text, topic, review: null },
			topic || '小论文批改'
		);
	};

	/** 卡片上的「重新出题 / 重新批改」和消息的「重新生成」：原地重跑，用卡片自存的参数 */
	const rerunPaperCard = (messageId: string) => {
		if (generating) {
			return;
		}

		const card = messages.find((message) => message.id === messageId)?.paperCard;
		if (!card) {
			return;
		}

		const fresh: PaperCard =
			card.kind === 'topic'
				? { kind: 'topic', hint: card.hint, topic: null }
				: { kind: 'review', text: card.text, topic: card.topic, review: null };
		const seq = bumpGeneration();
		// 重跑就是新的一轮：上一轮被刷新打断留下的「没有完成」标记要清掉，
		// 否则重批成功了，卡片下面还挂着「这次回答没有完成」
		patchMessage(messageId, {
			paperCard: fresh,
			content: pendingContent(fresh),
			streaming: true,
			interrupted: undefined
		});
		generating = true;
		commitActive();
		void runPaperCard(messageId, fresh, seq);
	};

	const adoptTopic = (topic: EssayTopic) => {
		const requirements = topic.requirements.join('\n');
		const existing = paperContext.courseRequirements.trim();
		handlePaperTaskChange({
			...paperTask,
			title: topic.title,
			context: {
				...paperContext,
				// 学生自己填过的课程要求不覆盖，把这道题的写作要求接在后面
				courseRequirements: !existing
					? requirements
					: existing.includes(requirements)
						? existing
						: `${existing}\n${requirements}`
			}
		});
		toast('已设为本次题目');
	};

	const fillSample = () => {
		const sample = samples[sampleIndex % samples.length];
		sampleIndex += 1;
		prompt = sample.body;
		// 范例是照着它自己的题目写的，换成它的题目，「切题与内容」才判得公平。
		// 但这会把刚刚「设为本次题目」的那道题顶掉——演示主线正好是
		// 出题 → 设为本次题目 → 填入范例，一声不响地换掉等于白出了一道题。
		// 所以把原题目一并说出来，方便放回去。
		const previous = paperTitle.trim();
		if (sample.topic && sample.topic !== previous) {
			handlePaperTaskChange({ ...paperTask, title: sample.topic });
			toast(
				previous
					? `已填入范例：${sample.title}。题目改成了范例自带的「${sample.topic}」，原题目是「${previous}」`
					: `已填入范例：${sample.title}（题目一并设为「${sample.topic}」）`,
				5200
			);
			return;
		}
		toast(`已填入范例：${sample.title}`);
	};

	const stopResponse = () => {
		bumpGeneration();
		finishStreamingMessages();
		// 一个字还没回就点了停止：补一条空的「没有完成」，问题下面不至于空着，也有「重新生成」可点
		const last = messages.at(-1);
		if (last?.role === 'user') {
			messages = [
				...messages,
				{ id: `assistant-stopped-${last.id}`, role: 'assistant', content: '', interrupted: true }
			];
		}
		generating = false;
		commitActive();
	};

	const regenerateResponse = (messageId: string) => {
		if (generating) {
			return;
		}

		// 出题卡 / 批改卡不走对话流：原地用卡片自带的参数重跑
		if (messages.some((message) => message.id === messageId && message.paperCard)) {
			rerunPaperCard(messageId);
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
				message.id === messageId
					? { ...message, content: joined, streaming: true, interrupted: undefined }
					: message
			);
			scheduleStreamingCommit();
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
				const notebookIds = currentNotebookIds();

				const result = await streamAgentChat(
					continuePrompt,
					selectedModelId,
					writeDelta,
					controller.signal,
					{
						notebookIds,
						mode: assistMode,
						history: historyForRequest(messages),
						...paperRetrievalOptions(),
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
		setRecordingPaused(false);
		if (paperTaskSyncTimer !== null) {
			window.clearTimeout(paperTaskSyncTimer);
		}
		if (streamingCommitTimer !== null) {
			window.clearTimeout(streamingCommitTimer);
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

<!-- 刷新、关页时把正在吐字的回答再存一次：定时落盘之间的那一秒也不丢（onDestroy 管不到整页刷新） -->
<svelte:window
	onpagehide={() => {
		if (generating && !isTemporarySession()) {
			commitActive();
		}
	}}
/>

<main class="flex h-screen overflow-hidden bg-gray-900 text-white">
	{#if sidebarOpen}
		<MockSidebar
			{activeChatId}
			{selectedFolderId}
			chats={sidebarChats}
			searchChats={modeChats}
			{folders}
			userName={userSettings.displayName}
			avatarText={userSettings.avatarText}
			statusEmoji={userSettings.statusEmoji}
			statusMessage={userSettings.statusMessage}
			activeNav="chats"
			onHome={returnToSelect}
			onNewChat={() => {
				createEmptyChat();
				closeSidebarIfNarrow();
			}}
			onSelectChat={(...args: Parameters<typeof selectChat>) => {
				selectChat(...args);
				closeSidebarIfNarrow();
			}}
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
				void goto(resolve('/notebook?from=qa'));
			}}
			onClose={() => {
				sidebarOpen = false;
			}}
		/>
		<!-- 窄屏时侧栏盖在内容上，点旁边这层遮罩就收起 -->
		<button
			type="button"
			class="fixed inset-0 z-30 bg-black/50 md:hidden"
			aria-label="收起侧栏"
			onclick={() => {
				sidebarOpen = false;
			}}
		></button>
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
				onOpenExam={openExam}
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
					class="max-h-[calc(100vh-4rem)] min-h-0 shrink-0 overflow-y-auto overscroll-contain border-b border-white/[0.06] bg-gray-900 px-3 py-2 md:px-5"
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
						onProposeTopic={proposeTopic}
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
								bind:prompt
								{generating}
								mode={assistMode}
								{temporaryChat}
								landingPageMode={userSettings.landingPageMode}
								ctrlEnterToSend={userSettings.ctrlEnterToSend}
								enableMessageQueue={userSettings.enableMessageQueue}
								showFormattingToolbar={userSettings.showFormattingToolbar}
								richTextInput={userSettings.richTextInput}
								promptAutocomplete={userSettings.promptAutocomplete}
								insertSuggestionPrompt={userSettings.insertSuggestionPrompt}
								{lastUserMessage}
								modelName={currentModelName}
								onSubmit={submitPrompt}
								onReview={assistMode === 'paper' ? submitPaperForReview : null}
								onFillSample={assistMode === 'paper' && samples.length > 0 ? fillSample : null}
								onStop={stopResponse}
								knowledgeOptions={notebooks.map((n) => ({ id: n.id, name: n.name }))}
								{modelOptions}
								onSelectKnowledge={selectKnowledgeFromInput}
								onSelectModel={selectModelFromInput}
								largeTextAsFile={userSettings.largeTextAsFile}
								imageCompression={userSettings.imageCompression}
								imageCompressionSize={userSettings.imageCompressionSize}
								speechAutoSend={userSettings.speechAutoSend}
								webSearchAlways={userSettings.webSearchAlways}
								noteOptions={inputNoteOptions}
								chatOptions={inputChatOptions}
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
							resolveModelName={modelDisplayName}
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
							currentTopic={paperTitle}
							onAdoptTopic={adoptTopic}
							onRetryPaperCard={rerunPaperCard}
							onContinue={continueResponse}
							continueLabel={assistMode === 'paper' ? `继续写${paperSection}` : '继续回答'}
							onEditMessage={editMessage}
							onSaveToNotebook={openSaveToNotebook}
							onToast={toast}
							onQuickAction={(content, displayContent) => {
								prompt = content;
								submitPrompt(content, displayContent);
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

					<div class="relative z-10 shrink-0 px-4 pt-4 pb-2">
						<div
							class={`mx-auto w-full ${userSettings.widescreenMode ? 'max-w-full' : 'max-w-3xl'}`}
						>
							<MockMessageInput
								bind:prompt
								placeholder="有什么我能帮您的吗？"
								{generating}
								ctrlEnterToSend={userSettings.ctrlEnterToSend}
								enableMessageQueue={userSettings.enableMessageQueue}
								showFormattingToolbar={userSettings.showFormattingToolbar}
								richTextInput={userSettings.richTextInput}
								promptAutocomplete={userSettings.promptAutocomplete}
								{lastUserMessage}
								modelName={currentModelName}
								onSubmit={submitPrompt}
								onReview={assistMode === 'paper' ? submitPaperForReview : null}
								onFillSample={assistMode === 'paper' && samples.length > 0 ? fillSample : null}
								onStop={stopResponse}
								knowledgeOptions={notebooks.map((n) => ({ id: n.id, name: n.name }))}
								{modelOptions}
								onSelectKnowledge={selectKnowledgeFromInput}
								onSelectModel={selectModelFromInput}
								largeTextAsFile={userSettings.largeTextAsFile}
								imageCompression={userSettings.imageCompression}
								imageCompressionSize={userSettings.imageCompressionSize}
								speechAutoSend={userSettings.speechAutoSend}
								webSearchAlways={userSettings.webSearchAlways}
								noteOptions={inputNoteOptions}
								chatOptions={inputChatOptions}
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

<!--
	下面这几个弹窗平时关着：打开时才加载（设置面板一项就有几十 KB），
	不压在答疑页首屏里。关上即卸载，下次打开重新挂载、重新读一遍设置。
-->
{#if saveOpen}
	{#await import('$lib/components/chat/SaveToNotebookDialog.svelte') then { default: SaveToNotebookDialog }}
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
	{/await}
{/if}

{#if settingsOpen}
	{#await import('$lib/components/chat/SettingsModal.svelte') then { default: SettingsModal }}
		<SettingsModal
			open={settingsOpen}
			initialTab={settingsTab}
			userRole="admin"
			showAdminPanel={true}
			onClose={() => {
				settingsOpen = false;
			}}
			onSettingsChange={handleSettingsChange}
			onImportChats={importChatsFromFile}
			onExportChats={exportAllChats}
			onArchiveAllChats={archiveAllChats}
			onDeleteAllChats={deleteAllChats}
			onToast={(message) => {
				saveToast = message;
				window.setTimeout(() => {
					saveToast = '';
				}, 2800);
			}}
		/>
	{/await}
{/if}

{#if archivedOpen}
	{#await import('$lib/components/layout/ArchivedChatsModal.svelte') then { default: ArchivedChatsModal }}
		<ArchivedChatsModal
			bind:show={archivedOpen}
			chats={archivedChats}
			onUnarchive={unarchiveChat}
			onOpenChat={openArchivedChat}
			onDelete={deleteChatById}
		/>
	{/await}
{/if}

{#if shortcutsOpen}
	{#await import('$lib/components/chat/ShortcutsModal.svelte') then { default: ShortcutsModal }}
		<ShortcutsModal
			open={shortcutsOpen}
			onClose={() => {
				shortcutsOpen = false;
			}}
		/>
	{/await}
{/if}

{#if saveToast}
	<div
		class="fixed bottom-6 left-1/2 z-[70] -translate-x-1/2 rounded-xl border border-white/10 bg-gray-900 px-4 py-2 text-sm text-gray-100 shadow-lg"
	>
		{saveToast}
	</div>
{/if}
