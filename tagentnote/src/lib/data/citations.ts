import {
	findCollection,
	findFileInCollections,
	sourceHref,
	toCitation,
	type Citation,
	type KnowledgeCollection,
	type KnowledgeFile,
	type SourceKind
} from '$lib/data/knowledge';

export type Locator = {
	chapter?: string;
	page?: string;
};

export type SearchHit = {
	id?: string;
	parentId?: string;
	title?: string;
	text?: string;
	notebookId?: string;
};

const asRecord = (value: unknown): Record<string, unknown> | null =>
	value && typeof value === 'object' && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: null;

const asString = (value: unknown) => (typeof value === 'string' ? value.trim() : '');

const STOP_WORDS = new Set([
	'什么',
	'哪个',
	'哪些',
	'怎么',
	'如何',
	'请问',
	'为什么',
	'为何',
	'是否',
	'一下',
	'这个',
	'那个',
	'一个',
	'哪里',
	'哪儿',
	'多少',
	'可以',
	'怎样',
	'还有',
	'如果',
	'因为',
	'所以',
	'但是',
	'然后',
	'以及',
	'或者',
	'不是',
	'没有',
	'问题',
	'帮我',
	'的',
	'了',
	'是',
	'在',
	'吗',
	'呢',
	'啊',
	'吧',
	'着',
	'和',
	'与',
	'或',
	'及',
	'等',
	'这',
	'那',
	'就',
	'都',
	'也',
	'还',
	'很',
	'太',
	'不',
	'么',
	'到',
	'对',
	'为',
	'以',
	'把',
	'被',
	'从',
	'并',
	'你',
	'我',
	'他',
	'它',
	'们',
	'请',
	'哪'
]);

const WEAK_TERMS = new Set([
	'系统',
	'方法',
	'模型',
	'内容',
	'基本',
	'概念',
	'介绍',
	'备份',
	'英文',
	'第四',
	'版本',
	'现代',
	'教材',
	'笔记',
	'来源',
	'检索',
	'知识',
	'课程',
	'实验',
	'指导',
	'指南',
	'城市',
	'位于',
	'属于',
	'the',
	'and',
	'for'
]);

const ALIASES: Record<string, string[]> = {
	文件: ['file', 'files'],
	文件系统: ['filesystem', 'file system'],
	磁盘: ['disk', 'disks'],
	进程: ['process', 'processes'],
	线程: ['thread', 'threads'],
	内存: ['memory'],
	操作系统: ['operating system'],
	仿真: ['simulation', 'simulate'],
	建模: ['modeling', 'modelling'],
	队列: ['queue', 'queuing'],
	网络: ['network', 'networks'],
	连续: ['continuous'],
	离散: ['discrete']
};

const expandAliases = (text: string) => {
	const lower = text.toLowerCase();
	const extra: string[] = [];

	for (const [zh, english] of Object.entries(ALIASES)) {
		if (lower.includes(zh) || english.some((item) => lower.includes(item))) {
			extra.push(zh, ...english);
		}
	}

	return extra.length > 0 ? `${lower} ${extra.join(' ')}` : lower;
};

export function contentTerms(text: string): string[] {
	let source = text.toLowerCase();
	const multi = [...STOP_WORDS]
		.filter((word) => word.length >= 2)
		.sort((a, b) => b.length - a.length);

	for (const word of multi) {
		source = source.split(word).join(' ');
	}

	const terms = new Set<string>();

	for (const word of source.match(/[a-z][a-z0-9]{2,}/g) ?? []) {
		if (!WEAK_TERMS.has(word) && !STOP_WORDS.has(word)) {
			terms.add(word);
		}
	}

	for (const run of source.match(/[\u4e00-\u9fff]+/g) ?? []) {
		let buffer = '';
		const flush = () => {
			if (buffer.length >= 2 && !WEAK_TERMS.has(buffer) && !STOP_WORDS.has(buffer)) {
				terms.add(buffer);
			}
			buffer = '';
		};

		for (const char of run) {
			if (STOP_WORDS.has(char)) {
				flush();
			} else {
				buffer += char;
			}
		}

		flush();
	}

	return [...terms];
}

