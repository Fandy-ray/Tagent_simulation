/**
 * 闪卡边写边给（后端 /quiz/flash/stream）用到的纯函数：拆行、往刷卡队列里追加新到的卡。
 *
 * 这个模块**只有类型 import**，纯函数，可用 node --test 单测（flash.ts 引了 $lib 别名，测不了）。
 *
 * 为什么要边写边给：一片四张卡要写两三秒，而第一张写完时才过去一秒左右。以前等整组
 * 写完一起给，学生要对着转圈等三秒多；现在第一张一到就能开始刷，后面的边刷边到。
 */

import type { FlashCard, FlashSession } from './flash';

/** 后端一行一个 JSON，各行的样子见 basic-agent 的 ExamService.stream_flash_deck */
export type FlashStreamEvent =
	| { type: 'deck'; deck_id: string; title: string }
	| { type: 'title'; title: string }
	| { type: 'card'; card: FlashCard }
	| { type: 'done'; total_cards: number }
	| { type: 'error'; message: string; code?: string };

/**
 * 把新收到的一块文字接在上次剩下的半行后面，拆出完整的几行。
 * 最后不带换行的那半行留着（rest），等下一块来了再拼。
 */
export const splitLines = (rest: string, chunk: string): { lines: string[]; rest: string } => {
	const parts = (rest + chunk).split('\n');
	const tail = parts.pop() ?? '';
	return { lines: parts.map((line) => line.trim()).filter(Boolean), rest: tail };
};

/** 一行解析成事件；不认识的、半截坏掉的行返回 null，跳过就行 */
export const parseEvent = (line: string): FlashStreamEvent | null => {
	try {
		const event = JSON.parse(line) as { type?: unknown };
		return event && typeof event.type === 'string' ? (event as FlashStreamEvent) : null;
	} catch {
		return null;
	}
};

/**
 * 新到的卡排到队尾。同一个 id 不会进两次（后端按到达先后编号，正常不会重复）。
 *
 * 学生把已经到的卡刷完、队列空了的时候，advance 会盖上结束时间；这时又来了新卡，
 * 这一轮其实还没完，所以把结束时间清掉。
 */
export const appendCards = (session: FlashSession, cards: FlashCard[]): FlashSession => {
	const seen = new Set(session.deck.cards.map((card) => card.id));
	const fresh = cards.filter((card) => !seen.has(card.id));

	if (fresh.length === 0) {
		return session;
	}

	const all = [...session.deck.cards, ...fresh];

	return {
		...session,
		deck: { ...session.deck, cards: all, total_cards: all.length },
		queue: [...session.queue, ...fresh.map((card) => card.id)],
		endedAt: null
	};
};
