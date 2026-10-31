<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { loadKatex } from '$lib/data/math';

	import { streamFlashDeck } from '$lib/apis/agent';
	import FlashCard from '$lib/components/quiz/FlashCard.svelte';
	import { formatDuration } from '$lib/data/exam';
	import MathText from '$lib/components/MathText.svelte';
	import {
		advance,
		answerLabel,
		cardHeadline,
		clearFlashDeck,
		createSession,
		currentCard,
		focusCard,
		gradeAnswer,
		recordAnswer,
		replayStruggled,
		rotateQueue,
		saveFlashDeck,
		stats,
		type FlashSession,
		type SavedFlashDeck
	} from '$lib/data/flash';
	import { appendCards } from '$lib/data/flashStream';

	type Phase = 'generating' | 'studying' | 'summary' | 'failed';

	/**
	 * 客户端等待上限。后端 FLASH_LLM_BUDGET=200s 已经封了顶，这里只是"服务端
	 * 再也不会回话了"的兜底（实测第一张 1 秒左右到、整组 3 秒左右写完，这条基本不该触发）。
	 */
	const CLIENT_TIMEOUT_MS = 240_000;
	/**
	 * 第一张卡平时一秒左右就到，等过这么久还没有就换成「比平时慢」的说法。
	 * 只拿来切换文案，秒数本身不上屏：用户不需要看我们内部的计时。
	 */
	const SLOW_AFTER_S = 12;
	/** 一组最多 12 张（后端分片上限），进度条上还在写的占位格不会超过它 */
	const DECK_MAX_CARDS = 12;

	type Props = {
		modelId: string;
		topic: string;
		notebookIds: string[];
		/** flip = 翻卡自评；type = 输入作答。开关在外壳顶栏 */
		inputMode?: 'flip' | 'type';
		onTitle: (title: string) => void;
		onError: (message: string) => void;
		onExit: () => void;
		onSwitchToFull: () => void;
		/** 报给外壳：现在结束这一轮会丢掉什么。空字符串＝没有进度，可以直接走。 */
		onLeavingCost?: (cost: string) => void;
		/** 上次退出时存下的卡组：有它就接着刷，不重新出卡 */
		resume?: SavedFlashDeck | null;
	};

	let {
		modelId,
		topic,
		notebookIds,
		inputMode = 'flip',
		onTitle,
		onError,
		onExit,
		onSwitchToFull,
		onLeavingCost,
		resume = null
	}: Props = $props();

	let phase = $state<Phase>('generating');
	let session = $state<FlashSession | null>(null);

	let flipped = $state(false);
	let typed = $state('');
	let picked = $state<number | null>(null);
	let graded = $state<'correct' | 'wrong' | null>(null);

	let elapsed = $state(0);
	let ticker: ReturnType<typeof setInterval> | null = null;
	let controller: AbortController | null = null;
	let failure = $state('');
	/** 后面还有卡在路上（边写边给，第一张到了就开始刷） */
	let incoming = $state(false);
	/** 已经在刷了、后面的卡却没出来：不打断刷卡，刷完到的这几张再停下来说明 */
	let cut = $state(false);

	let card = $derived(session ? currentCard(session) : null);
	let summary = $derived(session ? stats(session) : null);
	let slow = $derived(phase === 'generating' && elapsed >= SLOW_AFTER_S);

	// 到手的卡和进度随时存下来：点顶栏的「离开测评」、刷新都不丢（见 $lib/data/flash 的 SavedFlashDeck）
	$effect(() => {
		if (session && session.deck.cards.length > 0 && (phase === 'studying' || phase === 'summary')) {
			saveFlashDeck({ modelId, topic, notebookIds, session });
		}
	});

	// 「结束这一轮」是真的放弃这组卡：刷了一半时让外壳问一句再走。
	$effect(() => {
		if (!onLeavingCost) {
			return;
		}
		const done = summary && phase === 'studying' ? summary.total - summary.remaining : 0;
		onLeavingCost(
			phase === 'studying' && summary && done > 0
				? `这组闪卡刷了 ${done} / ${summary.total} 张，结束后进度就清掉了`
				: ''
		);
		// 卸载时自己把话收回去。外壳那边切模式时也会清一次，但不该靠它记得——
		// 留着的话，切到整卷后按返回，弹出来的还是「这组闪卡刷了 N 张」。
		return () => onLeavingCost('');
	});

	// 顶栏切了作答方式：把这张卡已经做的清掉，免得翻卡时的状态带进输入框
	let lastInputMode: 'flip' | 'type' | null = null;
	$effect(() => {
		const next = inputMode;
		if (lastInputMode !== null && lastInputMode !== next) {
			resetCardState();
		}
		lastInputMode = next;
	});

	// 还在出卡时总数后面带个 +：后面还有
	let more = $derived(incoming ? '+' : '');
	let position = $derived(
		session && card ? `${session.known.length + 1}/${session.deck.cards.length}${more}` : ''
	);

	// 顶上那条进度：一张卡一格。已过绿、重练后才过的带一截琥珀、正在看的白、
	// 进了重练还没过的琥珀、到了还没刷的灰。还在写的卡另画几格淡色占位——总数要等写完才知道
	let segments = $derived.by(() => {
		const current = session;

		if (!current) {
			return [];
		}

		const currentId = current.queue[0];

		return current.deck.cards.map((item) => {
			const done = current.known.includes(item.id);
			const struggled = (current.attempts[item.id]?.again ?? 0) > 0;
			const isCurrent = item.id === currentId;

			return {
				id: item.id,
				current: isCurrent,
				clickable: !done && !isCurrent,
				className: isCurrent
					? 'bg-white'
					: done
						? struggled
							? 'bg-[linear-gradient(90deg,#5ee9b5_70%,#ffd230_70%)]'
							: 'bg-emerald-300'
						: struggled
							? 'bg-amber-300/70'
							: 'bg-white/20',
				label: isCurrent
					? '正在看'
					: done
						? struggled
							? '重练后过'
							: '已过'
						: struggled
							? '待重练'
							: '还没刷'
			};
		});
	});

	let ghostCount = $derived(
		incoming && session ? Math.max(1, Math.min(3, DECK_MAX_CARDS - session.deck.cards.length)) : 0
	);

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
		cut = false;
		phase = 'generating';
		session = null;
		clearFlashDeck();
		incoming = true;
		resetCardState();
		elapsed = 0;
		stopTicker();
		ticker = setInterval(() => {
			elapsed += 1;
		}, 1000);

		// 等模型出题的这几秒顺手把 KaTeX 下好（$lib/data/math 的 loadKatex），题目出来时公式不先闪一下原文
		void loadKatex();
		void streamFlashDeck(modelId, topic, notebookIds, signal, (event) => {
			if (signal.aborted) {
				return;
			}
			if (event.type === 'deck') {
				onTitle(event.title);
				session = createSession({
					deck_id: event.deck_id,
					title: event.title,
					total_cards: 0,
					cards: []
				});
			} else if (event.type === 'title' && session) {
				onTitle(event.title);
				session = { ...session, deck: { ...session.deck, title: event.title } };
			} else if (event.type === 'card' && session) {
				session = appendCards(session, [event.card]);
				// 第一张到了就开始刷，后面的边刷边到
				if (phase === 'generating') {
					stopTicker();
					phase = 'studying';
				}
			}
		})
			.then(() => {
				clearTimeout(ceiling);

				if (signal.aborted) {
					return;
				}

				incoming = false;
				if (phase === 'generating') {
					// 后端一张没出成会报错，正常走不到这里；万一走到了也别一直转圈
					stopTicker();
					failure = '这一轮没有出卡，请重试。';
					phase = 'failed';
					return;
				}
				finishIfDrained();
			})
			.catch((error: unknown) => {
				clearTimeout(ceiling);

				// 超时与"用户主动取消/面板卸载"都会 abort，先看是不是超时
				if (!timedOut && signal.aborted) {
					// 主动取消或面板已卸载：这一轮不该再改任何状态
					return;
				}

				incoming = false;

				if (phase !== 'generating') {
					// 已经在刷了：不打断，先刷已经到的这几张；刷完了停在「后面的卡没出来」那一屏
					cut = true;
					return;
				}

				stopTicker();
				// **就地停下，不要 onExit()**。以前失败就弹回模式选择首屏，
				// 最常见的触发是 429（并发闸门满）——而"取消"只能掐断浏览器这边，
				// 服务端那次还在跑、名额还占着，于是取消后立刻重试必然 429、
				// 必然被弹回去，看起来就像点一下自己退回去了。
				failure = timedOut
					? '等了 4 分钟还没出完卡，basic-agent 可能没在正常回话。'
					: error instanceof Error
						? error.message
						: '出卡失败，请重试。';
				phase = 'failed';
			});
	};

	/** 接着刷上次退出时的那组卡：不调模型。退出时还在路上的卡就没有了，已经到的都在 */
	const restoreFrom = (saved: SavedFlashDeck) => {
		session = saved.session;
		incoming = false;
		onTitle(saved.session.deck.title);
		phase = saved.session.queue.length === 0 ? 'summary' : 'studying';
	};

	const showSummary = () => {
		if (!session) {
			return;
		}
		session = { ...session, endedAt: session.endedAt ?? Date.now() };
		phase = 'summary';
	};

	/**
	 * 卡都到齐了、已经到的又都刷完了：这一轮才算结束。
	 * 后面的卡没出来（cut）时不自动跳小结，停在说明那一屏，让人知道这组为什么比平时少。
	 */
	const finishIfDrained = () => {
		if (phase === 'studying' && session && session.queue.length === 0 && !incoming && !cut) {
			showSummary();
		}
	};

	/** 到的都刷完了、后面的还没写好，不想等：掐掉这一轮，用已经到的几张出小结 */
	const stopWaiting = () => {
		controller?.abort();
		controller = null;
		incoming = false;
		showSummary();
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
		// 已经到的刷完了、后面还有在路上的：留在刷卡页等下一张
		finishIfDrained();
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
		// 重刷的是已经到手的卡，和「后面的卡没出来」无关：不清掉的话，刷完又会停在那句说明上
		cut = false;
		resetCardState();
		phase = 'studying';
	};

	const onKeydown = (event: KeyboardEvent) => {
		// 刷完已经到的、等下一张的时候没有当前卡，按键一律不理
		if (phase !== 'studying' || !card || event.isComposing) {
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
		if (resume) {
			restoreFrom(resume);
		} else {
			start();
		}
	});

	onDestroy(() => {
		stopTicker();
		controller?.abort();

		if (typeof window !== 'undefined') {
			window.removeEventListener('keydown', onKeydown);
		}
	});
