import { browser } from '$app/environment';

import type { PaperCard } from '$lib/data/essay';
import type { Citation } from '$lib/data/knowledge';
import type { PaperTask } from '$lib/data/paperWorkflow';

export type AssistMode = 'qa' | 'paper';

export type QaMessage = {
	id: string;
	role: 'user' | 'assistant';
	content: string;
	/** 卡片操作只展示简短标签，真正发送给 Agent 的请求保存在这里。 */
	requestContent?: string;
	/** 带了附件、技能时，检索知识库只用学生打的那句话（重新生成时也要用同一句） */
	retrievalQuery?: string;
	model?: string;
	citations?: Citation[];
	streaming?: boolean;
	followUps?: string[];
	tags?: string[];
	/** 论文模式的出题卡 / 批改卡：有它时渲染卡片而不是 Markdown（见 $lib/data/essay 的 PaperCard） */
	paperCard?: PaperCard;
	/** 生成到一半被打断（刷新、关页、断网）：存下来的是半截，刷新后提示可以「重新生成」 */
	interrupted?: boolean;
	/** 学生点的「有帮助 / 没有帮助」；同时记到后端，老师在管理员面板「评估」里看 */
	rating?: 'up' | 'down';
};

export type QaChat = {
	id: string;
	title: string;
	updatedAt: number;
	collectionId?: string;
	folderId?: string | null;
	tags?: string[];
	mode?: AssistMode;
	paperTask?: PaperTask;
	archived?: boolean;
	messages: QaMessage[];
};

const STORAGE_KEY = 'tagentnote.qa.chats.v1';
/**
 * 流式回答进行中的「草稿」：只有正在吐字的那一条消息（几 KB）。
 *
 * 生成中每秒都要落一次盘，好让浏览器崩溃、被杀进程时已经吐出的部分不丢；但整个会话库
 * （几十段对话、带全文的批改卡）每秒序列化一遍太重，会卡住正在刷字的页面。所以生成中只写这一条，
 * 下次读取会话时并回去；任何一次完整保存都已经包含最新内容，顺手把草稿清掉。
 */
const DRAFT_KEY = 'tagentnote.qa.streaming-draft.v1';
const MAX_CHATS = 40;

type StoredBundle = {
	chats: QaChat[];
	activeId: string | null;
};

const snapshotMessage = (message: QaMessage): QaMessage => ({
	id: message.id,
	role: message.role,
	content: message.content,
	requestContent: message.requestContent,
	retrievalQuery: message.retrievalQuery,
	model: message.model,
	citations: message.citations?.map((citation) => ({ ...citation })),
	followUps: message.followUps?.slice(),
	tags: message.tags?.slice(),
	// 存盘时还在吐字的消息就是被打断的那条
	interrupted: message.interrupted || message.streaming ? true : undefined,
	rating: message.rating === 'up' || message.rating === 'down' ? message.rating : undefined,
	// 页面里的消息是 $state 代理，structuredClone 会直接抛错；卡片本来就是纯 JSON，走一遍 JSON 最稳
	paperCard: message.paperCard
		? (JSON.parse(JSON.stringify(message.paperCard)) as PaperCard)
		: undefined,
	streaming: false
});

const snapshotChat = (chat: QaChat): QaChat => ({
	id: chat.id,
	title: chat.title,
	updatedAt: chat.updatedAt,
	collectionId: chat.collectionId,
	folderId: chat.folderId ?? null,
	tags: chat.tags ? [...chat.tags] : undefined,
	mode: chat.mode,
	paperTask: chat.paperTask
		? {
				...chat.paperTask,
				context: chat.paperTask.context
					? {
							...chat.paperTask.context,
							attachedNotes: Object.fromEntries(
								Object.entries(chat.paperTask.context.attachedNotes ?? {}).map(([key, notes]) => [
									key,
									notes?.map((note) => ({ ...note })) ?? []
								])
							),
							attachedFiles:
								chat.paperTask.context.attachedFiles?.map((file) => ({ ...file })) ?? []
						}
					: undefined
			}
		: undefined,
	archived: chat.archived,
	messages: chat.messages.map(snapshotMessage)
});

export function loadQaChats(): StoredBundle {
	if (!browser) {
		return { chats: [], activeId: null };
	}

	try {
		const raw = localStorage.getItem(STORAGE_KEY);

		if (!raw) {
			return { chats: [], activeId: null };
		}

		const parsed = JSON.parse(raw) as Partial<StoredBundle>;
		const chats = Array.isArray(parsed.chats)
			? parsed.chats
					.filter((chat) => chat && typeof chat.id === 'string' && Array.isArray(chat.messages))
					.map(snapshotChat)
			: [];
		const activeId =
			typeof parsed.activeId === 'string' && chats.some((chat) => chat.id === parsed.activeId)
				? parsed.activeId
				: null;

		applyStreamingDraft(chats);
		return { chats, activeId };
	} catch {
		return { chats: [], activeId: null };
	}
}

export function saveQaChats(chats: QaChat[], activeId: string | null) {
	if (!browser) {
		return;
	}

	const bundle: StoredBundle = {
		chats: chats.slice(0, MAX_CHATS).map(snapshotChat),
		activeId
	};

	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(bundle));
		// 完整保存里已经是最新内容了，草稿作废
		localStorage.removeItem(DRAFT_KEY);
	} catch {
		// Quota or private mode. Keep going with in-memory chats.
	}
}

type StreamingDraft = { chatId: string; message: QaMessage };

/** 生成中定时存的那一条（存下来就是「没有完成」的状态：snapshotMessage 会把 streaming 记成 interrupted） */
export function saveStreamingDraft(chatId: string, message: QaMessage) {
	if (!browser) {
		return;
	}
	try {
		const draft: StreamingDraft = { chatId, message: snapshotMessage(message) };
		localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
	} catch {
		// 同上
	}
}

/** 上次生成到一半页面就没了（崩溃、被杀）：把草稿并回它所在的对话 */
function applyStreamingDraft(chats: QaChat[]) {
	let draft: StreamingDraft | null = null;
	try {
		const raw = localStorage.getItem(DRAFT_KEY);
		draft = raw ? (JSON.parse(raw) as StreamingDraft) : null;
	} catch {
		draft = null;
	}
	if (
		!draft?.message ||
		typeof draft.message.id !== 'string' ||
		typeof draft.message.content !== 'string'
	) {
		return;
	}
	const chat = chats.find((item) => item.id === draft.chatId);
	if (!chat) {
		return;
	}
	const index = chat.messages.findIndex((message) => message.id === draft.message.id);
	if (index === -1) {
		chat.messages.push(snapshotMessage(draft.message));
	} else if (draft.message.content.length > chat.messages[index].content.length) {
		chat.messages[index] = snapshotMessage(draft.message);
	}
}