export function isRelevantToQuery(source: string, question: string) {
	const terms = contentTerms(expandAliases(question)).filter((term) => term.length >= 2);

	if (terms.length === 0 || !source.trim()) {
		return false;
	}

	const hay = expandAliases(source);
	return terms.some((term) => hay.includes(term));
}

export function isCitationRelevant(citation: Citation, question: string) {
	return isRelevantToQuery(
		`${citation.collectionName} ${citation.title} ${citation.snippet ?? ''}`,
		question
	);
}

const pickString = (record: Record<string, unknown> | null, keys: string[]) => {
	if (!record) {
		return '';
	}

	for (const key of keys) {
		const value = asString(record[key]);

		if (value) {
			return value;
		}
	}

	return '';
};

const chineseChapter = (raw: string) => {
	const digits = raw.replace(/\s+/g, '');

	if (/^\d+$/.test(digits)) {
		return `第${Number(digits)}章`;
	}

	return `第${digits}章`;
};

export function formatLocator(locator: Locator) {
	return [locator.chapter, locator.page].filter(Boolean).join(' · ');
}

export function extractLocator(text: string): Locator {
	if (!text.trim()) {
		return {};
	}

	const chapterMatch =
		text.match(/第\s*([0-9零一二三四五六七八九十百]+)\s*章/) ||
		text.match(/CHAP(?:TER)?\.?\s*(\d+)/i) ||
		text.match(/Chapter\s+(\d+)/i);

	const pageRangeInName = text.match(/_(\d{1,4})\s*[-–—]\s*(\d{1,4})\.(?:pdf|docx?|pptx?)/i);
	const pageZh = text.match(/第\s*(\d{1,4})\s*(?:[-–—至到]\s*(\d{1,4})\s*)?页/);
	const pageEn =
		text.match(/\bpp?\.?\s*(\d{1,4})(?:\s*[-–]\s*(\d{1,4}))?/i) ||
		text.match(/\bPage(?:s)?\s+(\d{1,4})(?:\s*[-–]\s*(\d{1,4}))?/i);
	const runningHeader = text.match(/(?:^|\n)\s*(\d{1,4})\s+[A-Z][A-Za-z][^\n]{0,40}\s+CHAP/i);

	let page: string | undefined;

	if (pageZh) {
		page = pageZh[2] ? `第${pageZh[1]}–${pageZh[2]}页` : `第${pageZh[1]}页`;
	} else if (pageEn) {
		page = pageEn[2] ? `第${pageEn[1]}–${pageEn[2]}页` : `第${pageEn[1]}页`;
	} else if (pageRangeInName) {
		page = `第${pageRangeInName[1]}–${pageRangeInName[2]}页`;
	} else if (runningHeader) {
		page = `第${runningHeader[1]}页`;
	}

	return {
		chapter: chapterMatch ? chineseChapter(chapterMatch[1]) : undefined,
		page
	};
}

export function locatorFromPassage(fullText: string, query: string): Locator {
	if (!isRelevantToQuery(fullText, query)) {
		return {};
	}

	const needles = contentTerms(query)
		.flatMap((term) => [term, ...(ALIASES[term] ?? [])])
		.filter((item) => item.length >= 2)
		.slice(0, 12);

	const lower = fullText.toLowerCase();

	for (const needle of needles) {
		const index = lower.indexOf(needle.toLowerCase());

		if (index < 0) {
			continue;
		}

		const window = fullText.slice(Math.max(0, index - 280), index + needle.length + 280);
		const local = extractLocator(window);

		if (local.chapter || local.page) {
			return local;
		}
	}

	return {};
}

const kindFromId = (id: string, fallback: SourceKind = 'file'): SourceKind => {
	if (id.startsWith('note:')) {
		return 'note';
	}

	if (id.startsWith('http://') || id.startsWith('https://')) {
		return 'web';
	}

	return fallback;
};

const cleanTitle = (title: string) =>
	title
		.replace(/（备份）/g, '')
		.replace(/\.[a-z0-9]+$/i, '')
		.trim() || title;

