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
	// 后两条看着脱离上下文，但现在请求会带上前几轮对话（见 chatHistory.ts），
	// 模型知道「它」指什么。多轮记忆没接通之前，这两条确实问了也白问。
	return [`请更详细地解释「${base}」`, '用例子说明一下', '相关还有哪些知识点？'];
}

export function buildTags(question: string, limit = 3): string[] {
	const cleaned: string[] = [];
	for (const raw of question.match(TOKEN) ?? []) {
		// 中文串先按虚词切开；拉丁/记号（M/M/1）整体保留，不能切
		const pieces = CJK.test(raw) ? raw.split(PARTICLES) : [raw];
		for (const piece of pieces) {
			const token = piece.slice(0, TAG_MAX_CHARS);
			if (token.length < 2 || cleaned.includes(token)) {
				continue;
			}
			cleaned.push(token);
		}
	}
	const picked = cleaned.slice(0, limit);
	return picked.length ? picked : ['答疑'];
}
