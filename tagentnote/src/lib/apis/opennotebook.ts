import { env } from '$env/dynamic/public';

import { createTtlCache } from '$lib/data/ttlCache';
import {
	type KnowledgeCollection,
	type KnowledgeFile,
	type SourceKind,
	type SourceStatus
} from '$lib/data/knowledge';

type NotebookListItem = {
	id: string;
	name: string;
	description?: string | null;
	archived?: boolean;
	source_count?: number;
	note_count?: number;
};

type SourceListItem = {
	id: string;
	title?: string | null;
	status?: string | null;
	asset?: {
		file_path?: string | null;
		url?: string | null;
	} | null;
};

type NoteListItem = {
	id: string;
	title?: string | null;
	name?: string | null;
};

const DEFAULT_API_URL = 'http://localhost:5055';

export function getOpenNotebookApiUrl() {
	const explicit = env.PUBLIC_OPENNOTEBOOK_API_URL?.trim();

	if (explicit) {
		return explicit.replace(/\/$/, '');
	}

	const ui = env.PUBLIC_OPENNOTEBOOK_URL?.trim();

	if (!ui) {
		return DEFAULT_API_URL;
	}

	try {
		const url = new URL(ui.includes('://') ? ui : `http://${ui}`);

		if (url.port === '8502' || url.port === '') {
			url.port = '5055';
		}

		url.pathname = '';
		url.search = '';
		url.hash = '';

		return url.toString().replace(/\/$/, '');
	} catch {
		return DEFAULT_API_URL;
	}
}

const fileNameFromPath = (path: string) => {
	const trimmed = path.trim();
	const parts = trimmed.split(/[\\/]/);

	return parts[parts.length - 1] || trimmed;
};

const sourceTitle = (source: SourceListItem) => {
	const title = source.title?.trim();

	if (title && title !== 'Processing...') {
		return title;
	}

	const path = source.asset?.file_path || source.asset?.url || '';

	return fileNameFromPath(path) || '未命名来源';
};

const sourceKind = (source: SourceListItem): SourceKind => {
	if (source.asset?.url) {
		return 'web';
	}

	return 'file';
};

const toSourceFile = (source: SourceListItem): KnowledgeFile => {
	const rawStatus = source.status?.trim().toLowerCase() || 'completed';
	const failed = ['failed', 'failure', 'error', 'download_failed', 'download-failed'].includes(
		rawStatus
	);
	const processing = !failed && rawStatus !== 'completed';
	const status: SourceStatus = failed ? 'failed' : processing ? 'processing' : 'ready';
	const title = sourceTitle(source);

	return {
		id: source.id,
		title: failed ? `${title}（下载失败）` : processing ? `${title}（处理中）` : title,
		kind: sourceKind(source),
		status
	};
};

const toNoteFile = (note: NoteListItem): KnowledgeFile => ({
	id: note.id,
	title: note.title?.trim() || note.name?.trim() || '未命名笔记',
	kind: 'note'
});

export type NotebookSummary = {
	id: string;
	name: string;
	description?: string | null;
	note_count?: number;
	/** 供前端组件使用的驼峰字段；由 listNotebooks 统一填充。 */
	noteCount?: number;
};

export type CreatedNote = {
	id: string;
	title: string | null;
	content: string | null;
};

const fetchJson = async <T>(path: string, signal?: AbortSignal): Promise<T> => {
	const response = await fetch(`${getOpenNotebookApiUrl()}${path}`, { signal });

	if (!response.ok) {
		throw new Error(`OpenNoteBook ${path} ${response.status}`);
	}

	return (await response.json()) as T;
};

const postJson = async <T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> => {
	const response = await fetch(`${getOpenNotebookApiUrl()}${path}`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(body),
		signal
	});

	if (!response.ok) {
		const detail = await response.text().catch(() => '');
		throw new Error(`OpenNoteBook ${path} ${response.status}${detail ? `: ${detail}` : ''}`);
	}

	return (await response.json()) as T;
};

export async function listNotebooks(signal?: AbortSignal): Promise<NotebookSummary[]> {
	const notebooks = await fetchJson<NotebookListItem[]>(
		'/api/notebooks?archived=false&order_by=updated+desc',
		signal
	);

	// 列表里带了 note_count 就直接用；只有没带（老版本镜像）才逐本去数——
	// 以前每本都再请求一次笔记列表，十本笔记本就是 11 个请求，打开答疑页、笔记页都要等它
	return Promise.all(
		notebooks.map(async (notebook) => {
			const reportedCount = notebook.note_count;
			const reported =
				typeof reportedCount === 'number' && Number.isFinite(reportedCount) ? reportedCount : null;
			const count =
				reported ??
				(await fetchJson<NoteListItem[]>(
					`/api/notes?notebook_id=${encodeURIComponent(notebook.id)}`,
					signal
				)
					.then((notes) => notes.length)
					.catch(() => 0));

			return {
				...notebook,
				note_count: count,
				noteCount: count
			};
		})
	);
}

export async function createNotebook(name: string, description = '') {
	return postJson<NotebookSummary>('/api/notebooks', {
		name: name.trim(),
		description
	});
}

export async function createNote(input: {
	title: string;
	content: string;
	notebookId: string;
	noteType?: 'human' | 'ai';
}) {
	return postJson<CreatedNote>('/api/notes', {
		title: input.title,
		content: input.content,
		notebook_id: input.notebookId,
		note_type: input.noteType ?? 'ai'
	});
}

