/**
 * 管理员面板用到的 basic-agent 接口：学习记录统计、反馈、知识库、数据库。模型登记在 model-providers.ts。
 *
 * 全都要管理口令（TAgent重写版/.env.runtime 里的 AGENT_ADMIN_TOKEN，启动脚本会自动生成），随
 * X-Agent-Admin-Token 头发出去。口令默认只放在内存里（adminToken）：在管理员面板里来回切页不用重输，
 * 刷新或关掉页面就没了——它能读到全班学生的原文和成绩，不该随便留在浏览器里。
 * 只有勾了「在这台电脑上记住」才写进 localStorage（部署到服务器后每次都上去查太麻烦），
 * 「锁定」和后端拒了这份口令时一起清掉。
 */
import { get, writable } from 'svelte/store';

import { agentBase } from '$lib/apis/agent';
import { adminToken, clearAdminToken } from '$lib/data/adminToken';

export {
	adminToken,
	clearAdminToken,
	rememberAdminToken,
	rememberedAdminToken,
	restoreAdminToken
} from '$lib/data/adminToken';

/** 口令被后端拒了（后端换了口令、重新生成过）时回到输入口令那一页，并在那里说明原因 */
export const adminLockReason = writable('');

export class AdminError extends Error {
	constructor(
		message: string,
		readonly status: number,
		readonly code?: string
	) {
		super(message);
		this.name = 'AdminError';
	}
}

function explain(status: number, payload: unknown): AdminError {
	const error = (payload as { error?: { message?: string; code?: string } })?.error;
	const code = error?.code;
	const message = error?.message ?? '';
	if (code === 'admin_token_not_configured') {
		return new AdminError(
			'后端还没有管理口令：跑一次启动脚本（start.command / start.bat）会自动生成。',
			status,
			code
		);
	}
	if (status === 403) {
		return new AdminError(
			'管理口令不对。它在 TAgent重写版/.env.runtime 里，AGENT_ADMIN_TOKEN= 后面那一串。',
			status,
			code ?? 'forbidden'
		);
	}
	if (code === 'learning_store_unavailable') {
		return new AdminError(
			'学习记录库没有启用（LEARNING_STORE=0，或启动时没能打开数据库文件）。',
			status,
			code
		);
	}
	if (status === 502 || status === 503 || status === 504) {
		return new AdminError('basic-agent 没有响应：它可能没有启动。', status, code);
	}
	return new AdminError(
		message ? `请求失败（${status}）：${message}` : `请求失败（${status}）`,
		status,
		code
	);
}

async function adminRequest<T>(path: string, method = 'GET', token?: string): Promise<T> {
	const value = (token ?? get(adminToken)).trim();
	if (!value) {
		throw new AdminError('先输入管理口令。', 403, 'forbidden');
	}
	let response: Response;
	try {
		response = await fetch(`${agentBase()}${path}`, {
			method,
			headers: { 'X-Agent-Admin-Token': value }
		});
	} catch {
		throw new AdminError('连不上 basic-agent，确认它已经启动。', 0);
	}
	const payload = await response.json().catch(() => ({}));
	if (!response.ok) {
		const error = explain(response.status, payload);
		// 用的是记着的口令却被拒了：别停在一页报错上，回到输入口令那一页
		if (token === undefined && response.status === 403) {
			adminLockReason.set(error.message);
			clearAdminToken();
		}
		throw error;
	}
	return payload as T;
}

/** 试一下口令对不对：用最轻的一个接口（模型登记列表，不碰学习记录库，库没开也能验） */
export async function verifyAdminToken(token: string): Promise<void> {
	await adminRequest('/admin/model-providers', 'GET', token);
	adminLockReason.set('');
	adminToken.set(token.trim());
}

// ====================== 学习记录 ======================
export type StudentSummary = {
	id: string;
	name: string;
	first_seen_at: number;
	last_seen_at: number;
	chat_turns: number;
	essay_reviews: number;
	essay_avg: number | null;
	exams_reviewed: number;
	exam_avg_percent: number | null;
};

