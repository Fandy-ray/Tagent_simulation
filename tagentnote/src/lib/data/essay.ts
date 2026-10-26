/**
 * 小论文批改（答疑 · 论文辅助模式）与整卷大题逐句批注共用的类型与纯函数。
 *
 * 类型按后端实际下发的字段声明，见 app/schema/essay.py 的 PaperReview / Annotation。
 *
 * 高亮的唯一事实源是后端 split_sentences 切出的 (start, end)：前端**绝不**自己切句、
 * 也不拿批注原文去正文里搜位置——两边规则差一个标点，所有高亮就整体错位。
 * 这里只做两件机械的事：把后端的下标换算成浏览器能用的下标，以及校验恒等式
 * source[start:end] === text 是否成立；不成立就不画，而不是去猜。
 */

export type AnnotationKind = 'issue' | 'suggestion' | 'praise';
export const annotationLabel = (kind: AnnotationKind) =>
	({ issue: '需修改', suggestion: '表达完善', praise: '写得好' })[kind];
export type DimensionName = 'content' | 'argument' | 'language';

export type Annotation = {
	sentence_id: string;
	kind: AnnotationKind;
	comment: string;
	/** Python 字符串下标（按码点计），不是 JS 的 UTF-16 下标 */
	start: number;
	end: number;
	text: string;
};

export type DimensionResult = {
	name: DimensionName;
	label: string;
	weight: number;
	score_ratio: number;
	hits: string[];
	misses: string[];
	comment: string;
};

export type QuickScan = {
	characters: number;
	paragraphs: number;
	sentences: number;
	empty_paragraphs: number;
	duplicate_sentence_ids: string[];
	cites_material: boolean;
};

export type PaperReview = {
	title: string;
	word_count: number;
	quick_scan: QuickScan;
	dimensions: DimensionResult[];
	annotations: Annotation[];
	score: number;
	overall_comment: string;
};

export type AnswerAnnotations = {
	question_id: string;
	annotations: Annotation[];
};

/**
 * 评分栏在交稿**之前**就要印出来（让学生先知道批哪三样、各占多少），
 * 那时还没有后端结果，所以这里抄一份 app/schema/essay.py 的
 * DIMENSION_LABELS / DIMENSION_WEIGHTS。拿到结果后一律以后端下发的 weight 为准。
 */
export const DIMENSIONS: { name: DimensionName; label: string; weight: number }[] = [
	{ name: 'content', label: '切题与内容', weight: 0.4 },
	{ name: 'argument', label: '论证与结构', weight: 0.35 },
	{ name: 'language', label: '语言与规范', weight: 0.25 }
];

/** 与 app/config.py 的 ESSAY_MIN_CHARS / ESSAY_MAX_CHARS 一致，按去空白后的字数计 */
export const ESSAY_MIN_CHARS = 100;
export const ESSAY_MAX_CHARS = 6000;
/** 与 app/api/validators.py 的 MAX_TOPIC_LENGTH 一致 */
export const ESSAY_TOPIC_MAX = 100;
/** 与 app/config.py 的 ANNOTATE_MIN_ANSWER_CHARS 一致：更短的作答后端直接回空 */
export const ANNOTATE_MIN_ANSWER_CHARS = 40;

/**
 * Python str.isspace() 认的空白字符。
 *
 * 后端先 strip() 再切句，下标是相对 strip 之后的正文算的。JS 的 trim() 和它不是
 * 同一个集合（JS 多认 U+FEFF，少认 \x1c-\x1f 和 U+0085），差一个字符，下标就
 * 整体平移——所以这里按 Python 的定义自己写，而不是用 trim()。
 * 同一个集合也是 Python `re` 里 `\s` 的含义，字数统计（quick_scan）用的就是它。
 */
const PY_SPACE =
	'\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