export type KnowledgeSearchHit = {
	id?: string;
	parentId?: string;
	title?: string;
	text?: string;
	notebookId?: string;
};

type SourceDetail = SourceListItem & {
	full_text?: string | null;
	notebooks?: string[] | null;
};

const asRecord = (value: unknown): Record<string, unknown> | null =>
	value && typeof value === 'object' && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: null;

const asString = (value: unknown) => (typeof value === 'string' ? value.trim() : '');

export async function searchKnowledge(
	query: string,
	options?: { limit?: number; signal?: AbortSignal }
): Promise<KnowledgeSearchHit[]> {
	const keyword = query.trim();

	if (!keyword) {
		return [];
	}

	const payload = await postJson<{ results?: unknown[] }>(
		'/api/search',
		{
			query: keyword,
			type: 'text',
			limit: options?.limit ?? 8,
			search_sources: true,
			search_notes: true
		},
		options?.signal
	).catch(() => ({ results: [] }));

	const rows = Array.isArray(payload.results) ? payload.results : [];

	return rows
		.map((item): KnowledgeSearchHit | null => {
			const row = asRecord(item);
			if (!row) {
				return null;
			}

			const parent = asRecord(row.parent);
			const matches = Array.isArray(row.matches) ? row.matches : [];
			const matchText = matches
				.map((match) => asString(asRecord(match)?.text) || asString(asRecord(match)?.content))
				.filter(Boolean)
				.join('\n');

			const hit: KnowledgeSearchHit = {
				id: asString(row.id) || undefined,
				parentId: asString(row.parent_id) || asString(parent?.id) || asString(row.id) || undefined,
				title: asString(row.title) || asString(parent?.title) || asString(row.name) || undefined,
				text:
					matchText ||
					asString(row.content) ||
					asString(row.text) ||
					asString(row.snippet) ||
					undefined,
				notebookId: asString(row.notebook_id) || undefined
			};

			if (!hit.id && !hit.title) {
				return null;
			}

			return hit;
		})
		.filter((item): item is KnowledgeSearchHit => item !== null);
}

export async function getSourceText(sourceId: string, signal?: AbortSignal) {
	if (!sourceId.startsWith('source:')) {
		return '';
	}

	const source = await fetchJson<SourceDetail>(
		`/api/sources/${encodeURIComponent(sourceId)}`,
		signal
	).catch(() => null);

	return source?.full_text?.trim() || '';
}

/** 一条笔记的正文（答疑输入框里把笔记当附件引用时用）。取不到返回空串 */
export async function getNoteText(noteId: string, signal?: AbortSignal) {
	const note = await fetchJson<{ content?: string | null }>(
		`/api/notes/${encodeURIComponent(noteId)}`,
		signal
	).catch(() => null);
	return note?.content?.trim() || '';
}

/**
 * 列一遍笔记本要 1 + 2N 个请求（笔记本、每本的来源、每本的笔记）。
 * 答疑页每次挂载都会调，页面来回切时整轮重发——内容又不会秒秒钟变，缓存十几秒。
 * 新建/删除笔记本后调 invalidateNotebookKnowledge() 立刻见新的。
 */
const knowledgeCache = createTtlCache<KnowledgeCollection[]>();

export function invalidateNotebookKnowledge(): void {
	knowledgeCache.invalidate();
}

export function listNotebookKnowledge(signal?: AbortSignal): Promise<KnowledgeCollection[]> {
	// 共享的那次请求**不绑**任何调用方的 signal：几个组件共用同一个 Promise，
	// 绑了的话谁先卸载一 abort，别人的加载也跟着失败
	// （实测路径：KnowledgeCombobox 传了 signal，答疑页和笔记本页没传，
	// 三者拿到的是同一个 Promise）。
	// 调用方的 signal 只负责让**它自己**不再等下去。
	const shared = knowledgeCache.get(() => loadNotebookKnowledge());
	if (!signal) {
		return shared;
	}
	if (signal.aborted) {
		return Promise.reject(new DOMException('Aborted', 'AbortError'));
	}
	return new Promise((resolve, reject) => {
		const stop = () => reject(new DOMException('Aborted', 'AbortError'));
		signal.addEventListener('abort', stop, { once: true });
		shared.then(resolve, reject).finally(() => signal.removeEventListener('abort', stop));
	});
}

async function loadNotebookKnowledge(signal?: AbortSignal): Promise<KnowledgeCollection[]> {
	const notebooks = await fetchJson<NotebookListItem[]>(
		'/api/notebooks?archived=false&order_by=updated+desc',
		signal ?? new AbortController().signal
	);

	const collections = await Promise.all(
		notebooks.map(async (notebook) => {
			const [sources, notes] = await Promise.all([
				fetchJson<SourceListItem[]>(
					`/api/sources?notebook_id=${encodeURIComponent(notebook.id)}&limit=100&sort_by=updated&sort_order=desc`,
					signal ?? new AbortController().signal
				).catch(() => [] as SourceListItem[]),
				fetchJson<NoteListItem[]>(
					`/api/notes?notebook_id=${encodeURIComponent(notebook.id)}`,
					signal ?? new AbortController().signal
				).catch(() => [] as NoteListItem[])
			]);

			return {
				id: notebook.id,
				name: notebook.name,
				description: notebook.description?.trim() || 'OpenNoteBook 笔记本',
				files: [...sources.map(toSourceFile), ...notes.map(toNoteFile)]
			};
		})
	);

	return collections;
}