export type LearningSummary = {
	totals: { students: number; chat_turns: number; essay_reviews: number; exams_reviewed: number };
	students: StudentSummary[];
};

export type ChatTurnRecord = {
	id: number;
	mode: string;
	model: string;
	question: string;
	answer: string;
	finish_reason: string | null;
	duration_ms: number | null;
	created_at: number;
};

export type EssayReviewRecord = {
	id: number;
	model: string;
	topic: string;
	text: string;
	score: number | null;
	review: unknown;
	created_at: number;
};

export type ExamAttemptRecord = {
	exam_id: string;
	model: string;
	title: string;
	topic: string;
	total_points: number;
	score: number | null;
	created_at: number;
	reviewed_at: number | null;
};

export type StudentTimeline = {
	student: { id: string; name: string; first_seen_at: number; last_seen_at: number };
	chat_turns: ChatTurnRecord[];
	essay_reviews: EssayReviewRecord[];
	exam_attempts: ExamAttemptRecord[];
};

export const getLearningSummary = () => adminRequest<LearningSummary>('/admin/learning/summary');

export const getStudentTimeline = (studentId: string) =>
	adminRequest<StudentTimeline>(`/admin/learning/students/${encodeURIComponent(studentId)}`);

export type DailyActivity = {
	day: string;
	chat_turns: number;
	essay_reviews: number;
	exams_generated: number;
	exams_reviewed: number;
	active_students: number;
};

export type ActiveStudent = {
	id: string;
	name: string;
	chat_turns: number;
	essay_reviews: number;
	exams_reviewed: number;
};

export type LearningAnalytics = {
	days: number;
	daily: DailyActivity[];
	totals: {
		chat_turns: number;
		essay_reviews: number;
		exams_generated: number;
		exams_reviewed: number;
	};
	/** 按场景分的提问数：qa 课程答疑、paper 论文助手、chat Playground */
	chat_modes: Record<string, number>;
	/** 窗口里有过答疑、批改或交卷的学生数 */
	active_students: number;
	/** 其中最活跃的 50 个 */
	students: ActiveStudent[];
};

export const getLearningAnalytics = (days: number) =>
	adminRequest<LearningAnalytics>(`/admin/learning/analytics?days=${days}`);

export type ModelStat = {
	model: string;
	chat_turns: number;
	avg_duration_ms: number | null;
	completed: number;
	interrupted: number;
	completion_rate: number | null;
	essay_reviews: number;
	essay_avg: number | null;
	exams_reviewed: number;
	exam_avg_percent: number | null;
	thumbs_up: number;
	thumbs_down: number;
	thumbs_up_rate: number | null;
};

/** 不给 days 时统计全部记录 */
export const getModelStats = (days?: number) =>
	adminRequest<{ models: ModelStat[] }>(
		days ? `/admin/learning/models?days=${days}` : '/admin/learning/models'
	).then((body) => body.models);

export type ModelActivity = {
	model: string;
	days: number;
	daily: { day: string; chat_turns: number; thumbs_up: number; thumbs_down: number }[];
	chat_modes: Record<string, number>;
};

export const getModelActivity = (model: string, days: number) =>
	adminRequest<ModelActivity>(
		`/admin/learning/models/${encodeURIComponent(model)}/activity?days=${days}`
	);

export type FeedbackEntry = {
	id: number;
	student_id: string;
	student_name: string | null;
	model: string;
	mode: string;
	/** 1 = 有帮助，-1 = 没有帮助 */
	rating: 1 | -1;
	question: string;
	answer: string;
	created_at: number;
	updated_at: number;
};

/** 一次最多取这么多条（后端上限 500），最新的在前 */
export const FEEDBACK_LIMIT = 500;

export const getFeedback = (limit = FEEDBACK_LIMIT) =>
	adminRequest<{ feedback: FeedbackEntry[] }>(`/admin/learning/feedback?limit=${limit}`).then(
		(body) => body.feedback
	);

