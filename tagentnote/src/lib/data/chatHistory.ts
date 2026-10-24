/**
 * 把会话整理成可以发给模型的多轮上下文。
 *
 * 在这之前答疑是**没有多轮记忆**的：每次只发 [system?] + 当前这一句。
 * 所以学生问「那它的前提呢」，模型根本不知道「它」指什么；追问建议也只能
 * 写死成三个固定模板——脱离上下文发出去模型照样答不上来，根因是同一个。
 *
 * 这个模块刻意**不 import 任何东西**：输入形状按结构声明即可。
 * qaConversations.ts 里有 SvelteKit 的 $app，一旦引它，这段纯逻辑就没法单测了。
 */

export type HistoryMessage = { role: 'user' | 'assistant'; content: string };

/** 历史最多带这么多条、这么多字符。两个都是为了别把上下文撑爆。 */
export const HISTORY_MAX_MESSAGES = 8;
export const HISTORY_MAX_CHARS = 6000;

type HistorySource = {
	role: 'user' | 'assistant';
	content?: string;
	/** 卡片操作展示的是短标签，真正问出去的在这里 */
	requestContent?: string;
	streaming?: boolean;
};

export function historyForRequest(
	messages: readonly HistorySource[],
	{ maxMessages = HISTORY_MAX_MESSAGES, maxChars = HISTORY_MAX_CHARS } = {}
): HistoryMessage[] {
	const usable = messages
		.filter((message) => !message.streaming)
		.map((message) => ({
			role: message.role,
			content: (message.requestContent ?? message.content ?? '').trim()
		}))
		.filter((message) => message.content.length > 0);

	// 当前这一问由 question 参数单独发，历史里不能再有一份
	if (usable.at(-1)?.role === 'user') {
		usable.pop();
	}

	const recent = usable.slice(-maxMessages);
	let total = 0;
	const kept: HistoryMessage[] = [];
	// 从最近的往回收：超预算时丢掉的是最旧的，留下离当前最近的几轮
	for (let index = recent.length - 1; index >= 0; index -= 1) {
		total += recent[index].content.length;
		if (total > maxChars && kept.length > 0) {
			break;
		}
		kept.unshift(recent[index]);
	}
	return kept;
}