const PY_SPACE_EDGES = new RegExp(`^[${PY_SPACE}]+|[${PY_SPACE}]+$`, 'g');
const PY_SPACE_RUN = new RegExp(`[${PY_SPACE}]+`, 'g');
const PY_NON_SPACE = new RegExp(`[^${PY_SPACE}]`);

/** 等价于 Python 的 str.strip()（无参数） */
export const pyStrip = (value: string) => (value ?? '').replace(PY_SPACE_EDGES, '');

/** 去空白后的字数，按码点计。等价于后端 len(re.sub(r"\s+", "", source)) */
export const countCharacters = (value: string) =>
	Array.from((value ?? '').replace(PY_SPACE_RUN, '')).length;

/** 非空段数。等价于后端 quick_scan 里按 "\n" 切、丢掉全空白行之后的段数 */
export const countParagraphs = (value: string) =>
	(value ?? '').split('\n').filter((line) => PY_NON_SPACE.test(line)).length;

export type LengthGate =
	{ ok: true; message: string } | { ok: false; message: string; tooLong: boolean };

/** 交稿前的长度闸，文案与后端 InvalidExamRequestError 的说法对齐 */
export const essayLengthGate = (characters: number): LengthGate => {
	if (characters === 0) {
		return { ok: false, tooLong: false, message: '先把论文正文粘进输入框' };
	}

	if (characters < ESSAY_MIN_CHARS) {
		return {
			ok: false,
			tooLong: false,
			message: `还差 ${ESSAY_MIN_CHARS - characters} 字才能批改（至少 ${ESSAY_MIN_CHARS} 字）`
		};
	}

	if (characters > ESSAY_MAX_CHARS) {
		return {
			ok: false,
			tooLong: true,
			message: `超出单次批改上限 ${characters - ESSAY_MAX_CHARS} 字，请删减或分段提交`
		};
	}

	return { ok: true, message: `可以交稿（上限 ${ESSAY_MAX_CHARS.toLocaleString()} 字）` };
};

// ====================== 批注落位 ======================

/** 通过了恒等式校验、可以画出来的批注。n 是按原文顺序的编号，从 1 起 */
export type PlacedAnnotation = Annotation & { n: number };

export type Segment =
	{ kind: 'text'; text: string } | { kind: 'mark'; text: string; note: PlacedAnnotation };

/** 一个自然段的渲染片段。只用于排版（缩进、分段），跟后端的段号无关 */
export type RenderedParagraph = { key: number; segments: Segment[] };

export type Placement = {
	paragraphs: RenderedParagraph[];
	placed: PlacedAnnotation[];
	/** 下标对不上原文、没有画出来的批注。正常不该出现，出现了说明两边正文不一致 */
	unplaced: Annotation[];
};

/**
 * 按后端给的下标把批注落到原文上。
 *
 * 下标按**码点**计（Python 语义），所以先 Array.from 拆成码点再切——直接用
 * String.slice 的话，正文里只要有一个 emoji 或扩展区汉字（UTF-16 占两位），
 * 后面所有高亮都会错开一位。
 *
 * 逐条校验 source[start:end] === text：通不过的不画、放进 unplaced，
 * 由调用方如实告诉用户，**不去正文里搜**。
 */
export const placeAnnotations = (source: string, annotations: Annotation[]): Placement => {
	const chars = Array.from(source);
	const sorted = [...annotations].sort((a, b) => a.start - b.start);

	const placed: PlacedAnnotation[] = [];
	const unplaced: Annotation[] = [];
	let cursor = 0;

	for (const item of sorted) {
		const inRange =
			Number.isInteger(item.start) &&
			Number.isInteger(item.end) &&
			item.start >= cursor &&
			item.end > item.start &&
			item.end <= chars.length;

		if (inRange && chars.slice(item.start, item.end).join('') === item.text) {
			placed.push({ ...item, n: placed.length + 1 });
			cursor = item.end;
		} else {
			unplaced.push(item);
		}
	}

	// 按 "\n" 分行只为了排版：每段首行缩进、段间不留空行。句子不会跨段
	// （后端先切段再切句），所以批注区间不会被这里切断。
	const paragraphs: RenderedParagraph[] = [];
	let lineStart = 0;

	for (let index = 0; index <= chars.length; index += 1) {
		if (index < chars.length && chars[index] !== '\n') {
			continue;
		}

		const segments = lineSegments(chars, lineStart, index, placed);

		if (segments.length > 0) {
			paragraphs.push({ key: lineStart, segments });
		}

		lineStart = index + 1;
	}

	return { paragraphs, placed, unplaced };
};