const mergeLocator = (...parts: Locator[]): Locator => {
	const merged: Locator = {};

	for (const part of parts) {
		if (!merged.chapter && part.chapter) {
			merged.chapter = part.chapter;
		}
		if (!merged.page && part.page) {
			merged.page = part.page;
		}
	}

	return merged;
};

/**
 * 后端随回答返回的出处（basic-agent 的 app/rag/citations.py）。
 * 教材和论文不在任何笔记本里，单独成条；笔记本来源（kind: notebook）仍按 id 对回前端的笔记本。
 */
function backendCitation(record: Record<string, unknown>): Citation | null {
	const snippet = asString(record.snippet).slice(0, 180) || undefined;

	if (record.kind === 'textbook') {
		const chapter = typeof record.chapter === 'number' ? `第${record.chapter}章` : undefined;
		const page = typeof record.page === 'number' ? `第${record.page}页` : undefined;
		const fileId = asString(record.id) || 'textbook';
		return {
			id: fileId,
			collectionId: 'textbook',
			collectionName: '课程教材',
			fileId,
			title: asString(record.title) || '课程教材',
			kind: 'file',
			// 教材不在笔记本里，没有可以打开的页面
			href: '',
			chapter,
			page,
			locator: formatLocator({ chapter, page }) || undefined,
			snippet,
			grounded: true
		};
	}

	if (record.kind === 'paper') {
		const title = asString(record.title);
		if (!title) {
			return null;
		}
		const href = asString(record.href);
		const fileId = asString(record.id) || `reference:${title}`;
		return {
			id: fileId,
			collectionId: 'references',
			collectionName: '参考文献',
			fileId,
			title,
			kind: 'paper',
			// 期刊官网的文章页；只认网页地址
			href: /^https?:\/\//i.test(href) ? href : '',
			locator: asString(record.citation) || undefined,
			snippet,
			grounded: true
		};
	}

	return null;
}

export function citationFromUnknown(
	raw: unknown,
	index: number,
	collections: KnowledgeCollection[],
	notebook?: { id: string; name: string } | null
): Citation | null {
	if (typeof raw === 'string') {
		const locator = extractLocator(raw);
		const matched = matchFileFromText(raw, collections, notebook?.id);
		if (
			matched &&
			isRelevantToQuery(`${matched.collection.name} ${matched.file.title} ${raw}`, raw)
		) {
			return toCitation(matched.collection, matched.file, 'qa', {
				...locator,
				locator: formatLocator(locator) || undefined,
				snippet: raw.slice(0, 180)
			});
		}

		return null;
	}

	const record = asRecord(raw);

	if (!record) {
		return null;
	}

	const fromBackend = backendCitation(record);
	if (fromBackend) {
		return fromBackend;
	}
	// 后端说回答用到了的笔记本来源
	const grounded = record.kind === 'notebook' ? { grounded: true } : {};

	const fileId =
		pickString(record, ['fileId', 'file_id', 'source_id', 'sourceId', 'id', 'parent_id']) || '';
	const title =
		pickString(record, ['title', 'name', 'filename', 'file_name', 'source', 'document']) || '';
	const snippet = pickString(record, ['snippet', 'content', 'text', 'quote']);
	const locator = mergeLocator(
		extractLocator([title, snippet, pickString(record, ['locator', 'chapter', 'page'])].join('\n')),
		{
			chapter: asString(record.chapter) ? chineseChapter(asString(record.chapter)) : undefined,
			page: (() => {
				const page = record.page ?? record.page_number ?? record.pageNumber;
				if (typeof page === 'number') {
					return `第${page}页`;
				}
				const text = asString(page);
				return text ? extractLocator(`第${text}页`).page || extractLocator(text).page : undefined;
			})()
		}
	);

	const found =
		(fileId ? findFileInCollections(fileId, collections) : null) ||
		matchFileFromText(`${title}\n${snippet}`, collections, notebook?.id);

	if (found) {
		return {
			...toCitation(found.collection, found.file, 'qa', {
				...locator,
				locator: formatLocator(locator) || undefined,
				snippet: snippet.slice(0, 180) || undefined
			}),
			...grounded
		};
	}

	const collection =
		(notebook ? findCollection(notebook.id, collections) : null) ||
		(asString(record.collectionId)
			? findCollection(asString(record.collectionId), collections)
			: null) ||
		(asString(record.notebook_id)
			? findCollection(asString(record.notebook_id), collections)
			: null);

	if (!collection && !notebook && !fileId && !title) {
		return null;
	}

	const owner = collection ?? {
		id: notebook?.id || 'knowledge',
		name: notebook?.name || '知识库',
		description: '',
		files: [] as KnowledgeFile[]
	};

	return {
		id: fileId || `citation-${index}`,
		collectionId: owner.id,
		collectionName: owner.name,
		fileId,
		title: cleanTitle(title) || '检索来源',
		kind: kindFromId(fileId),
		href: sourceHref(owner.id, fileId, 'qa'),
		...locator,
		locator: formatLocator(locator) || undefined,
		snippet: snippet.slice(0, 180) || undefined,
		...grounded
	};
}