</script>

{#snippet keycap(label: string, onLight = false)}
	<kbd
		class={`rounded-md px-1.5 py-px font-sans text-[11px] font-normal ${
			onLight
				? 'bg-black/[0.06] text-gray-700'
				: 'border border-white/10 bg-white/[0.04] text-gray-300'
		}`}>{label}</kbd
	>
{/snippet}

{#snippet arrow(direction: 1 | -1, disabled: boolean)}
	<!-- 窄屏藏起左右键：一张卡在 375px 下只剩 ~215px 可读宽度，句子被切得七零八落。
	     跳卡在窄屏用顶上的进度格，够用了。 -->
	<button
		type="button"
		class="hover:bg-gray-850 hidden size-11 shrink-0 items-center justify-center rounded-xl text-gray-400 transition hover:text-white disabled:pointer-events-none disabled:text-gray-600 sm:flex"
		{disabled}
		onclick={() => rotate(direction)}
		aria-label={direction === 1 ? '这张先跳过，看下一张' : '看待过队列里的上一张'}
		title={direction === 1 ? '下一张（→）' : '上一张（←）'}
	>
		<svg
			class="size-5"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
			aria-hidden="true"
		>
			<path d={direction === 1 ? 'm9 18 6-6-6-6' : 'm15 18-6-6 6-6'}></path>
		</svg>
	</button>
{/snippet}

{#if phase === 'generating' || phase === 'studying'}
	<!-- 出卡中、刷卡、等下一张、出卡中断共用一个骨架：卡片永远在同一个位置，内容到了只是原地填进来 -->
	<div class="mx-auto flex h-full min-h-0 w-full max-w-[880px] flex-col px-4 py-5 sm:px-5 sm:py-7">
		<div class="shrink-0 sm:px-[60px]">
			<!-- 每格的线只有 4px，上下各留 10px 白：看着细，手指也点得中（约 24px 高） -->
			<div class="flex gap-1">
				{#if phase === 'generating' || !session}
					{#each [0, 1, 2, 3, 4, 5] as index (index)}
						<span class="flex-1 py-2.5" aria-hidden="true">
							<span
								class="block h-1 animate-pulse rounded-full bg-white/[0.08]"
								style={`animation-delay: ${index * 150}ms`}
							></span>
						</span>
					{/each}
				{:else}
					{#each segments as segment (segment.id)}
						<button
							type="button"
							class={`group flex-1 py-2.5 ${segment.clickable && !flipped ? 'cursor-pointer' : 'cursor-default'}`}
							disabled={!segment.clickable || flipped}
							onclick={() => jumpTo(segment.id)}
							aria-label={`${segment.id}，${segment.label}`}
							aria-current={segment.current ? 'true' : undefined}
							title={`${segment.id} · ${segment.label}`}
						>
							<span
								class={`block h-1 rounded-full transition ${segment.className} ${
									segment.clickable && !flipped ? 'group-hover:brightness-150' : ''
								}`}
							></span>
						</button>
					{/each}
					{#each Array.from({ length: ghostCount }, (_, index) => index) as index (index)}
						<span class="flex-1 py-2.5" aria-hidden="true">
							<span
								class="block h-1 animate-pulse rounded-full bg-white/[0.08]"
								style={`animation-delay: ${index * 200}ms`}
							></span>
						</span>
					{/each}
				{/if}
			</div>

			<div
				class="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500 tabular-nums"
			>
				<span>
					{#if phase === 'generating' || !summary}
						这组 6~12 张 · 第一张到了就开刷，其余边刷边到
					{:else if card}
						第 {summary.known + 1} 张 · 已过 <span class="text-gray-200">{summary.known}</span>
						张{summary.pendingAgain > 0 ? ` · 待重练 ${summary.pendingAgain}` : ''}
					{:else}
						已过 <span class="text-gray-200">{summary.known}</span> 张{summary.struggled > 0
							? ` · 其中 ${summary.struggled} 张重练后过`
							: ''}
					{/if}
				</span>

				<span aria-live="polite">
					{#if phase === 'generating'}
						{#if slow}
							<span
								class="inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 px-2.5 py-0.5 text-[11px] text-amber-300"
							>
								<span class="size-1.5 animate-pulse rounded-full bg-amber-300"></span>
								比平时慢一些
							</span>
						{:else}
							<span
								class="inline-flex items-center gap-1.5 rounded-full bg-sky-500/15 px-2.5 py-0.5 text-[11px] text-sky-300"
							>
								<span class="size-1.5 animate-pulse rounded-full bg-sky-300"></span>
								正在出卡
							</span>
						{/if}
					{:else if incoming}
						<span
							class="inline-flex items-center gap-1.5 rounded-full bg-sky-500/15 px-2.5 py-0.5 text-[11px] text-sky-300"
						>
							<span class="size-1.5 animate-pulse rounded-full bg-sky-300"></span>
							还在出卡 · 已到 {summary?.total ?? 0} 张
						</span>
					{:else if cut}
						<span
							class="inline-flex items-center rounded-full bg-amber-500/15 px-2.5 py-0.5 text-[11px] text-amber-300"
						>
							出卡中断 · 这组共 {summary?.total ?? 0} 张
						</span>
					{:else}
						共 {summary?.total ?? 0} 张
					{/if}
				</span>
			</div>
		</div>

		<div class="flex min-h-0 flex-1 items-center gap-4 py-5">
			{@render arrow(
				-1,
				phase !== 'studying' || !card || flipped || (session?.queue.length ?? 0) < 2
			)}

			<div class="relative flex h-full max-h-[400px] min-h-[300px] min-w-0 flex-1">
				<!-- 卡后面露出的一道边：一叠卡的意思 -->
				<div
					class="pointer-events-none absolute inset-x-5 top-2.5 -bottom-2.5 rounded-3xl border border-white/[0.05] bg-[#191919]"
					aria-hidden="true"
				></div>

				{#if phase === 'generating'}
					<div
						class="relative flex w-full flex-col rounded-3xl border border-white/[0.08] bg-[#1d1d1d] p-6 shadow-[0_24px_48px_-24px_rgba(0,0,0,0.6)] sm:px-8 sm:py-7"
					>
						<div class="flex items-center justify-between">
							<div class="exam-shim h-5 w-11 rounded-full"></div>
							<span class="text-[11px] text-gray-500">第 1 张</span>
						</div>

						<div class="flex flex-1 flex-col justify-center gap-4" aria-hidden="true">
							<div class="exam-shim h-2.5 w-[30%] rounded-full"></div>
							<div class="flex items-center gap-2.5">
								<div class="exam-shim h-4 w-[34%] rounded-full"></div>
								<div class="h-4 w-[88px] border-b-2 border-sky-300/40"></div>
								<div class="exam-shim h-4 flex-1 rounded-full"></div>
							</div>
							<div class="exam-shim h-4 w-[56%] rounded-full"></div>
						</div>

						{#if slow}
							<div
								class="flex items-start gap-2.5 rounded-2xl bg-amber-500/10 px-3.5 py-3 text-left"
							>
								<svg
									class="mt-0.5 size-4 shrink-0 text-amber-300"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.7"
									stroke-linecap="round"
									stroke-linejoin="round"
									aria-hidden="true"
								>
									<circle cx="12" cy="12" r="9"></circle>
									<path d="M12 7v5l3 2"></path>
								</svg>
								<p class="text-[13px] leading-relaxed text-amber-100">
									可能在排队，再稍等一下。真出不来的话会直接告诉你原因，不会一直卡在这里。
								</p>
							</div>
						{:else}
							<div class="flex items-center justify-center gap-1 text-[13px] text-gray-400">
								{#each [0, 1, 2] as index (index)}
									<span
										class="size-1 animate-pulse rounded-full bg-gray-400"
										style={`animation-delay: ${index * 150}ms`}
									></span>
								{/each}
								<span class="ml-1.5">正在写第一张，马上就好</span>
							</div>
						{/if}
					</div>
				{:else if card}
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
				{:else if cut}
					<div
						class="relative flex w-full flex-col items-center justify-center gap-2.5 rounded-3xl border border-white/[0.08] bg-[#1d1d1d] p-8 text-center"
					>
						<div class="mb-2 flex size-11 items-center justify-center rounded-2xl bg-amber-500/15">
							<svg
								class="size-5 text-amber-300"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.7"
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
						</div>
						<div class="text-[17px] font-medium text-white">后面的卡没出来</div>
						<p class="max-w-sm text-[13px] leading-relaxed text-gray-500">
							这组只出了 {summary?.total ?? 0} 张，到的都刷完了，进度没丢。
						</p>
						<div class="mt-3 flex flex-wrap justify-center gap-2">
							<button
								type="button"
								class="min-h-10 rounded-full bg-white px-5 text-sm font-medium text-black transition hover:bg-gray-200"
								onclick={showSummary}
							>
								看这 {summary?.total ?? 0} 张的小结
							</button>
							<button
								type="button"
								class="min-h-10 rounded-full border border-white/10 bg-white/[0.03] px-5 text-sm text-gray-300 transition hover:bg-white/[0.08] hover:text-white"
								onclick={start}
							>
								再来一组
							</button>
						</div>
					</div>
				{:else}
					<div
						class="relative flex w-full flex-col items-center justify-center gap-2.5 rounded-3xl border border-dashed border-white/[0.12] bg-gray-900 p-8 text-center"
					>
						<div class="exam-bob relative mb-3 h-[46px] w-16" aria-hidden="true">
							<div
								class="absolute inset-0 translate-x-[7px] translate-y-[5px] rotate-[8deg] rounded-[10px] border border-white/[0.06] bg-[#1b1b1b]"
							></div>
							<div
								class="absolute inset-0 flex items-center justify-center gap-1 rounded-[10px] border border-white/10 bg-[#222]"
							>
								{#each [0, 1, 2] as index (index)}
									<span
										class="size-1 animate-pulse rounded-full bg-sky-300"
										style={`animation-delay: ${index * 200}ms`}
									></span>
								{/each}
							</div>
						</div>
						<div class="text-[17px] font-medium text-white">下一张还在写</div>
						<p class="max-w-sm text-[13px] leading-relaxed text-gray-500">
							到的 {summary?.total ?? 0} 张都刷完了。新卡一到就自动翻出来，不用点。
						</p>
						<button
							type="button"
							class="mt-3 min-h-9 rounded-full border border-white/10 bg-white/[0.03] px-4 text-[13px] text-gray-300 transition hover:bg-white/[0.08] hover:text-white"
							onclick={stopWaiting}
						>
							不等了，先看这 {summary?.total ?? 0} 张的小结
						</button>
					</div>
				{/if}
			</div>

			{@render arrow(
				1,
				phase !== 'studying' || !card || flipped || (session?.queue.length ?? 0) < 2
			)}
		</div>

		<div class="flex min-h-10 shrink-0 flex-wrap items-center justify-between gap-3 sm:px-[60px]">
			{#if phase === 'generating'}
				<!-- 快捷键提示只给有键盘的宽屏；手机上只留「取消」 -->
				<div class="hidden flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-500 sm:flex">
					<span class="inline-flex items-center gap-1.5">{@render keycap('空格')}翻面</span>
					<span class="inline-flex items-center gap-1.5">{@render keycap('A–D')}选项</span>
					<span class="inline-flex items-center gap-1.5">{@render keycap('1')}会了</span>
					<span class="inline-flex items-center gap-1.5">{@render keycap('2')}再练</span>
					<span class="inline-flex items-center gap-1.5">{@render keycap('← →')}跳过</span>
				</div>
				<button
					type="button"
					class="ml-auto min-h-9 rounded-full border border-white/10 bg-white/[0.03] px-4 text-[13px] text-gray-300 transition hover:bg-white/[0.08] hover:text-white"
					onclick={cancel}
				>
					取消
				</button>
			{:else if card}
				<div class="text-xs text-gray-500">
					{#if flipped}
						{graded === 'wrong'
							? '答错了：进重练的卡过一会儿会再考你'
							: '会了就过，没把握就再练一次'}
					{:else if incoming}
						新到的卡排在队尾，不会打断你
					{:else}
						<span class="hidden items-center gap-1.5 sm:inline-flex"
							>{@render keycap('← →')}先跳过这张</span
						>
					{/if}
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
								class="inline-flex min-h-10 items-center gap-2 rounded-full px-4 text-[13px] text-gray-400 transition hover:bg-white/[0.06] hover:text-white"
								onclick={() => judge('known')}
							>
								其实我答对了{@render keycap('1')}
							</button>
							<button
								type="button"
								class="inline-flex min-h-10 items-center gap-2 rounded-full bg-amber-500/15 pr-3 pl-5 text-sm font-medium text-amber-200 transition hover:bg-amber-500/25"
								onclick={() => judge('again')}
							>
								进重练{@render keycap('2')}
							</button>
						{:else}
							<button
								type="button"
								class="inline-flex min-h-10 items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] pr-3 pl-5 text-sm text-gray-300 transition hover:bg-white/[0.08] hover:text-white"
								onclick={() => judge('again')}
							>
								再练一次{@render keycap('2')}
							</button>
							<button
								type="button"
								class="inline-flex min-h-10 items-center gap-2 rounded-full bg-white pr-3 pl-5 text-sm font-medium text-black transition hover:bg-gray-200"
								onclick={() => judge('known')}
							>
								会了{@render keycap('1', true)}
							</button>
						{/if}
					</div>
				{:else if inputMode === 'flip'}
					<button
						type="button"
						class={`inline-flex min-h-10 shrink-0 items-center gap-2.5 rounded-full bg-white text-sm font-medium text-black transition hover:bg-gray-200 ${
							card.type === 'cloze' ? 'pr-3.5 pl-5' : 'px-5'
						}`}
						onclick={reveal}
					>
						看答案
						<!-- 空格只翻填空卡：选择卡要先选一个才翻面（见 onKeydown），这里就别提示空格了 -->
						{#if card.type === 'cloze'}{@render keycap('空格', true)}{/if}
					</button>
				{/if}
			{:else}
				<div class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-500">
					<span class="inline-flex items-center gap-1.5">
						<span class="h-1 w-3 rounded-full bg-emerald-300"></span>已过
					</span>
					<span class="inline-flex items-center gap-1.5">
						<span class="h-1 w-3 rounded-full bg-[linear-gradient(90deg,#5ee9b5_70%,#ffd230_70%)]"
						></span>重练后过
					</span>
					{#if incoming}
						<span class="inline-flex items-center gap-1.5">
							<span class="h-1 w-3 rounded-full bg-white/[0.16]"></span>还在写
						</span>
					{/if}
				</div>
			{/if}
		</div>
	</div>
{:else if phase === 'failed'}
	<div class="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
		<div class="mb-2 flex size-11 items-center justify-center rounded-2xl bg-amber-500/15">
			<svg
				class="size-5 text-amber-300"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="1.7"
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
		</div>

		<div class="text-[17px] font-medium text-white">这一轮没能出卡</div>

		<p class="max-w-sm text-sm leading-relaxed text-gray-400">{failure}</p>

		{#if failure.includes('过多')}
			<p class="max-w-sm text-xs leading-relaxed text-gray-500">
				同时在出题的人有点多。刚才如果点过「取消」，上一轮其实还在收尾，等十几秒再重试就好。
			</p>
		{/if}

		<div class="mt-3 flex flex-wrap justify-center gap-2">
			<button
				type="button"
				class="min-h-10 rounded-full bg-white px-5 text-sm font-medium text-black transition hover:bg-gray-200"
				onclick={retry}
			>
				重试
			</button>

			<button
				type="button"
				class="min-h-10 rounded-full border border-white/10 bg-white/[0.03] px-5 text-sm text-gray-300 transition hover:bg-white/[0.08] hover:text-white"
				onclick={onExit}
			>
				返回模式选择
			</button>
		</div>
	</div>
{:else if phase === 'summary' && session && summary}
	{@const struggledCards = session.deck.cards.filter(
		(item) => (session?.attempts[item.id]?.again ?? 0) > 0
	)}

	<!-- safe center：卡少时小结居中，待重练的一多照样从顶上开始滚 -->
	<div
		class="flex h-full min-h-0 flex-col items-center [justify-content:safe_center] overflow-y-auto px-4 py-8 text-center"
	>
		<div class="mt-2 text-xs tracking-[0.2em] text-gray-500">这组刷完了</div>

		<!-- 主数字用「一次过」而不是「会了」：队列空了才算刷完，
		     所以「会了」的张数永远等于卡组大小，拿它当成绩没有意义。 -->
		<div class="mt-4 text-6xl leading-none font-semibold text-white tabular-nums">
			{summary.firstTry}<span class="text-lg font-normal text-gray-500"> / {summary.total}</span>
		</div>
		<div class="mt-2 text-xs text-gray-500">一次就过</div>

		{#if cut}
			<p class="mt-3 max-w-md text-xs leading-relaxed text-amber-300">
				这组只出了 {summary.total} 张，后面的没出来。
			</p>
		{/if}

		<p class="mt-3 text-sm text-gray-400">
			{#if summary.struggled === 0}
				这一轮全部一次过，没有需要重练的卡。
			{:else}
				这一轮 {summary.firstTry} 张一次就过，另外 {summary.struggled} 张重练之后才记住。
			{/if}
		</p>

		<div class="mt-5 flex flex-wrap justify-center gap-2 text-xs tabular-nums">
			<div class="rounded-full bg-emerald-500/15 px-3.5 py-1.5 text-emerald-300">
				一次过 <b class="ml-0.5 font-semibold">{summary.firstTry}</b>
			</div>
			<div class="rounded-full bg-amber-500/15 px-3.5 py-1.5 text-amber-300">
				重练过 <b class="ml-0.5 font-semibold">{summary.struggled}</b>
			</div>
			<div class="rounded-full bg-white/[0.05] px-3.5 py-1.5 text-gray-300">
				用时 <b class="ml-0.5 font-semibold">{formatDuration(summary.elapsed)}</b>
			</div>
		</div>

		{#if struggledCards.length > 0}
			<div class="mt-7 w-full max-w-2xl text-left">
				<div class="px-1 text-xs font-medium text-amber-300">
					待重练的 {struggledCards.length} 张
				</div>

				<div class="mt-2.5 flex flex-col gap-2">
					{#each struggledCards as item (item.id)}
						{@const attempt = session?.attempts[item.id]}
						<div
							class="flex items-center gap-3 rounded-2xl border border-white/[0.06] bg-white/[0.02] px-4 py-3"
						>
							<span class="shrink-0 text-[11px] text-gray-500 tabular-nums">{item.id}</span>

							<span class="min-w-0 flex-1 truncate text-[13px] text-gray-300">
								<MathText value={cardHeadline(item)} />
							</span>

							{#if attempt?.graded === 'wrong'}
								<span class="shrink-0 text-[11px] text-red-300">
									答错：{attempt.answer.trim() || '未作答'}
								</span>
							{:else}
								<span class="shrink-0 text-[11px] text-amber-300">自评：再练</span>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<div class="mt-7 flex w-full max-w-2xl flex-wrap justify-center gap-2">
			{#if struggledCards.length > 0}
				<button
					type="button"
					class="min-h-10 rounded-full bg-white px-5 text-sm font-medium text-black transition hover:bg-gray-200"
					onclick={replayAgainOnly}
				>
					只重刷这 {struggledCards.length} 张
				</button>
			{/if}

			<button
				type="button"
				class="min-h-10 rounded-full border border-white/10 bg-white/[0.03] px-5 text-sm text-gray-200 transition hover:bg-white/[0.08] hover:text-white"
				onclick={start}
			>
				再来一组闪卡
			</button>

			<button
				type="button"
				class="min-h-10 rounded-full px-5 text-sm text-gray-400 transition hover:bg-white/[0.06] hover:text-white"
				onclick={onSwitchToFull}
			>
				换整卷练大题
			</button>
		</div>

		<p class="mt-5 mb-2 text-[11px] text-gray-500">全程未调用判卷模型 · 本地判定</p>
	</div>
{/if}

<style>
	/* 骨架条的流光：只表达「在写」，不假装知道写到哪了 */
	.exam-shim {
		background: linear-gradient(
			90deg,
			rgb(255 255 255 / 0.05) 0%,
			rgb(255 255 255 / 0.11) 50%,
			rgb(255 255 255 / 0.05) 100%
		);
		background-size: 800px 100%;
		animation: exam-shimmer 1.8s linear infinite;
	}

	.exam-bob {
		animation: exam-bob 2.6s ease-in-out infinite;
	}

	@keyframes exam-shimmer {
		0% {
			background-position: -400px 0;
		}
		100% {
			background-position: 400px 0;
		}
	}

	@keyframes exam-bob {
		0%,
		100% {
			transform: translateY(0);
		}
		50% {
			transform: translateY(-4px);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.exam-shim,
		.exam-bob {
			animation: none;
		}
	}
</style>