const lineSegments = (
	chars: string[],
	from: number,
	to: number,
	placed: PlacedAnnotation[]
): Segment[] => {
	// 行首行尾的空白不显示（缩进交给 CSS），批注永远不会落在这些空白上
	let start = from;
	let end = to;

	while (start < end && !PY_NON_SPACE.test(chars[start])) {
		start += 1;
	}

	while (end > start && !PY_NON_SPACE.test(chars[end - 1])) {
		end -= 1;
	}

	if (start >= end) {
		return [];
	}

	const segments: Segment[] = [];
	let cursor = start;

	for (const note of placed) {
		if (note.end <= start || note.start >= end) {
			continue;
		}

		const markStart = Math.max(note.start, start);
		const markEnd = Math.min(note.end, end);

		if (markStart > cursor) {
			segments.push({ kind: 'text', text: chars.slice(cursor, markStart).join('') });
		}

		segments.push({ kind: 'mark', text: chars.slice(markStart, markEnd).join(''), note });
		cursor = markEnd;
	}

	if (cursor < end) {
		segments.push({ kind: 'text', text: chars.slice(cursor, end).join('') });
	}

	return segments;
};

// ====================== 评分栏 ======================

/** 旁批编号用带圈数字，和老师在稿纸边上写的一样。批注定额最多 5 条，够用 */
const CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩'];

export const circled = (n: number) => CIRCLED[n - 1] ?? `(${n})`;

/** 一个维度折算进总分的分值：得分率 × 权重 × 100 */
export const dimensionPoints = (dimension: Pick<DimensionResult, 'score_ratio' | 'weight'>) =>
	dimension.score_ratio * dimension.weight * 100;

/**
 * 各维的整数得分，加起来正好等于后端给的总分（最大余数法）。
 *
 * 每维 4 条要点、权重 35/40/25，折算出来常带 .25/.5/.75；直接显示小数，学生会问「17.5 分是怎么来的」，
 * 各自四舍五入又可能加不回总分。先各取整数部分，差的那几分给小数部分最大的几维（一样大时给满分高的）。
 * total 为 null（还没出总分）时按四舍五入后的合计算。
 */
export function integerPoints(
	dimensions: readonly Pick<DimensionResult, 'name' | 'score_ratio' | 'weight'>[],
	total: number | null = null
): Map<DimensionName, number> {
	const exact = dimensions.map((item) => ({
		name: item.name,
		value: dimensionPoints(item),
		full: fullMarks(item.weight)
	}));
	// 浮点误差（0.35 × 0.75 × 100 = 26.249999…）先抹掉，免得整数部分少算一分
	const tidy = exact.map((item) => ({ ...item, value: Math.round(item.value * 1e6) / 1e6 }));
	const floors = tidy.map((item) => Math.floor(item.value));
	const target = total ?? Math.round(tidy.reduce((sum, item) => sum + item.value, 0));
	let left = Math.max(
		0,
		Math.min(tidy.length, target - floors.reduce((sum, value) => sum + value, 0))
	);
	const order = tidy
		.map((item, index) => ({ index, remainder: item.value - floors[index], full: item.full }))
		.sort((a, b) => b.remainder - a.remainder || b.full - a.full);
	const points = [...floors];
	for (const item of order) {
		if (left === 0) break;
		if (item.remainder === 0 || points[item.index] >= tidy[item.index].full) continue;
		points[item.index] += 1;
		left -= 1;
	}
	return new Map(tidy.map((item, index) => [item.name, points[index]]));
}

