/**
 * 追问建议与自动标签。
 *
 * 这个模块**不 import 任何东西**，纯函数，可用 node --test 单测。
 *
 * 原来的两个问题：
 * - 追问在第 24 个字符硬切，切在「…怎么」这种半截词上，也不补省略号；
 * - 标签把问题按标点切开就完事，`M/M/1` 的斜杠被当标点去掉后，剩下
 *   「M」「M」「1」各不足两字全被丢掉——偏偏它才是最该当标签的那个词。
 */

/** 追问里引用原问题时，最多引这么长 */
const QUESTION_EXCERPT = 24;

/**
 * 中文没有词边界，一整串汉字会被当成一个词（「排队系统里的服务台有几个」）。
 * 这里不上分词库，只按常见虚词把长串切开——够用，而且不引依赖。
 */
const PARTICLES = /[的了吗呢吧呀啊着过和与或在里中是有把被将对及以之]/;

/** 切完还嫌长的段，标签只取前这么多字 */
const TAG_MAX_CHARS = 6;

/** 疑问词、指代词切出来的碎片：「什么是 M/M/1」切出「什么」，「那它的前提呢」切出「那它」 */
const NOT_A_TAG = new Set([
	'什么',
	'怎么',
	'怎样',
	'为什么',
	'如何',
	'哪些',
	'哪个',
	'请问',
	'一下',
	'那它',
	'那么',
	'它们',
	'这个',
	'那个',
	'这些',
	'那些',
	'还有',
	'另外'
]);

/**
 * 指代型追问（「那它的前提呢」）：离开上文就不完整，原样引进「请更详细地解释「…」」
 * 里读着别扭。和后端 app/rag/followup.py 的判断同一个思路，只看短句，免得误伤长问题。
 */
const DEIXIS = /它|他|她|这个|这些|那个|那些|上述|前者|后者|^(?:那|那么|还有|另外)|呢[？?]?$/;
const BARE_FOLLOW_UP_MAX_CHARS = 12;

const CJK = /[一-龥]/;

/** 像 M/M/1、λ/μ、0.75 这样的记号：内部的 / 和 . 是词的一部分，不是标点 */
const TOKEN = /[A-Za-zͰ-Ͽ][A-Za-z0-9Ͱ-Ͽ]*(?:[/.][A-Za-z0-9Ͱ-Ͽ]+)+|[一-龥]+|[A-Za-z][A-Za-z0-9]+/g;

/** 截断并补省略号；在边界上截，不要切出半截词。 */
export function excerpt(text: string, limit = QUESTION_EXCERPT): string {
	const flat = text.replace(/\s+/g, ' ').trim();
	if (flat.length <= limit) {
		return flat;
	}
	const cut = flat.slice(0, limit);
	// 英文在最后一个空格处收口；中文没有词边界，只能直接截，但一定补省略号
	const lastSpace = cut.lastIndexOf(' ');
	const body = lastSpace > limit * 0.6 ? cut.slice(0, lastSpace) : cut;
	return `${body.replace(/[，,。.、；;：:]$/, '')}…`;
}

export function buildFollowUps(question: string): string[] {
	const base = excerpt(question);
	if (!base) {
		return [];
	}
	// 追问本身是「那它的前提呢」这种时，不引原话，直接请它展开上面的回答
	const bare = base.length <= BARE_FOLLOW_UP_MAX_CHARS && DEIXIS.test(base);
	const first = bare ? '请把上面的回答再展开讲讲' : `请更详细地解释「${base}」`;
	// 后两条看着脱离上下文，但现在请求会带上前几轮对话（见 chatHistory.ts），
	// 模型知道「它」指什么。多轮记忆没接通之前，这两条确实问了也白问。
	return [first, '用例子说明一下', '相关还有哪些知识点？'];
}

export function buildTags(question: string, limit = 3): string[] {
	const cleaned: string[] = [];
	for (const raw of question.match(TOKEN) ?? []) {
		// 中文串先按虚词切开；拉丁/记号（M/M/1）整体保留，不能切
		const pieces = CJK.test(raw) ? raw.split(PARTICLES) : [raw];
		for (const piece of pieces) {
			const token = piece.slice(0, TAG_MAX_CHARS);
			if (token.length < 2 || NOT_A_TAG.has(token) || cleaned.includes(token)) {
				continue;
			}
			cleaned.push(token);
		}
	}
	const picked = cleaned.slice(0, limit);
	return picked.length ? picked : ['答疑'];
}
