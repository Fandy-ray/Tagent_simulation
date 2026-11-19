/**
 * 极简的「同一份结果短时间内复用」缓存。
 *
 * 用处：答疑页每次挂载都要列一遍笔记本，而列一遍是 1 + 2N 个请求
 * （笔记本、每本的来源、每本的笔记）。在页面间来回切时这些请求会整轮重发，
 * 笔记本一多就明显卡。内容本来也不会秒秒钟变，缓存十几秒足够。
 *
 * 顺带把「同时发起的多次请求」合并成一次：第二个调用方拿到的是第一个的 Promise，
 * 不会再打一轮。
 *
 * 不 import 任何东西，时钟可注入，能用 node --test 单测。
 */

type Entry<T> = { at: number; value: Promise<T> };

export type TtlCache<T> = {
	get(load: () => Promise<T>): Promise<T>;
	invalidate(): void;
};

export function createTtlCache<T>(ttlMs = 15_000, now: () => number = Date.now): TtlCache<T> {
	let entry: Entry<T> | null = null;

	return {
		get(load) {
			if (entry && now() - entry.at < ttlMs) {
				return entry.value;
			}
			const value = load();
			entry = { at: now(), value };
			// 失败的结果不留着：下次调用要能重新试，否则一次网络抖动会被缓存住
			value.catch(() => {
				if (entry?.value === value) {
					entry = null;
				}
			});
			return value;
		},
		invalidate() {
			entry = null;
		}
	};
}

/** Keep cached account data inside the identity and course that requested it. */
export function createScopedTtlCache<T>(
	scope: () => string,
	ttlMs = 15_000,
	now: () => number = Date.now
): TtlCache<T> {
	let activeScope: string | null = null;
	const cache = createTtlCache<T>(ttlMs, now);
	return {
		get(load) {
			const requestedScope = scope();
			if (activeScope !== requestedScope) {
				cache.invalidate();
				activeScope = requestedScope;
			}
			return cache.get(async () => {
				const value = await load();
				if (activeScope !== requestedScope || scope() !== requestedScope) {
					throw new Error('账号或课程已切换，请重新载入笔记本。');
				}
				return value;
			});
		},
		invalidate() {
			cache.invalidate();
		}
	};
}
