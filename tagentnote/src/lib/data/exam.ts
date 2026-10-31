import type { Annotation } from '$lib/data/essay';

/**
 * 整卷（试卷模式）共用的类型与渲染工具。
 *
 * 从原来的 MockExamPanel（现 FullExamPanel）里抽出来，让闪卡与整卷两个面板共享同一份判定配色，
 * 不至于哪天改了「部分得分」的颜色只改了一半。
 *
 * 类型按**后端实际下发的字段**声明 —— `to_public()`（app/schema/exam.py:273）
 * 是显式逐字段投影，答案、正确选项、参考答案、解析都不会出现在题面里，
 * 解析只在判卷结果 `results[].explanation` 中返回。
 */

/** 测评的两种模式：闪卡（填空 + 选择、本地判定）与整卷（三段、100 分、AI 判大题）。 */
export type ExamMode = 'flash' | 'full';

export type QuestionType = 'cloze' | 'choice' | 'essay';
export type Verdict = 'correct' | 'partial' | 'wrong' | 'unanswered';

export type ExamAnswer = string | number | null;
export type ExamAnswers = Record<string, ExamAnswer>;

export type ClozeQuestion = {
	id: string;
	type: 'cloze';
	points: number;
	cue: string;
	text: string;
};

export type ChoiceQuestion = {
	id: string;
	type: 'choice';
	points: number;
	question: string;
	options: string[];
};

export type EssayQuestion = {
	id: string;
	type: 'essay';
	points: number;
	question: string;
};

export type PublicQuestion = ClozeQuestion | ChoiceQuestion | EssayQuestion;

export type PublicExam = {
	exam_id: string;
	title: string;
	total_points: number;
	cloze: ClozeQuestion[];
	choice: ChoiceQuestion[];
	essay: EssayQuestion[];
};

export type ReviewResult = {
	id: string;
	type: QuestionType;
	score: number;
	points: number;
	verdict: Verdict;
	my_answer: string | number | null;
	correct_answer: string;
	feedback: string;
	explanation: string;
};

export type ExamSectionReview = {
	earned: number;
	max: number;
};

export type ExamReview = {
	exam_id: string;
	total_score: number;
	total_points: number;
	overall_comment: string;
	sections: Record<QuestionType, ExamSectionReview>;
	results: ReviewResult[];
};

export type SavedAnswerNote = {
	status: 'done';
	source: string;
	items: Annotation[];
};

export type AnswerNoteState =
	| { status: 'loading'; source: string }
	| SavedAnswerNote
	| { status: 'failed'; source: string; error: string };

/** Only completed annotations are safe to restore after a refresh. */
export const completedAnswerNotes = (notes: Record<string, AnswerNoteState>) =>
	Object.fromEntries(
		Object.entries(notes).flatMap(([questionId, note]) =>
			note.status === 'done' ? [[questionId, note]] : []
		)
	);

export const LETTERS = ['A', 'B', 'C', 'D'];

export const SECTION_LABELS: Record<QuestionType, string> = {
	cloze: '填空题',
	choice: '选择题',
	essay: '大题'
};

export const hasAnswer = (question: PublicQuestion, answerMap: ExamAnswers) => {
	const answer = answerMap[question.id];

	if (question.type === 'choice') {
		return typeof answer === 'number';
	}

	return typeof answer === 'string' && answer.trim() !== '';
};

export const answerNavClass = (
	question: PublicQuestion,
	index: number,
	currentIndex: number,
	answerMap: ExamAnswers
) =>
	index === currentIndex
		? 'bg-white text-black border-white'
		: hasAnswer(question, answerMap)
			? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
			: 'bg-white/[0.04] text-gray-400 border-white/[0.08]';

export const resultNavClass = (item: ReviewResult) => {
	if (item.verdict === 'correct') {
		return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
	}

	if (item.verdict === 'partial') {
		return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
	}

	if (item.verdict === 'unanswered') {
		return 'bg-white/[0.04] text-gray-400 border-white/[0.08]';
	}

	return 'bg-red-500/15 text-red-300 border-red-500/30';
};

export const verdictClass = (verdict: Verdict) => {
	if (verdict === 'correct') {
		return 'text-emerald-300';
	}

	if (verdict === 'partial') {
		return 'text-amber-300';
	}

	if (verdict === 'unanswered') {
		return 'text-gray-500';
	}

	return 'text-red-300';
};

export const verdictLabel = (verdict: Verdict) => {
	const labels: Record<Verdict, string> = {
		correct: '✓ 正确',
		partial: '◐ 部分得分',
		wrong: '✗ 错误',
		unanswered: '未作答'
	};

	return labels[verdict];
};

/** 秒 → m:ss。闪卡结算与整卷生成中的计时共用。 */
export const formatDuration = (seconds: number) => {
	const total = Math.max(0, Math.round(seconds));
	return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
};

// ====================== 整卷进度：刷新不丢 ======================

/**
 * 整卷答到一半刷新页面，以前整张卷子和已经写的答案全丢，只能重新出卷。现在把卷面、答案、
 * 做到第几题、判卷结果存进 sessionStorage：同一个标签页里刷新能接着做，关掉标签页就没了
 * （不跨标签、不长期留在本机）。
 *
 * 存的是公开卷面（不含参考答案）。判卷仍然要后端缓存里的那份私有卷，后端留 2 小时，
 * 这里也只认 2 小时内出的卷。
 */
export type SavedFullExam = {
	v: 1;
	/** 出卷时刻，用来和后端的 2 小时缓存对齐 */
	startedAt: number;
	modelId: string;
	topic: string;
	notebookIds: string[];
	exam: PublicExam;
	answers: ExamAnswers;
	pageIndex: number;
	review: ExamReview | null;
	resultIndex: number;
	/** 已完成的逐句批注；进行中的请求不落盘，避免刷新后留下永久 loading。 */
	answerNotes: Record<string, SavedAnswerNote>;
};

const FULL_EXAM_KEY = 'tagent:full-exam';
const FULL_EXAM_TTL_MS = 2 * 60 * 60 * 1000;

export const loadFullExam = (): SavedFullExam | null => {
	try {
		const raw = sessionStorage.getItem(FULL_EXAM_KEY);
		if (!raw) {
			return null;
		}
		const saved = JSON.parse(raw) as SavedFullExam;
		if (saved?.v !== 1 || !saved.exam?.exam_id || Date.now() - saved.startedAt > FULL_EXAM_TTL_MS) {
			sessionStorage.removeItem(FULL_EXAM_KEY);
			return null;
		}
		return { ...saved, answerNotes: saved.answerNotes ?? {} };
	} catch {
		return null;
	}
};

export const saveFullExam = (saved: Omit<SavedFullExam, 'v'>) => {
	try {
		sessionStorage.setItem(FULL_EXAM_KEY, JSON.stringify({ ...saved, v: 1 }));
	} catch {
		// 隐私模式或存储满：照常答题，只是刷新后接不上
	}
};

export const clearFullExam = () => {
	try {
		sessionStorage.removeItem(FULL_EXAM_KEY);
	} catch {
		// 同上
	}
};