/** 权重 → 满分（0.35 → 35） */
export const fullMarks = (weight: number) => Math.round(weight * 100);

/**
 * 分值显示：整数不带小数，其余最多两位（17.5、18.75）。
 * 每维 4 条要点、权重 35/25，所以 .25 .5 .75 都会出现，截成一位小数反而加不回总分。
 */
export const formatPoints = (value: number) => String(Math.round(value * 100) / 100);

/**
 * 评分要点的**顺序**，抄自 app/schema/essay.py 的 RUBRIC_POINTS。
 *
 * 模型写评语时爱说「命中了第 1、2、4 条」，这个「第几条」指的是 prompt 里的顺序；
 * 后端只分开下发 hits / misses、不带顺序，所以这里抄一份用来排序和编号。
 * 只有四条全部对得上才编号——这份抄本一旦和后端不一致，宁可不编号也不能编错。
 */
const RUBRIC_ORDER: Record<DimensionName, readonly string[]> = {
	content: [
		'回应了题目要求，没有答非所问',
		'用上了课程材料里的概念，而不是只凭常识泛谈',
		'有具体例子、数据或案例支撑，不是空泛表述',
		'观点明确，读得出作者自己的立场'
	],
	argument: [
		'每个论点都有对应的论据，不是只下结论',
		'段落之间有逻辑推进，不是并列罗列',
		'考虑了反面情形或适用局限',
		'结论由前文推出，不是凭空跳出来的'
	],
	language: [
		'没有明显病句或成分残缺',
		'术语使用准确，没有张冠李戴',
		'是书面语，没有口语化表达',
		'段落长度与格式得当，没有整篇一段到底'
	]
};

export type RubricLine = { point: string; hit: boolean; n: number | null };

export const rubricLines = (dimension: DimensionResult): RubricLine[] => {
	const order = RUBRIC_ORDER[dimension.name] ?? [];
	const lines = [
		...dimension.hits.map((point) => ({ point, hit: true })),
		...dimension.misses.map((point) => ({ point, hit: false }))
	];
	const known = lines.length === order.length && lines.every((line) => order.includes(line.point));

	if (!known) {
		// 对不上就不编号，按「先缺后有」排：学生最该先看没拿到分的那几条
		return [...lines.filter((line) => !line.hit), ...lines.filter((line) => line.hit)].map(
			(line) => ({ ...line, n: null })
		);
	}

	return lines
		.map((line) => ({ ...line, n: order.indexOf(line.point) + 1 }))
		.sort((a, b) => a.n - b.n);
};

/**
 * 模型写评语时会顺手引用正文编号（P3、P3S1）——那是喂给它的带号正文里的记号，
 * 学生看不懂。这里只在显示时替换：P3S1 → 第3段第1句，P3 → 第3段。
 * 段号的数法（跳过空行、从 1 起）和本页排版出来的自然段一一对应。
 */
const SENTENCE_REF = /(?<![A-Za-z0-9])P(\d{1,3})(?:S(\d{1,3}))?(?![A-Za-z0-9])/g;

export const humanizeRefs = (text: string) =>
	(text ?? '').replace(SENTENCE_REF, (_match, paragraph: string, sentence?: string) =>
		sentence ? `第${paragraph}段第${sentence}句` : `第${paragraph}段`
	);

/** 默认展开得分率最低的那一维：学生最该先看的就是它 */
export const weakestDimension = (dimensions: DimensionResult[]) =>
	dimensions.reduce<DimensionResult | null>(
		(weakest, item) => (!weakest || item.score_ratio < weakest.score_ratio ? item : weakest),
		null
	);

