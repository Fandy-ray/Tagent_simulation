/**
 * 闪卡刷卡队列 —— 纯函数，不碰 DOM、不发请求。
 *
 * 规则很短：一张卡「会了」就出队，「再练」回队尾；队列空了这一轮就结束。
 * 队列里每个 id 至多出现一次（先出队再入队），所以不会因为反复「再练」
 * 把同一张卡堆进去。
 *
 * 所有函数都返回新对象，方便 Svelte 5 的 $state 直接整体替换。
 */

import { clozeMatches, type MatchMode } from '$lib/data/cloze';

export type FlashClozeCard = {
	id: string;
	type: 'cloze';
	cue: string;
	text: string;
	accept: string[];
	accept_normalized: string[];
	match_mode: MatchMode;
	explanation: string;
};

export type FlashChoiceCard = {
	id: string;
	type: 'choice';
	question: string;
	options: string[];
	correct_index: number;
	explanation: string;
};

/** 一组闪卡里两类混着来；大题不进闪卡，写一段话没法当场判。 */
export type FlashCard = FlashClozeCard | FlashChoiceCard;

export type FlashDeck = {
	deck_id: string;
	title: string;
	total_cards: number;
	cards: FlashCard[];
};

export type FlashOutcome = 'known' | 'again';

export type FlashAttempt = {
	/** 本轮被判「再练」的次数（含答错自动入队） */
	again: number;
	/** 最近一次输入作答的判定；翻卡自评不写这个字段 */
	graded: 'correct' | 'wrong' | null;
	answer: string;
};

export type FlashSession = {
	deck: FlashDeck;
	/** 待过的卡，队首是当前这张 */
	queue: string[];
	/** 已「会了」的卡，按完成先后 */
	known: string[];
	attempts: Record<string, FlashAttempt>;
	startedAt: number;
	endedAt: number | null;
};

// ====================== 闪卡进度：退出再进来不丢 ======================

/**
 * 出一组卡要等十几秒，还花模型的额度，以前点一下「返回」就没了。和整卷一样存进 sessionStorage：
 * 同一个标签页里退出再进来、刷新都能接着刷，关掉标签页就没了。明确选了放弃、或者开始新一轮才清。
 * 闪卡的判定本来就在前端、答案就在卡里，存下来不多暴露什么。
 */
export type SavedFlashDeck = {
	v: 1;
	modelId: string;
	topic: string;
	notebookIds: string[];
	session: FlashSession;
};

const FLASH_DECK_KEY = 'tagent:flash-deck';
const FLASH_DECK_TTL_MS = 2 * 60 * 60 * 1000;

export const loadFlashDeck = (now = Date.now()): SavedFlashDeck | null => {
	try {
		const raw = sessionStorage.getItem(FLASH_DECK_KEY);
		if (!raw) {
			return null;
		}
		const saved = JSON.parse(raw) as SavedFlashDeck;
		if (
			saved?.v !== 1 ||
			!saved.session?.deck?.cards?.length ||
			now - saved.session.startedAt > FLASH_DECK_TTL_MS
		) {
			sessionStorage.removeItem(FLASH_DECK_KEY);
			return null;
		}
		return saved;
	} catch {
		return null;
	}
};

export const saveFlashDeck = (saved: Omit<SavedFlashDeck, 'v'>) => {
	try {
		sessionStorage.setItem(FLASH_DECK_KEY, JSON.stringify({ ...saved, v: 1 }));
	} catch {
		// 隐私模式或存储满：照常刷，只是退出后接不上
	}
};

export const clearFlashDeck = () => {
	try {
		sessionStorage.removeItem(FLASH_DECK_KEY);
	} catch {
		// 同上
	}
};

const byId = (deck: FlashDeck) => new Map(deck.cards.map((card) => [card.id, card]));

export const createSession = (deck: FlashDeck, now = Date.now()): FlashSession => ({
	deck,
	queue: deck.cards.map((card) => card.id),
	known: [],
	attempts: {},
	startedAt: now,
	endedAt: null
});

export const currentCard = (session: FlashSession): FlashCard | null => {
	const id = session.queue[0];
	return id ? (byId(session.deck).get(id) ?? null) : null;
};

/**
 * 判定一次作答。
 *
 * 填空：参考侧用后端下发的 accept_normalized，前端只归一用户输入那一侧。
 * 选择：比下标就行——正确答案本来就随卡组发下来了。
 */
export const gradeAnswer = (card: FlashCard, answer: string | number) => {
	if (card.type === 'choice') {
		return answer === card.correct_index ? 'correct' : 'wrong';
	}

	return clozeMatches(String(answer ?? ''), card.accept_normalized, card.match_mode)
		? 'correct'
		: 'wrong';
};

