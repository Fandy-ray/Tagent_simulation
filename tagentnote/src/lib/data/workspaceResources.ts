import { browser } from '$app/environment';
import { readPersonalCache, writePersonalCache } from '$lib/apis/auth';

export type WorkspaceView = '' | 'created' | 'shared';

export type WorkspaceModel = {
	id: string;
	name: string;
	baseModelId?: string | null;
	description?: string;
	system?: string;
	tags?: string[];
	isActive?: boolean;
	params?: Record<string, unknown>;
	meta?: {
		hidden?: boolean;
		profileImageUrl?: string;
		knowledgeIds?: string[];
		knowledgeFiles?: { id: string; name: string; type: 'file'; size?: number }[];
		toolIds?: string[];
		skillIds?: string[];
		capabilities?: Record<string, boolean>;
		builtinTools?: Record<string, boolean>;
		defaultFeatureIds?: string[];
		suggestionPrompts?: { content: string; title: [string, string] }[] | null;
		ttsVoice?: string;
	};
	owner?: 'you' | 'shared' | 'system';
	createdAt: number;
	updatedAt: number;
};

export type KnowledgeDoc = {
	id: string;
	name: string;
	content: string;
	createdAt: number;
};

export type WorkspaceKnowledge = {
	id: string;
	name: string;
	description?: string;
	notebookId?: string | null;
	docs: KnowledgeDoc[];
	writeAccess?: boolean;
	owner?: 'you' | 'shared';
	createdAt: number;
	updatedAt: number;
};

export type PromptHistoryEntry = {
	id: string;
	commitMessage: string;
	content: string;
	createdAt: number;
};

export type WorkspacePrompt = {
	id: string;
	title: string;
	command: string;
	content: string;
	tags?: string[];
	isActive?: boolean;
	owner?: 'you' | 'shared';
	history?: PromptHistoryEntry[];
	createdAt: number;
	updatedAt: number;
};

export type WorkspaceSkill = {
	id: string;
	name: string;
	description?: string;
	content: string;
	isActive?: boolean;
	owner?: 'you' | 'shared';
	createdAt: number;
	updatedAt: number;
};

export type WorkspaceTool = {
	id: string;
	name: string;
	description?: string;
	content: string;
	meta?: { manifest?: Record<string, unknown> };
	owner?: 'you' | 'shared';
	createdAt: number;
	updatedAt: number;
};

type Bundle = {
	models: WorkspaceModel[];
	knowledge: WorkspaceKnowledge[];
	prompts: WorkspacePrompt[];
	skills: WorkspaceSkill[];
	tools: WorkspaceTool[];
};

const now = () => Date.now();

const seed = (): Bundle => {
	const t = now();
	return {
		models: [],
		knowledge: [
			{
				id: 'kb-course-sim',
				name: '离散事件仿真教材',
				description: '课程答疑用知识集合（可绑定 OpenNoteBook）',
				notebookId: null,
				docs: [],
				writeAccess: true,
				owner: 'you',
				createdAt: t,
				updatedAt: t
			}
		],
		prompts: [
			{
				id: 'prompt-explain',
				title: '概念解释',
				command: '/explain',
				content: '请用通俗语言解释：{{topic}}\n并给出一个仿真课相关的例子。',
				tags: ['教学'],
				isActive: true,
				owner: 'you',
				createdAt: t,
				updatedAt: t
			},
			{
				id: 'prompt-paper-outline',
				title: '论文大纲',
				command: '/outline',
				content: '请为题目「{{title}}」生成课程论文大纲，包含摘要、相关工作、方法、实验与结论。',
				tags: ['论文'],
				isActive: true,
				owner: 'you',
				createdAt: t,
				updatedAt: t
			}
		],
		skills: [
			{
				id: 'skill-citation',
				name: '教材引用助手',
				description: '回答时优先引用笔记本/教材段落',
				content:
					'---\nname: citation-helper\ndescription: Prefer textbook citations\n---\n\nWhen answering course questions, cite notebook sources when available.',
				isActive: true,
				owner: 'you',
				createdAt: t,
				updatedAt: t
			}
		],
		tools: [
			{
				id: 'tool-calculator',
				name: '计算器',
				description: '基础数值计算',
				content:
					'class Tools:\n    def calculator(self, expression: str) -> str:\n        """Evaluate a math expression."""\n        return str(eval(expression))\n',
				meta: { manifest: { name: 'calculator' } },
				owner: 'you',
				createdAt: t,
				updatedAt: t
			},
			{
				id: 'tool-time',
				name: '时间查询',
				description: '返回当前本地时间',
				content:
					'class Tools:\n    def current_time(self) -> str:\n        """Return current local time."""\n        from datetime import datetime\n        return datetime.now().isoformat()\n',
				meta: { manifest: { name: 'time' } },
				owner: 'you',
				createdAt: t,
				updatedAt: t
			}
		]
	};
};

const empty = (): Bundle => ({
	models: [],
	knowledge: [],
	prompts: [],
	skills: [],
	tools: []
});

export function loadWorkspace(): Bundle {
	if (!browser) return empty();
	try {
		const raw = readPersonalCache('workspace');
		if (!raw) {
			const initial = seed();
			writePersonalCache('workspace', JSON.stringify(initial));
			return initial;
		}
		const parsed = JSON.parse(raw) as Partial<Bundle>;
		return {
			models: Array.isArray(parsed.models) ? parsed.models : [],
			knowledge: Array.isArray(parsed.knowledge) ? parsed.knowledge : [],
			prompts: Array.isArray(parsed.prompts) ? parsed.prompts : [],
			skills: Array.isArray(parsed.skills) ? parsed.skills : [],
			tools: Array.isArray(parsed.tools) ? parsed.tools : []
		};
	} catch {
		return seed();
	}
}