export const deleteFeedback = (id: number) =>
	adminRequest<{ status: boolean }>(`/admin/learning/feedback/${id}`, 'DELETE');

export type DbInfo = {
	path: string;
	bytes: number;
	schema_version: number;
	tables: Record<string, number>;
	backups: { file: string; bytes: number; modified_at: number }[];
	backup_keep: number;
};

export const getDbInfo = () => adminRequest<DbInfo>('/admin/learning/db');

export const backupDb = () =>
	adminRequest<{ status: boolean; file: string; bytes: number }>('/admin/learning/backup', 'POST');

/** 学习记录里的 mode → 页面上的说法 */
export const MODE_LABELS: Record<string, string> = {
	qa: '课程答疑',
	paper: '论文助手',
	chat: 'Playground'
};

// ====================== 知识库 ======================
export type JobStatus = {
	status: 'idle' | 'running' | 'succeeded' | 'failed';
	started_at: number | null;
	finished_at: number | null;
	message: string;
};

export type LocalKnowledgeSnapshot = {
	kind: 'local';
	textbook: { file: string; chunks: number };
	references: { enabled: boolean; papers: number; chunks: number };
	embedding: { model: string; loaded: boolean; revision: string | null };
	chunking: {
		chunk_size: number;
		chunk_overlap: number;
		reference_window: number;
		reference_window_overlap: number;
	};
	retrieval: {
		qa_top_k: number;
		cache: { enabled: boolean; entries: number; max_entries: number; ttl_seconds: number };
	};
	exam: {
		sample_k: number;
		textbook_min_share: number;
		mmr_lambda: number;
		mmr_fetch_k: number;
		context_char_limit: number;
	};
	index: { ready: boolean; vectors: number | null; disk_cache: boolean };
	resting_seconds?: number;
};

export type NotebookKnowledgeSnapshot = {
	kind: 'notebook';
	url: string;
	timeout_seconds: number;
	auth: boolean;
	resting_seconds?: number;
};

export type KnowledgeSnapshot =
	| LocalKnowledgeSnapshot
	| NotebookKnowledgeSnapshot
	| { kind: 'composite'; sources: (LocalKnowledgeSnapshot | NotebookKnowledgeSnapshot)[] };

export type KnowledgeAdmin = {
	source: 'local' | 'notebook' | 'composite';
	notebook_url: string;
	notebook_reachable: boolean | null;
	knowledge_base: KnowledgeSnapshot;
	jobs: { reload: JobStatus; references: JobStatus };
};

export const getKnowledgeAdmin = () => adminRequest<KnowledgeAdmin>('/admin/knowledge');

export const clearRetrievalCache = () =>
	adminRequest<{ cleared: number }>('/admin/knowledge/cache/clear', 'POST');

export const reloadKnowledge = () =>
	adminRequest<{ started: boolean; job: JobStatus }>('/admin/knowledge/reload', 'POST');

export const refreshReferences = () =>
	adminRequest<{ started: boolean; job: JobStatus }>('/admin/knowledge/references/refresh', 'POST');

/** 把快照拆成各个来源（单一来源时就是它自己） */
export const knowledgeSources = (snapshot: KnowledgeSnapshot) =>
	snapshot.kind === 'composite' ? snapshot.sources : [snapshot];

// ====================== 显示 ======================
export const formatTime = (ms: number | null | undefined) =>
	ms ? new Date(ms).toLocaleString('zh-CN', { hour12: false }) : '—';

export function timeAgo(ms: number) {
	const minutes = Math.max(1, Math.floor((Date.now() - ms) / 60000));
	if (minutes < 60) return `${minutes} 分钟前`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours} 小时前`;
	return `${Math.floor(hours / 24)} 天前`;
}

export const percent = (ratio: number | null | undefined) =>
	ratio === null || ratio === undefined ? '—' : `${(ratio * 100).toFixed(1)}%`;

export function formatBytes(bytes: number) {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