/** 结算页要展示的"我当时答了什么"。 */
export const answerLabel = (card: FlashCard, answer: string | number) => {
	if (card.type === 'choice') {
		return typeof answer === 'number' ? (card.options[answer] ?? '') : '';
	}

	return String(answer ?? '');
};

/** 卡片的一句话标题：选择用题干；填空用 cue，没有 cue（现在不再让模型写）就用挖空句。结算页的清单共用。 */
export const cardHeadline = (card: FlashCard) =>
	card.type === 'choice' ? card.question : card.cue || card.text;

export const recordAnswer = (
	session: FlashSession,
	cardId: string,
	answer: string,
	graded: 'correct' | 'wrong'
): FlashSession => {
	const previous = session.attempts[cardId];

	return {
		...session,
		attempts: {
			...session.attempts,
			[cardId]: { again: previous?.again ?? 0, graded, answer }
		}
	};
};

/**
 * 处理一张卡的去留。
 *
 * `known` 出队记账；`again` 回队尾。队列空了就盖上结束时间 —— 结算页读它。
 */
export const advance = (
	session: FlashSession,
	outcome: FlashOutcome,
	now = Date.now()
): FlashSession => {
	const [cardId, ...rest] = session.queue;

	if (!cardId) {
		return session;
	}

	if (outcome === 'known') {
		return {
			...session,
			queue: rest,
			known: [...session.known, cardId],
			endedAt: rest.length === 0 ? now : null
		};
	}

	const previous = session.attempts[cardId];

	return {
		...session,
		queue: [...rest, cardId],
		attempts: {
			...session.attempts,
			[cardId]: {
				again: (previous?.again ?? 0) + 1,
				graded: previous?.graded ?? null,
				answer: previous?.answer ?? ''
			}
		}
	};
};

/** 结算页的「只重刷再练的」：留下这一轮至少被「再练」过一次的卡。 */
export const replayStruggled = (session: FlashSession, now = Date.now()): FlashSession => {
	const struggled = session.deck.cards.filter(
		(card) => (session.attempts[card.id]?.again ?? 0) > 0
	);

	if (struggled.length === 0) {
		return createSession(session.deck, now);
	}

	return createSession({ ...session.deck, cards: struggled, total_cards: struggled.length }, now);
};

/**
 * 在「待过」队列里前后翻看，不作判定。
 *
 * 往后转一张就是「这张先跳过」——它还在队里，只是排到后面去了，
 * 与「再练」的区别是不记账（不会进结算页的待重练清单）。
 */
export const rotateQueue = (session: FlashSession, direction: 1 | -1): FlashSession => {
	if (session.queue.length < 2) {
		return session;
	}

	const queue =
		direction === 1
			? [...session.queue.slice(1), session.queue[0]]
			: [session.queue[session.queue.length - 1], ...session.queue.slice(0, -1)];

	return { ...session, queue };
};

/** 点底部圆点直接跳到那张卡；已经「会了」的卡不回队。 */
export const focusCard = (session: FlashSession, cardId: string): FlashSession => {
	if (!session.queue.includes(cardId) || session.queue[0] === cardId) {
		return session;
	}

	return {
		...session,
		queue: [cardId, ...session.queue.filter((id) => id !== cardId)]
	};
};

export type FlashStats = {
	total: number;
	/** 已经过掉的张数。刷完一轮必然等于 total —— 别拿它当成绩。 */
	known: number;
	/** 还在队列里的张数 */
	remaining: number;
	/** 还在队列里、且被标过「再练」的张数 —— 刷卡途中的「待重练」 */
	pendingAgain: number;
	/** 这一轮标过「再练」的总张数（含已经过掉的） */
	struggled: number;
	/** 一次就过、从没标过「再练」的张数 —— 这才是这一轮的成绩 */
	firstTry: number;
	/** 秒 */
	elapsed: number;
	pct: number;
	finished: boolean;
};

export const stats = (session: FlashSession, now = Date.now()): FlashStats => {
	const total = session.deck.cards.length;
	const known = session.known.length;
	const struggled = session.deck.cards.filter(
		(card) => (session.attempts[card.id]?.again ?? 0) > 0
	).length;
	const pendingAgain = session.queue.filter((id) => (session.attempts[id]?.again ?? 0) > 0).length;

	return {
		total,
		known,
		remaining: session.queue.length,
		pendingAgain,
		struggled,
		firstTry: total - struggled,
		elapsed: ((session.endedAt ?? now) - session.startedAt) / 1000,
		pct: total > 0 ? Math.round((known / total) * 100) : 0,
		finished: session.endedAt !== null
	};
};