// ====================== 答疑 · 论文辅助模式 ======================

/** 后端 /essay/topic 的返回，见 app/schema/essay.py 的 EssayTopic */
export type EssayTopic = {
	title: string;
	requirements: string[];
	suggested_chars: number;
	/** 后端按检索结果算：false 表示没检索到笔记本材料，题目是按课程通用内容出的 */
	grounded: boolean;
};

/**
 * 论文模式对话里的两种卡片，挂在消息的 paperCard 上，随会话一起存进 localStorage。
 *
 * review 卡的 text 必须是**发给后端的原文一字不差**（pyStrip 之后）：批注下标相对它算，
 * 刷新页面以后要靠它重新 placeAnnotations。卡片自带重跑所需的全部参数。
 */
export type PaperCard =
	| { kind: 'topic'; hint: string; topic: EssayTopic | null; error?: string }
	| { kind: 'review'; text: string; topic: string; review: PaperReview | null; error?: string };

/** 批改是三维并发、可能再下钻一轮，后端预算 220 秒；前端多留些给网络，再久就当后端没了响应 */
export const ESSAY_CLIENT_TIMEOUT_MS = 260_000;

/** 后端目前把「切题与内容」的评语当总评下发，和评分栏里那条重复；只有总评另有内容时才单独写 */
export const extraOverallComment = (review: PaperReview) => {
	const comment = review.overall_comment.trim();

	if (!comment || review.dimensions.some((item) => item.comment.trim() === comment)) {
		return '';
	}

	return humanizeRefs(comment);
};

/** 交稿那条用户消息只显示字数和开头一行，免得几千字刷屏 */
export const paperSubmissionLabel = (text: string) => {
	const firstLine = Array.from(
		text
			.split('\n')
			.find((line) => line.trim())
			?.trim() ?? ''
	);
	const preview = firstLine.slice(0, 40).join('') + (firstLine.length > 40 ? '…' : '');
	return `交稿批改 · ${countCharacters(text).toLocaleString()} 字\n${preview}`;
};

const tableCell = (value: string) =>
	value
		.replace(/\|/g, '｜')
		.replace(/\s*\n\s*/g, ' ')
		.trim();

/** 题目卡的纯文本版，当消息 content 用：复制、存进笔记本都直接可读 */
export const essayTopicMarkdown = (topic: EssayTopic) =>
	[
		`## 小论文题目：${topic.title}`,
		'',
		'写作要求：',
		...topic.requirements.map((item, index) => `${index + 1}. ${item}`),
		'',
		`建议篇幅：${topic.suggested_chars} 字左右`,
		...(topic.grounded ? [] : ['', '（没检索到笔记本材料，这道题按课程通用内容出。）'])
	].join('\n');

/** 批改卡的纯文本版，用途同上 */
export const paperReviewMarkdown = (review: PaperReview, topic: string, text: string) => {
	const { placed, unplaced } = placeAnnotations(text, review.annotations);
	const notes = [...placed, ...unplaced];
	const extra = extraOverallComment(review);

	return [
		`## 小论文批改：${review.score} / 100`,
		'',
		`题目：${topic || '（未设题目）'} · 全文 ${review.quick_scan.characters.toLocaleString()} 字`,
		'',
		'| 维度 | 得分 | 评语 |',
		'| --- | --- | --- |',
		...review.dimensions.map(
			(item) =>
				`| ${item.label} | ${formatPoints(dimensionPoints(item))} / ${fullMarks(item.weight)} | ${tableCell(humanizeRefs(item.comment))} |`
		),
		...(notes.length > 0
			? [
					'',
					'### 批注',
					...notes.map(
						(note, index) =>
							`${index + 1}. 【${annotationLabel(note.kind)}】「${note.text}」—— ${humanizeRefs(note.comment)}`
					)
				]
			: []),
		...(extra ? ['', `总评：${extra}`] : [])
	].join('\n');
};