export function saveWorkspace(bundle: Bundle) {
	if (!browser) return;
	writePersonalCache('workspace', JSON.stringify(bundle));
}

const patch = <K extends keyof Bundle>(key: K, items: Bundle[K]) => {
	const bundle = loadWorkspace();
	bundle[key] = items;
	saveWorkspace(bundle);
	return items;
};

export const slugify = (text: string) =>
	text
		.trim()
		.toLowerCase()
		.replace(/\s+/g, '-')
		.replace(/[^a-z0-9\u4e00-\u9fff-_]/g, '')
		.slice(0, 64) || `item-${Date.now()}`;

export const filterByView = <T extends { owner?: string }>(items: T[], view: WorkspaceView) => {
	if (view === 'created') return items.filter((i) => (i.owner ?? 'you') === 'you');
	if (view === 'shared') return items.filter((i) => i.owner === 'shared');
	return items;
};

export const matchQuery = (haystack: string, query: string) => {
	const q = query.trim().toLowerCase();
	if (!q) return true;
	return haystack.toLowerCase().includes(q);
};

// —— Models ——
export function listModels() {
	return loadWorkspace().models.sort((a, b) => b.updatedAt - a.updatedAt);
}
export function getModel(id: string) {
	return listModels().find((m) => m.id === id) ?? null;
}
export function upsertModel(model: WorkspaceModel) {
	const items = listModels();
	const idx = items.findIndex((m) => m.id === model.id);
	if (idx >= 0) items[idx] = { ...model, updatedAt: now() };
	else items.unshift({ ...model, createdAt: model.createdAt || now(), updatedAt: now() });
	return patch('models', items);
}
export function deleteModel(id: string) {
	return patch(
		'models',
		listModels().filter((m) => m.id !== id)
	);
}

// —— Knowledge ——
export function listKnowledge() {
	return loadWorkspace().knowledge.sort((a, b) => b.updatedAt - a.updatedAt);
}
export function getKnowledge(id: string) {
	return listKnowledge().find((k) => k.id === id) ?? null;
}
export function upsertKnowledge(item: WorkspaceKnowledge) {
	const items = listKnowledge();
	const idx = items.findIndex((k) => k.id === item.id);
	if (idx >= 0) items[idx] = { ...item, updatedAt: now() };
	else items.unshift({ ...item, createdAt: item.createdAt || now(), updatedAt: now() });
	return patch('knowledge', items);
}
export function deleteKnowledge(id: string) {
	return patch(
		'knowledge',
		listKnowledge().filter((k) => k.id !== id)
	);
}

// —— Prompts ——
export function listPrompts() {
	return loadWorkspace().prompts.sort((a, b) => b.updatedAt - a.updatedAt);
}
export function getPrompt(id: string) {
	return listPrompts().find((p) => p.id === id) ?? null;
}
export function upsertPrompt(item: WorkspacePrompt) {
	const items = listPrompts();
	const idx = items.findIndex((p) => p.id === item.id);
	if (idx >= 0) items[idx] = { ...item, updatedAt: now() };
	else items.unshift({ ...item, createdAt: item.createdAt || now(), updatedAt: now() });
	return patch('prompts', items);
}
export function deletePrompt(id: string) {
	return patch(
		'prompts',
		listPrompts().filter((p) => p.id !== id)
	);
}

// —— Skills ——
export function listSkills() {
	return loadWorkspace().skills.sort((a, b) => b.updatedAt - a.updatedAt);
}
export function getSkill(id: string) {
	return listSkills().find((s) => s.id === id) ?? null;
}
export function upsertSkill(item: WorkspaceSkill) {
	const items = listSkills();
	const idx = items.findIndex((s) => s.id === item.id);
	if (idx >= 0) items[idx] = { ...item, updatedAt: now() };
	else items.unshift({ ...item, createdAt: item.createdAt || now(), updatedAt: now() });
	return patch('skills', items);
}
export function deleteSkill(id: string) {
	return patch(
		'skills',
		listSkills().filter((s) => s.id !== id)
	);
}

// —— Tools ——
export function listTools() {
	return loadWorkspace().tools.sort((a, b) => b.updatedAt - a.updatedAt);
}
export function getTool(id: string) {
	return listTools().find((t) => t.id === id) ?? null;
}
export function upsertTool(item: WorkspaceTool) {
	const items = listTools();
	const idx = items.findIndex((t) => t.id === item.id);
	if (idx >= 0) items[idx] = { ...item, updatedAt: now() };
	else items.unshift({ ...item, createdAt: item.createdAt || now(), updatedAt: now() });
	return patch('tools', items);
}
export function deleteTool(id: string) {
	return patch(
		'tools',
		listTools().filter((t) => t.id !== id)
	);
}

export function downloadJson(filename: string, data: unknown) {
	const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
	const href = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = href;
	a.download = filename;
	a.click();
	URL.revokeObjectURL(href);
}

export function relativeTime(ts: number) {
	const diff = Date.now() - ts;
	const m = Math.floor(diff / 60000);
	if (m < 1) return '刚刚';
	if (m < 60) return `${m} 分钟前`;
	const h = Math.floor(m / 60);
	if (h < 24) return `${h} 小时前`;
	const d = Math.floor(h / 24);
	if (d < 30) return `${d} 天前`;
	return new Date(ts).toLocaleDateString('zh-CN');
}