export function matchFileFromText(
	text: string,
	collections: KnowledgeCollection[],
	notebookId?: string
) {
	const scoped = notebookId
		? collections.filter((collection) => collection.id === notebookId)
		: collections;
	let best: { collection: KnowledgeCollection; file: KnowledgeFile; score: number } | null = null;

	for (const collection of scoped) {
		for (const file of collection.files) {
			const label = `${collection.name} ${file.title}`;

			if (!isRelevantToQuery(label, text) && !isRelevantToQuery(text, file.title)) {
				continue;
			}

			const hay = expandAliases(label);
			const score = contentTerms(text).filter((term) => hay.includes(term)).length;

			if (score > 0 && (!best || score > best.score)) {
				best = { collection, file, score };
			}
		}
	}

	return best;
}

export function citationsFromRetrievedContext(
	context: string,
	collections: KnowledgeCollection[],
	notebook?: { id: string; name: string } | null,
	question = ''
): Citation[] {
	if (!context.trim()) {
		return [];
	}

	const chunks = context
		.split(/\n(?=\[?来源|Source\s*\d+|#{1,3}\s*来源|\*\*来源)/i)
		.flatMap((block) => block.split(/\n{2,}/))
		.map((item) => item.trim())
		.filter((item) => item.length > 20);

	const blocks = chunks.length > 0 ? chunks.slice(0, 6) : [context.slice(0, 1200)];
	const citations: Citation[] = [];

	blocks.forEach((block, index) => {
		if (question && !isRelevantToQuery(block, question)) {
			return;
		}

		const citation = citationFromUnknown(block, index, collections, notebook);

		if (citation) {
			citations.push(citation);
		}
	});

	return dedupeCitations(citations);
}

export function citationsFromSearchHits(
	hits: SearchHit[],
	collections: KnowledgeCollection[],
	notebook?: { id: string; name: string } | null,
	question = ''
): Citation[] {
	return dedupeCitations(
		hits
			.filter((hit) => !notebook || !hit.notebookId || hit.notebookId === notebook.id)
			.filter((hit) => {
				if (!question) {
					return false;
				}

				return isRelevantToQuery(`${hit.title ?? ''} ${hit.text ?? ''}`, question);
			})
			.map((hit, index) =>
				citationFromUnknown(
					{
						id: hit.parentId || hit.id,
						title: hit.title,
						text: hit.text,
						notebook_id: hit.notebookId
					},
					index,
					collections,
					notebook
				)
			)
			.filter((item): item is Citation => item !== null)
	);
}

export function citationsFromAnswer(
	question: string,
	collections: KnowledgeCollection[],
	notebook?: { id: string; name: string } | null
): Citation[] {
	if (!question.trim()) {
		return [];
	}

	const matched = matchFileFromText(question, collections, notebook?.id);

	if (!matched) {
		return [];
	}

	const locator = extractLocator(`${matched.file.title} ${question}`);

	return [
		toCitation(matched.collection, matched.file, 'qa', {
			...locator,
			locator: formatLocator(locator) || undefined
		})
	];
}

export function mergeCitations(...lists: Citation[][]) {
	return dedupeCitations(lists.flat()).slice(0, 6);
}

export function buildQaCitations(input: {
	agentCitations?: unknown[];
	retrievedContext?: string;
	searchHits?: SearchHit[];
	question?: string;
	answer: string;
	collections: KnowledgeCollection[];
	notebook?: { id: string; name: string } | null;
}) {
	const question = input.question?.trim() ?? '';
	const fromAgent = (input.agentCitations ?? [])
		.map((item, index) => citationFromUnknown(item, index, input.collections, input.notebook))
		.filter((item): item is Citation => item !== null);

	const merged = mergeCitations(
		fromAgent,
		citationsFromRetrievedContext(
			input.retrievedContext ?? '',
			input.collections,
			input.notebook,
			question
		),
		citationsFromSearchHits(input.searchHits ?? [], input.collections, input.notebook, question),
		citationsFromAnswer(question, input.collections, input.notebook)
	);

	return question
		? merged.filter(
				(citation) =>
					citation.grounded ||
					isCitationRelevant(citation, question) ||
					citation.fileId.startsWith('source:')
			)
		: [];
}

export async function enrichCitationsWithPages(
	citations: Citation[],
	question: string,
	getText: (fileId: string) => Promise<string>
) {
	const maybeEnglish = contentTerms(question).some((term) => Boolean(ALIASES[term]));
	// 先过一遍：哪些原样留下、哪些丢掉、哪些要取原文补页码
	const steps: { citation: Citation; needsText: boolean }[] = [];

	for (const citation of citations) {
		// 教材、论文：后端已经给了章页 / 期刊出处，也不在笔记本里，没有原文可取
		if (citation.grounded && !citation.fileId.startsWith('source:')) {
			steps.push({ citation, needsText: false });
			continue;
		}

		const titleRelevant = isCitationRelevant(citation, question);

		if (!citation.fileId.startsWith('source:')) {
			if (titleRelevant) {
				steps.push({ citation, needsText: false });
			}
			continue;
		}

		if ((titleRelevant || citation.grounded) && citation.chapter && citation.page) {
			steps.push({ citation, needsText: false });
			continue;
		}

		// 回答确实用到的笔记本来源一律留下，这里只是去补页码
		if (!citation.grounded && !titleRelevant && !maybeEnglish) {
			continue;
		}

		steps.push({ citation, needsText: true });
	}

	// 要取原文的几条同时去取：以前一条等一条，五条出处就是五个来回，常常把 4 秒的上限等满
	const texts = new Map<string, Promise<string>>();
	for (const { citation, needsText } of steps) {
		if (needsText && !texts.has(citation.fileId)) {
			texts.set(
				citation.fileId,
				getText(citation.fileId).catch(() => '')
			);
		}
	}

	const kept: Citation[] = [];
	for (const { citation, needsText } of steps) {
		if (!needsText) {
			kept.push(citation);
			continue;
		}

		const text = (await texts.get(citation.fileId)) ?? '';
		const corpus = `${citation.title} ${citation.snippet ?? ''} ${text}`;

		if (!citation.grounded && !isRelevantToQuery(corpus, question)) {
			continue;
		}

		const locator = mergeLocator(
			locatorFromPassage(text, question),
			{ chapter: citation.chapter, page: citation.page },
			extractLocator(citation.title)
		);
		citation.chapter = locator.chapter;
		citation.page = locator.page;
		citation.locator = formatLocator(locator) || citation.locator;
		citation.id = `${citation.collectionId}:${citation.fileId}${citation.locator ? `:${citation.locator}` : ''}`;
		kept.push(citation);
	}

	return dedupeCitations(kept);
}

function dedupeCitations(citations: Citation[]) {
	const seen = new Set<string>();
	const result: Citation[] = [];

	for (const citation of citations) {
		const key = `${citation.fileId || citation.title}|${citation.locator || ''}`;

		if (seen.has(key)) {
			continue;
		}

		seen.add(key);
		result.push(citation);
	}

	return result;
}
