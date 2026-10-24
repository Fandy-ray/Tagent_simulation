<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { loadKatex } from '$lib/data/math';

	import { generateFlashDeck } from '$lib/apis/agent';
	import FlashCard from '$lib/components/quiz/FlashCard.svelte';
	import { formatDuration } from '$lib/data/exam';
	import MathText from '$lib/components/MathText.svelte';
	import {
		advance,
		answerLabel,
		cardHeadline,
		createSession,
		currentCard,
		focusCard,
		gradeAnswer,
		recordAnswer,
		replayStruggled,
		rotateQueue,
		stats,
		type FlashSession
	} from '$lib/data/flash';

	type Phase = 'generating' | 'studying' | 'summary' | 'failed';

	/**
	 * 客户端等待上限。后端 FLASH_LLM_BUDGET=200s 已经封了顶，这里只是"服务端
	 * 再也不会回话了"的兜底（实测正常出卡 6~10 秒，这条基本不该触发）。
	 */
	const CLIENT_TIMEOUT_MS = 240_000;

	type Props = {
		modelId: string;
		topic: string;
		notebookIds: string[];
		onTitle: (title: string) => void;
		onError: (message: string) => void;
		onExit: () => void;
		onSwitchToFull: () => void;
		/** 报给外壳：现在离开会丢掉什么。空字符串＝没有进度，可以直接走。 */
		onLeavingCost?: (cost: string) => void;
	};

	let {
		modelId,
		topic,
		notebookIds,
		onTitle,
		onError,
		onExit,
		onSwitchToFull,
		onLeavingCost
	}: Props = $props();

	let phase = $state<Phase>('generating');
	let session = $state<FlashSession | null>(null);
	let inputMode = $state<'flip' | 'type'>('flip');

	let flipped = $state(false);
	let typed = $state('');
	let picked = $state<number | null>(null);
	let graded = $state<'correct' | 'wrong' | null>(null);

	let elapsed = $state(0);
	let ticker: ReturnType<typeof setInterval> | null = null;
	let controller: AbortController | null = null;
	let failure = $state('');

	let card = $derived(session ? currentCard(session) : null);
	let summary = $derived(session ? stats(session) : null);

	// 卡组只在内存里，退出即丢。刷了一半时让外壳问一句再走。
	$effect(() => {
		if (!onLeavingCost) {
			return;
		}
		const done = summary && phase === 'studying' ? summary.total - summary.remaining : 0;
		onLeavingCost(
			phase === 'studying' && summary && done > 0
				? `这组闪卡刷了 ${done} / ${summary.total} 张，进度不会保存`
				: ''
		);
		// 卸载时自己把话收回去。外壳那边切模式时也会清一次，但不该靠它记得——
		// 留着的话，切到整卷后按返回，弹出来的还是「这组闪卡刷了 N 张」。
		return () => onLeavingCost('');
	});

	let position = $derived(
		session && card ? `${session.known.length + 1}/${session.deck.cards.length}` : ''
	);

	let dots = $derived.by(() => {
		const current = session;

		if (!current) {
			return [];
		}

		const currentId = current.queue[0];

		return current.deck.cards.map((item) => {
			const done = current.known.includes(item.id);
			const struggled = (current.attempts[item.id]?.again ?? 0) > 0;

			return {
				id: item.id,
				current: item.id === currentId,
				clickable: !done && item.id !== currentId,
				className:
					item.id === currentId
						? 'size-2.5 bg-blue-500'
						: done
							? 'size-2 bg-emerald-400'
							: struggled
								? 'size-2 bg-amber-400'
								: 'size-2 bg-gray-700'
			};
		});
	});

	const stopTicker = () => {
		if (ticker !== null) {
			clearInterval(ticker);
			ticker = null;
		}
	};

	const resetCardState = () => {
		flipped = false;
		typed = '';
		picked = null;
		graded = null;
	};

	const start = () => {
		if (!modelId) {
			onError('请先选择可用模型。');
			onExit();
			return;
		}

		controller?.abort();
		const own = new AbortController();
		controller = own;
		const signal = own.signal;

		// 超时与"用户主动取消/面板卸载"都会 abort，但两者该有完全不同的下场，
		// 所以用这个局部标记把它们区分开。
		let timedOut = false;
		const ceiling = setTimeout(() => {
			timedOut = true;
			own.abort();
		}, CLIENT_TIMEOUT_MS);

		failure = '';
		phase = 'generating';
		session = null;
		resetCardState();
		elapsed = 0;
		stopTicker();
		ticker = setInterval(() => {
			elapsed += 1;
		}, 1000);

		// 等模型出题的这几秒顺手把 KaTeX 下好（$lib/data/math 的 loadKatex），题目出来时公式不先闪一下原文
		void loadKatex();
		void generateFlashDeck(modelId, topic, notebookIds, signal)
			.then((deck) => {
				clearTimeout(ceiling);

				if (signal.aborted) {
					return;
				}

				stopTicker();
				onTitle(deck.title);
				session = createSession(deck);
				phase = 'studying';
			})
			.catch((error: unknown) => {
				clearTimeout(ceiling);

				if (timedOut) {
					stopTicker();
					failure = '等了 4 分钟还没出卡，basic-agent 可能没在正常回话。';
					phase = 'failed';
					return;
				}

				// 主动取消或面板已卸载：这一轮不该再改任何状态
				if (signal.aborted) {
					return;
				}

				stopTicker();
				// **就地停下，不要 onExit()**。以前失败就弹回模式选择首屏，
				// 最常见的触发是 429（并发闸门满）——而"取消"只能掐断浏览器这边，
				// 服务端那次还在跑、名额还占着，于是取消后立刻重试必然 429、
				// 必然被弹回去，看起来就像点一下自己退回去了。
				failure = error instanceof Error ? error.message : '出卡失败，请重试。';
				phase = 'failed';
			});
	};

	const cancel = () => {
		controller?.abort();
		controller = null;
		stopTicker();
		onExit();
	};

	const retry = () => {
		failure = '';
		start();
	};

	const reveal = () => {
		flipped = true;
	};

	const settle = (answer: string | number) => {
		if (!session || !card || flipped) {
			return;
		}

		const verdict = gradeAnswer(card, answer);
		graded = verdict;
		session = recordAnswer(session, card.id, answerLabel(card, answer), verdict);
		flipped = true;
	};

	const submitAnswer = () => settle(typed);

	/** 选择卡：点一下就判，不用再点「提交」——零摩擦才是选择卡存在的理由。 */
	const pickOption = (index: number) => {
		if (flipped) {
			return;
		}

		picked = index;
		settle(index);
	};

	const judge = (outcome: 'known' | 'again') => {
		if (!session) {
			return;
		}

		session = advance(session, outcome);
		resetCardState();

		if (session.queue.length === 0) {
			phase = 'summary';
		}
	};

	const rotate = (direction: 1 | -1) => {
		if (!session || flipped) {
			return;
		}

		session = rotateQueue(session, direction);
		resetCardState();
	};

	const jumpTo = (cardId: string) => {
		if (!session || flipped) {
			return;
		}

		session = focusCard(session, cardId);
		resetCardState();
	};

	const replayAgainOnly = () => {
		if (!session) {
			return;
		}

		session = replayStruggled(session);
		resetCardState();
		phase = 'studying';
	};

	const switchInputMode = (next: 'flip' | 'type') => {
		if (inputMode === next) {
			return;
		}

		inputMode = next;
		resetCardState();
	};

	const onKeydown = (event: KeyboardEvent) => {
		if (phase !== 'studying' || event.isComposing) {
			return;
		}

		if (event.ctrlKey || event.altKey || event.metaKey) {
			return;
		}

		const target = event.target;
		const inField =
			target instanceof Element &&
			target.closest('input, textarea, select, [contenteditable="true"]') !== null;

		if (event.key === ' ' && !inField) {
			event.preventDefault();

			// 选择卡和输入作答都要先给出答案才谈得上翻面
			if (!flipped && (card?.type === 'choice' || inputMode === 'type')) {
				return;
			}

			flipped = !flipped;
			return;
		}

		// 选择卡支持按 A~D 直接选
		if (!flipped && !inField && card?.type === 'choice') {
			const index = ['a', 'b', 'c', 'd'].indexOf(event.key.toLowerCase());
			if (index >= 0 && index < card.options.length) {
				event.preventDefault();
				pickOption(index);
				return;
			}
		}

		if (flipped && (event.key === '1' || event.key === '2') && !inField) {
			event.preventDefault();
			judge(event.key === '1' ? 'known' : 'again');
			return;
		}

		if (!inField && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
			event.preventDefault();
			rotate(event.key === 'ArrowRight' ? 1 : -1);
		}
	};

	onMount(() => {
		window.addEventListener('keydown', onKeydown);
		start();
	});

	onDestroy(() => {
		stopTicker();
		controller?.abort();

		if (typeof window !== 'undefined') {
			window.removeEventListener('keydown', onKeydown);
		}
	});
</script>

{#if phase === 'generating'}
	<div class="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
		<svg
			class="size-8 animate-spin text-blue-500"
			viewBox="0 0 24 24"
			fill="none"
			aria-hidden="true"
		>
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"
			></circle>
			<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"
			></path>
		</svg>

		<div class="font-mono text-3xl font-bold">{formatDuration(elapsed)}</div>

		<div class="text-sm text-gray-400">正在生成闪卡</div>

		<p class="max-w-sm text-xs leading-relaxed text-gray-500">
			三片同时向模型发问，每片只拿三分之一的材料 —— 既是提速的办法，也让三片不容易撞到同一个考点。
			服务端不分段回报，所以这里只报总用时；具体多久取决于你选的模型。
		</p>

		<button
			type="button"
			class="mt-1 rounded-xl border border-gray-700 px-5 py-2 text-sm text-gray-400 transition hover:bg-gray-800 hover:text-gray-200"
			onclick={cancel}
		>
			取消
		</button>
	</div>
{:else if phase === 'failed'}
	<div class="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
		<svg
			class="size-8 text-amber-400"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<path d="M12 9v4"></path>
			<path d="M12 17h.01"></path>
			<path
				d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"
			></path>
		</svg>

		<div class="text-sm font-medium">这一轮没能出卡</div>

		<p class="max-w-sm text-sm leading-relaxed text-gray-400">{failure}</p>

		{#if failure.includes('过多')}
			<p class="max-w-sm text-xs leading-relaxed text-gray-500">
				服务端同时只接两个出题/判分请求。刚才如果点过「取消」，那一次在服务端其实还在跑、名额还占着
				—— 等十几秒再重试就好。
			</p>
		{/if}

		<div class="mt-1 flex gap-2">
			<button
				type="button"
				class="rounded-xl bg-white px-5 py-2.5 text-sm font-medium text-gray-900 transition hover:bg-gray-200"
				onclick={retry}
			>
				重试
			</button>

			<button
				type="button"
				class="rounded-xl border border-gray-700 px-5 py-2.5 text-sm text-gray-400 transition hover:bg-gray-800 hover:text-gray-200"
				onclick={onExit}
			>
				返回模式选择
			</button>
		</div>
	</div>
{:else if phase === 'studying' && session && card}
	<div class="flex h-full min-h-0 flex-col">
		<!-- 窄屏（<640px）竖排：模式切换在上、进度在下。并排时进度那一栏会被挤扁，
		     实测 375px 下「已过 x / y」和百分比直接撞成两行。 -->
		<div class="flex shrink-0 flex-col-reverse gap-2 pb-2 sm:flex-row sm:items-center sm:gap-3">
			<div class="min-w-0 flex-1">
				<div class="h-1.5 overflow-hidden rounded-full bg-gray-800">
					<div
						class="h-full rounded-full bg-gradient-to-r from-blue-500 to-sky-400 transition-all duration-300"
						style={`width: ${summary?.pct ?? 0}%`}
					></div>
				</div>

				<div class="mt-1 flex justify-between font-mono text-[11px] text-gray-500">
					<span>
						已过 {summary?.known ?? 0} / {summary?.total ?? 0} · 待重练 {summary?.pendingAgain ?? 0}
					</span>
					<span>{summary?.pct ?? 0}%</span>
				</div>
			</div>

			<div
				class="flex shrink-0 items-center gap-0.5 self-end rounded-xl border border-white/[0.18] p-0.5 sm:self-auto"
			>
				<button
					type="button"
					class={`rounded-lg px-2.5 py-1.5 text-xs transition ${
						inputMode === 'flip'
							? 'bg-blue-500 font-semibold text-white'
							: 'text-gray-400 hover:text-gray-200'
					}`}
					title="只影响填空卡；选择卡一律点选作答"
					onclick={() => switchInputMode('flip')}
				>
					翻卡自评
				</button>

				<button
					type="button"
					class={`rounded-lg px-2.5 py-1.5 text-xs transition ${
						inputMode === 'type'
							? 'bg-blue-500 font-semibold text-white'
							: 'text-gray-400 hover:text-gray-200'
					}`}
					onclick={() => switchInputMode('type')}
				>
					输入作答
				</button>
			</div>
		</div>

		<div class="flex min-h-0 flex-1 items-stretch gap-2">
			<!-- 窄屏藏起左右键：一张卡在 375px 下只剩 ~215px 可读宽度，
			     句子被切得七零八落。跳卡在窄屏用底部的圆点，够用了。 -->
			<button
				type="button"
				class="hidden min-h-11 min-w-11 self-center rounded-xl border border-gray-700 text-2xl leading-none transition hover:bg-gray-800 disabled:opacity-40 disabled:hover:bg-transparent sm:block"
				disabled={flipped || session.queue.length < 2}
				onclick={() => rotate(-1)}
				aria-label="看待过队列里的上一张"
				title="上一张（←）"
			>
				‹
			</button>

			<div class="flex min-h-0 min-w-0 flex-1 items-center justify-center">
				{#key `${card.id}-${inputMode}`}
					<FlashCard
						{card}
						{inputMode}
						{flipped}
						{typed}
						{picked}
						{graded}
						{position}
						onReveal={reveal}
						onTyped={(value) => (typed = value)}
						onSubmit={submitAnswer}
						onPick={pickOption}
					/>
				{/key}
			</div>

			<button
				type="button"
				class="hidden min-h-11 min-w-11 self-center rounded-xl border border-gray-700 text-2xl leading-none transition hover:bg-gray-800 disabled:opacity-40 disabled:hover:bg-transparent sm:block"
				disabled={flipped || session.queue.length < 2}
				onclick={() => rotate(1)}
				aria-label="这张先跳过，看下一张"
				title="下一张（→）"
			>
				›
			</button>
		</div>

		<div class="mt-3 flex shrink-0 items-center gap-3 border-t border-gray-800 pt-3">
			<div class="min-w-0 flex-1 overflow-x-auto">
				<div class="flex min-w-max items-center gap-1.5">
					{#each dots as dot (dot.id)}
						<button
							type="button"
							class={`shrink-0 rounded-full transition ${dot.className} ${
								dot.clickable ? 'cursor-pointer hover:opacity-80' : 'cursor-default'
							}`}
							disabled={!dot.clickable || flipped}
							onclick={() => jumpTo(dot.id)}
							aria-label={`跳到 ${dot.id}`}
							title={dot.id}
						></button>
					{/each}
				</div>
			</div>

			{#if flipped}
				<!--
					本地已经判过对错时，默认动作要跟着判定走：答错了主按钮就是「进重练」，
					「其实我答对了」降成弱按钮留作纠正（比对判错时仍然需要）。
					原来两个按钮一样重，答错也能顺手点「会了」，错题就悄悄漏出了重练队列。
				-->
				<div class="flex shrink-0 gap-2">
					{#if graded === 'wrong'}
						<button
							type="button"
							class="rounded-xl border border-gray-700 px-3 py-2.5 text-xs text-gray-400 transition hover:bg-white/5 hover:text-gray-200"
							onclick={() => judge('known')}
						>
							其实我答对了
						</button>

						<button
							type="button"
							class="rounded-xl border border-amber-900 bg-amber-950/60 px-4 py-2.5 text-sm font-medium text-amber-200 transition hover:bg-amber-950/80"
							onclick={() => judge('again')}
						>
							进重练
						</button>
					{:else}
						<button
							type="button"
							class="rounded-xl border border-amber-900 bg-amber-950/40 px-4 py-2.5 text-sm font-medium text-amber-300 transition hover:bg-amber-950/70"
							onclick={() => judge('again')}
						>
							再练一次
						</button>

						<button
							type="button"
							class="rounded-xl border border-emerald-900 bg-emerald-950/50 px-4 py-2.5 text-sm font-medium text-emerald-300 transition hover:bg-emerald-950/80"
							onclick={() => judge('known')}
						>
							会了
						</button>
					{/if}
				</div>
			{:else if inputMode === 'flip'}
				<button
					type="button"
					class="shrink-0 rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-gray-900 transition hover:bg-gray-200"
					onclick={reveal}
				>
					看答案
				</button>
			{/if}
		</div>
	</div>
{:else if phase === 'summary' && session && summary}
	{@const struggledCards = session.deck.cards.filter(
		(item) => (session?.attempts[item.id]?.again ?? 0) > 0
	)}

	<div class="flex h-full min-h-0 flex-col items-center overflow-y-auto px-4 py-2 text-center">
		<div class="mt-2 font-mono text-xs tracking-[0.2em] text-gray-500">这组刷完了</div>

		<!-- 主数字用「一次过」而不是「会了」：队列空了才算刷完，
		     所以「会了」的张数永远等于卡组大小，拿它当成绩没有意义。 -->
		<div class="mt-2.5 font-mono text-6xl leading-none font-bold text-blue-500">
			{summary.firstTry}<span class="text-lg text-gray-400"> / {summary.total}</span>
		</div>

		<p class="mt-2 text-sm text-gray-400">
			{#if summary.struggled === 0}
				这一轮全部一次过，没有需要重练的卡。
			{:else}
				这一轮 {summary.firstTry} 张一次就过，另外 {summary.struggled} 张重练之后才记住。
			{/if}
		</p>

		<div class="mt-4 flex flex-wrap justify-center gap-2 font-mono text-xs">
			<div
				class="rounded-xl border border-emerald-900 bg-emerald-950/40 px-3.5 py-2 text-emerald-300"
			>
				一次过 <b class="text-sm">{summary.firstTry}</b>
			</div>
			<div class="rounded-xl border border-amber-900 bg-amber-950/40 px-3.5 py-2 text-amber-300">
				重练过 <b class="text-sm">{summary.struggled}</b>
			</div>
			<div class="rounded-xl border border-gray-700 bg-gray-800 px-3.5 py-2 text-gray-300">
				用时 <b class="text-sm">{formatDuration(summary.elapsed)}</b>
			</div>
		</div>

		{#if struggledCards.length > 0}
			<div class="mt-6 w-full max-w-2xl border-t border-gray-800 pt-4 text-left">
				<div class="text-xs font-semibold text-amber-300">
					待重练的 {struggledCards.length} 张
				</div>

				<div class="mt-2.5 flex flex-col gap-2">
					{#each struggledCards as item (item.id)}
						{@const attempt = session?.attempts[item.id]}
						<div class="flex items-center gap-2.5 rounded-xl border border-gray-700 px-3.5 py-2.5">
							<span class="shrink-0 font-mono text-[11px] text-gray-500">{item.id}</span>

							<span class="min-w-0 flex-1 truncate text-[13px] text-gray-300">
								<MathText value={cardHeadline(item)} />
							</span>

							{#if attempt?.graded === 'wrong'}
								<span class="shrink-0 font-mono text-[11px] text-red-300">
									答错：{attempt.answer.trim() || '未作答'}
								</span>
							{:else}
								<span class="shrink-0 font-mono text-[11px] text-amber-300">自评：再练</span>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<div class="mt-5 flex w-full max-w-2xl flex-wrap justify-center gap-2">
			{#if struggledCards.length > 0}
				<button
					type="button"
					class="rounded-xl bg-white px-5 py-2.5 text-sm font-medium text-gray-900 transition hover:bg-gray-200"
					onclick={replayAgainOnly}
				>
					只重刷这 {struggledCards.length} 张
				</button>
			{/if}

			<button
				type="button"
				class="rounded-xl border border-gray-700 px-5 py-2.5 text-sm transition hover:bg-gray-800"
				onclick={start}
			>
				再来一组闪卡
			</button>

			<button
				type="button"
				class="rounded-xl border border-gray-700 px-5 py-2.5 text-sm text-gray-400 transition hover:bg-gray-800 hover:text-gray-200"
				onclick={onSwitchToFull}
			>
				换整卷练大题
			</button>
		</div>

		<p class="mt-4 mb-2 font-mono text-[11px] text-gray-600">全程未调用判卷模型 · 本地判定</p>
	</div>
{/if}
