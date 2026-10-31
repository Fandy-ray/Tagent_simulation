<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { loadKatex } from '$lib/data/math';

	import { AgentRequestError, annotateExamAnswer, generateExam, reviewExam } from '$lib/apis/agent';
	import MathText from '$lib/components/MathText.svelte';
	import AnnotatedText from '$lib/components/essay/AnnotatedText.svelte';
	import { cueRepeatsText } from '$lib/data/cue';
	import {
		ANNOTATE_MIN_ANSWER_CHARS,
		annotationLabel,
		circled,
		countCharacters,
		humanizeRefs,
		placeAnnotations,
		pyStrip
	} from '$lib/data/essay';
	import {
		LETTERS,
		SECTION_LABELS,
		answerNavClass,
		hasAnswer,
		resultNavClass,
		verdictClass,
		verdictLabel,
		clearFullExam,
		completedAnswerNotes,
		saveFullExam,
		type ExamAnswers,
		type ExamReview,
		type AnswerNoteState,
		type PublicExam,
		type PublicQuestion,
		type ReviewResult,
		type SavedFullExam
	} from '$lib/data/exam';

	/** ready：卷子出好了、还没开始作答的总览页 */
	type Phase = 'generating' | 'ready' | 'answering' | 'submitting' | 'result' | 'failed';

	/**
	 * 客户端兜底上限，只防"再也不回话"。= 后端 EXAM_LLM_BUDGET（330 秒）+ 排队最多 30 秒 + 余量；
	 * basic-agent 的 tests/test_timeout_budgets.py 盯着这条关系。
	 */
	const CLIENT_TIMEOUT_MS = 380_000;
	/**
	 * 等过这么久还没出卷，就换成「比平时久一些」那一屏、把「改用闪卡」提成主按钮。
	 * 平时十秒到几十秒（看接的模型，见下面 elapsed 的注释），90 秒已经明显不正常了。
	 * 只拿来切换文案，秒数本身不上屏：出卷的用时是我们内部的事，用户不需要看着一个计时器等。
	 */
	const SLOW_AFTER_S = 90;

	// 卷面上三种题型的说明，出卷中和出好后共用一份：题量范围取自 app/schema/exam.py 的
	// *_COUNT_RANGE；判分方式对应 basic-agent 的 ExamService.review_exam（选择、精确匹配的填空
	// 本机判，其余的填空和解答题交模型）
	const SECTION_META = [
		{
			type: 'cloze',
			label: '填空题',
			range: [8, 10],
			judge: '先比对答案，拿不准的再交模型复核',
			chip: 'bg-sky-500/15 text-sky-300',
			bar: 'bg-sky-400'
		},
		{
			type: 'choice',
			label: '选择题',
			range: [6, 8],
			judge: '本机直接判，不调模型',
			chip: 'bg-violet-500/15 text-violet-300',
			bar: 'bg-violet-400'
		},
		{
			type: 'essay',
			label: '解答题',
			range: [2, 3],
			judge: '交卷后模型按评分要点逐条批改',
			chip: 'bg-fuchsia-500/15 text-fuchsia-300',
			bar: 'bg-fuchsia-400'
		}
	] as const;

	const TYPE_CHIP: Record<PublicQuestion['type'], string> = {
		cloze: SECTION_META[0].chip,
		choice: SECTION_META[1].chip,
		essay: SECTION_META[2].chip
	};

	type Props = {
		modelId: string;
		topic: string;
		notebookIds: string[];
		wide: boolean;
		onTitle: (title: string) => void;
		onError: (message: string) => void;
		onExit: () => void;
		onSwitchToFlash: () => void;
		/** 报给外壳：现在结束这一轮会丢掉什么。空字符串＝没有进度，可以直接走。 */
		onLeavingCost?: (cost: string) => void;
		/** 刷新前存下的这张卷：有就接着做，不重新出卷（见 $lib/data/exam 的 saveFullExam） */
		resume?: SavedFullExam | null;
	};

	let {
		modelId,
		topic,
		notebookIds,
		wide,
		onTitle,
		onError,
		onExit,
		onSwitchToFlash,
		onLeavingCost,
		resume = null
	}: Props = $props();

	let phase = $state<Phase>('generating');
	let exam = $state<PublicExam | null>(null);
	let review = $state<ExamReview | null>(null);
	let answers = $state<ExamAnswers>({});

	let pageIndex = $state(0);
	let resultIndex = $state(0);
	/** 出卷时刻：存档过期按它算，和后端缓存的 2 小时对齐 */
	let startedAt = 0;

	// 出卷要等多久取决于接的是哪个模型（实测 DeepSeek 十秒上下，后端注释里那组
	// 几十秒的旧数据出自另一个模型）。用时只在内部数，用来决定什么时候换成「比平时久一些」，
	// 不上屏——用户看着一个计时器等反而更焦虑，也不该看到我们内部怎么提速。
	let elapsed = $state(0);
	let ticker: ReturnType<typeof setInterval> | null = null;
	/** 「比平时久一些」那一屏点过「继续等」：收起提醒，回到普通的出卷中 */
	let slowDismissed = $state(false);
	let slow = $derived(phase === 'generating' && elapsed >= SLOW_AFTER_S && !slowDismissed);

	// 出卷这段等待里，用户完全可能返回首屏或改用闪卡。面板卸载了、
	// 请求还在飞，回来时 onTitle/onError 会改到已经不属于它的外层状态
	// （实测过：切到闪卡之后，标题被迟到的整卷标题覆盖）。所以每次请求都带一个
	// controller，离场即 abort，回调里再判一次 aborted。
	let controller: AbortController | null = null;
	let failure = $state('');
	/** 交卷时发现这张卷在服务端已经没有了：失败页的标题换个说法 */
	let paperGone = $state(false);

	// 大题的逐句批注是**按需**的：判卷已经等过一轮模型，再给每道大题各发一轮等待就翻倍了；
	// 学生点开哪道才批哪道（见 basic-agent 的 /quiz/exam/annotate）。结果按题号留着，来回翻页不重复花调用。
	let answerNotes = $state<Record<string, AnswerNoteState>>({});
	let activeNote = $state<number | null>(null);
	// 只是在飞的请求句柄，不参与渲染，所以用普通对象而不是响应式容器
	const noteControllers: Record<string, AbortController> = {};

	let allQuestions = $derived<PublicQuestion[]>(
		exam ? [...exam.cloze, ...exam.choice, ...exam.essay] : []
	);

	let questionById = $derived(
		new Map<string, PublicQuestion>(allQuestions.map((question) => [question.id, question]))
	);

	let currentQuestion = $derived<PublicQuestion | null>(allQuestions[pageIndex] ?? null);

	let currentResult = $derived<ReviewResult | null>(
		resultIndex > 0 ? (review?.results[resultIndex - 1] ?? null) : null
	);

	let currentResultQuestion = $derived<PublicQuestion | null>(
		currentResult ? (questionById.get(currentResult.id) ?? null) : null
	);

	let totalCount = $derived(allQuestions.length);

	let answeredCount = $derived(
		allQuestions.filter((question) => hasAnswer(question, answers)).length
	);

	let progressPct = $derived(totalCount > 0 ? Math.round((answeredCount / totalCount) * 100) : 0);

	// 「结束这一轮」会把本标签页的存档一起清掉：答了题再结束要先问一句。
	// 只想先走开就点「离开测评」，那个不清存档，回来接着答。
	$effect(() => {
		if (!onLeavingCost) {
			return;
		}
		onLeavingCost(
			(phase === 'answering' || phase === 'submitting') && answeredCount > 0
				? `这张卷答了 ${answeredCount} / ${totalCount} 题，结束后就清掉了`
				: ''
		);
		// 卸载时自己把话收回去，免得换到闪卡后按结束，弹出来的还是这张卷的提示
		return () => onLeavingCost('');
	});

	// 出好后的总览：每种题型几道、每题几分、小计，以及它在作答顺序里从第几题开始（点题号直接跳过去）
	let paperSections = $derived.by(() => {
		const current = exam;

		if (!current) {
			return [];
		}

		let start = 0;

		return SECTION_META.map((meta) => {
			const items: PublicQuestion[] = current[meta.type];
			const points = items.reduce((sum, item) => sum + item.points, 0);
			// 分值归一到 100 后同一题型里常有 2 分、3 分混着：写成区间，别和右边的小计重复
			const each = items.map((item) => item.points);
			const low = Math.min(...each);
			const high = Math.max(...each);
			const section = {
				...meta,
				items,
				points,
				pointsLabel:
					items.length === 0 ? '' : low === high ? `每题 ${low} 分` : `每题 ${low}~${high} 分`,
				start
			};

			start += items.length;
			return section;
		});
	});

	let currentNotes = $derived<AnswerNoteState | null>(
		currentResult ? (answerNotes[currentResult.id] ?? null) : null
	);

	// 批注下标相对后端 strip() 之后的作答计算，所以发出去、画高亮都用同一份 pyStrip 过的文本
	let currentSource = $derived(
		currentResult?.type === 'essay' ? pyStrip(String(answers[currentResult.id] ?? '')) : ''
	);

	// 不足 40 字后端直接回空数组，干脆不给按钮
	let canAnnotate = $derived(countCharacters(currentSource) >= ANNOTATE_MIN_ANSWER_CHARS);

	let currentPlacement = $derived(
		currentNotes?.status === 'done'
			? placeAnnotations(currentNotes.source, currentNotes.items)
			: null
	);

	const resetNotes = () => {
		for (const [questionId, pending] of Object.entries(noteControllers)) {
			pending.abort();
			delete noteControllers[questionId];
		}

		answerNotes = {};
		activeNote = null;
	};

	const requestCurrentNotes = () => {
		if (!exam || !currentResult || !canAnnotate) {
			return;
		}

		const questionId = currentResult.id;
		const source = currentSource;

		noteControllers[questionId]?.abort();
		const own = new AbortController();
		noteControllers[questionId] = own;
		answerNotes = { ...answerNotes, [questionId]: { status: 'loading', source } };

		const { id, my_answer, score, points, feedback } = currentResult;
		void annotateExamAnswer(modelId, exam.exam_id, questionId, source, own.signal, {
			id,
			my_answer,
			score,
			points,
			feedback
		})
			.then((data) => {
				if (own.signal.aborted) {
					return;
				}

				answerNotes = {
					...answerNotes,
					[questionId]: { status: 'done', source, items: data.annotations }
				};
			})
			.catch((error: unknown) => {
				if (own.signal.aborted) {
					return;
				}

				answerNotes = {
					...answerNotes,
					[questionId]: {
						status: 'failed',
						source,
						error: error instanceof Error ? error.message : '批注失败，请重试。'
					}
				};
			})
			.finally(() => {
				if (noteControllers[questionId] === own) {
					delete noteControllers[questionId];
				}
			});
	};

	const stopTicker = () => {
		if (ticker !== null) {
			clearInterval(ticker);
			ticker = null;
		}
	};

	const startGenerate = () => {
		if (!modelId) {
			onError('请先选择可用模型。');
			onExit();
			return;
		}

		controller?.abort();
		const own = new AbortController();
		controller = own;
		const signal = own.signal;

		let timedOut = false;
		const ceiling = setTimeout(() => {
			timedOut = true;
			own.abort();
		}, CLIENT_TIMEOUT_MS);

		failure = '';
		paperGone = false;
		clearFullExam();
		exam = null;
		review = null;
		answers = {};
		pageIndex = 0;
		resultIndex = 0;
		resetNotes();
		phase = 'generating';

		elapsed = 0;
		slowDismissed = false;
		stopTicker();
		ticker = setInterval(() => {
			elapsed += 1;
		}, 1000);

		// 等模型出题的这几秒顺手把 KaTeX 下好（$lib/data/math 的 loadKatex），题目出来时公式不先闪一下原文
		void loadKatex();
		void generateExam(modelId, topic, notebookIds, signal)
			.then((data) => {
				clearTimeout(ceiling);

				if (signal.aborted) {
					return;
				}

				stopTicker();
				startedAt = Date.now();
				exam = data;
				onTitle(data.title);
				answers = {};
				pageIndex = 0;
				resultIndex = 0;
				// 先停在总览页：看一眼题型和分值再开始，也能点题号从任意一题做起
				phase = 'ready';
				notifyReadyInTitle();
			})
			.catch((error: unknown) => {
				clearTimeout(ceiling);

				if (timedOut) {
					stopTicker();
					failure = `等了 ${Math.round(CLIENT_TIMEOUT_MS / 60_000)} 分钟还没出卷，basic-agent 可能没在正常回话。`;
					phase = 'failed';
					return;
				}

				if (signal.aborted) {
					return;
				}

				stopTicker();
				// 就地停下，别弹回模式选择首屏：最常见的失败是 429（并发闸门满），
				// 弹回去只会让人觉得"点一下自己退回来了"，还得重走一遍选择流程。
				failure = error instanceof Error ? error.message : '出卷失败，请重试。';
				phase = 'failed';
			});
	};

	/**
	 * 出卷中屏上说了「切走也行，出好了标题会提醒你」：卷子到了、人却不在这个标签页时，
	 * 在标签页标题前加一句，回来看到就还原。
	 */
	let titleBeforeReady: string | null = null;

	const restoreTitle = () => {
		if (titleBeforeReady !== null) {
			document.title = titleBeforeReady;
			titleBeforeReady = null;
		}
		document.removeEventListener('visibilitychange', onVisible);
	};

	const onVisible = () => {
		if (!document.hidden) {
			restoreTitle();
		}
	};

	const notifyReadyInTitle = () => {
		if (typeof document === 'undefined' || !document.hidden || titleBeforeReady !== null) {
			return;
		}
		titleBeforeReady = document.title;
		document.title = `卷子出好了 · ${document.title}`;
		document.addEventListener('visibilitychange', onVisible);
	};

	/**
	 * 出卷中点「取消出卷」：掐掉这一轮回模式选择。只掐得断浏览器这边——服务端那次还会跑完、
	 * 占着并发名额，所以马上再出一张可能要排一会儿（等久了那一屏会换成「比平时久一些」）。
	 */
	const cancel = () => {
		controller?.abort();
		controller = null;
		stopTicker();
		onExit();
	};

	/** 总览页点「开始作答」或某个题号：从那一题开始 */
	const startAnswering = (index = 0) => {
		goToQuestion(index);
		phase = 'answering';
	};

	/** 还没答完就点交卷时，先确认一次；确认过就直接交。 */
	let pendingSubmit = $state(false);
	let unanswered = $derived(totalCount - answeredCount);

	const submit = (confirmed = false) => {
		if (!exam || phase === 'submitting') {
			return;
		}

		// 只答了 3/21 就误触交卷，在真实考试里是前功尽弃。拦一次，不拦第二次。
		if (!confirmed && unanswered > 0) {
			pendingSubmit = true;
			return;
		}
		pendingSubmit = false;

		phase = 'submitting';

		controller?.abort();
		controller = new AbortController();
		const signal = controller.signal;

		void reviewExam(modelId, exam.exam_id, answers, signal)
			.then((data) => {
				if (signal.aborted) {
					return;
				}

				review = data;
				resultIndex = 0;
				phase = 'result';
				// 上一次交卷失败留下的红条，这次判成功了就收掉
				onError('');
			})
			.catch((error: unknown) => {
				if (signal.aborted) {
					return;
				}

				// 410：这张卷在服务端已经没有了（超过 2 小时，或出卷模型被删了）。再点交卷也一样，
				// 刷新又会把它从本标签页的存档里摆回来——所以清掉存档，直接给「重新出卷」
				if (error instanceof AgentRequestError && error.status === 410) {
					clearFullExam();
					paperGone = true;
					failure = error.message;
					exam = null;
					review = null;
					phase = 'failed';
					return;
				}

				onError(error instanceof Error ? error.message : '判卷失败，请重试。');
				phase = 'answering';
			});
	};

	const goToQuestion = (index: number) => {
		pageIndex = Math.max(0, Math.min(index, Math.max(0, allQuestions.length - 1)));
	};

	const goToResult = (index: number) => {
		resultIndex = Math.max(0, Math.min(index, review?.results.length ?? 0));
		activeNote = null;
	};

	const onKeydown = (event: KeyboardEvent) => {
		if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
			return;
		}

		if (event.isComposing || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) {
			return;
		}

		const target = event.target;

		if (
			target instanceof Element &&
			target.closest('input, textarea, select, button, [contenteditable="true"]')
		) {
			return;
		}

		const offset = event.key === 'ArrowRight' ? 1 : -1;

		if ((phase === 'answering' || phase === 'submitting') && allQuestions.length > 0) {
			event.preventDefault();
			goToQuestion(pageIndex + offset);
			return;
		}

		if (phase === 'result' && review) {
			event.preventDefault();
			goToResult(resultIndex + offset);
		}
	};

	/** 刷新后接着做：卷面、答案、做到第几题、判卷结果都从本标签页的存档里恢复，不花模型调用 */
	const restoreFrom = (saved: SavedFullExam) => {
		startedAt = saved.startedAt;
		exam = saved.exam;
		answers = saved.answers ?? {};
		pageIndex = saved.pageIndex ?? 0;
		review = saved.review;
		resultIndex = saved.resultIndex ?? 0;
		answerNotes = saved.answerNotes ?? {};
		onTitle(saved.exam.title);
		// 一题没答、还停在第一题：多半是在总览页刷新的，回到总览页
		const untouched =
			saved.pageIndex === 0 &&
			[...saved.exam.cloze, ...saved.exam.choice, ...saved.exam.essay].every(
				(question) => !hasAnswer(question, saved.answers ?? {})
			);
		phase = saved.review ? 'result' : untouched ? 'ready' : 'answering';
	};

	// 总览、答题、翻页、交卷后都存一份，刷新能接着做
	$effect(() => {
		if (
			!exam ||
			!(phase === 'ready' || phase === 'answering' || phase === 'submitting' || phase === 'result')
		) {
			return;
		}
		saveFullExam({
			startedAt,
			modelId,
			topic,
			notebookIds,
			exam,
			answers: $state.snapshot(answers),
			pageIndex,
			review,
			resultIndex,
			answerNotes: completedAnswerNotes($state.snapshot(answerNotes))
		});
	});

	onMount(() => {
		window.addEventListener('keydown', onKeydown);
		if (resume) {
			restoreFrom(resume);
		} else {
			startGenerate();
		}
	});

	onDestroy(() => {
		stopTicker();
		controller?.abort();
		resetNotes();

		// onDestroy 在 SSR 渲染完也会跑一次，那边没有 window。
		if (typeof window === 'undefined') {
			return;
		}

		window.removeEventListener('keydown', onKeydown);
		restoreTitle();
	});
</script>

<div class="flex h-full min-h-0 flex-col">
	{#if phase === 'generating' || phase === 'ready'}
		<div class="flex min-h-0 flex-1 flex-col overflow-y-auto">
			<div
				class="mx-auto my-auto grid w-full max-w-[1080px] gap-5 px-4 py-6 sm:px-6 sm:py-8 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start"
			>
				<!-- 卷面：出卷中和出好后是同一张。知道的照实写（题型、题量范围、怎么判），
				     还不知道的留白（标题、确切题数、分值），出好了原地填进来 -->
				<section
					class="rounded-3xl border border-white/[0.08] bg-white/[0.035] px-5 py-6 sm:px-9 sm:py-8"
					aria-label="卷面"
				>
					<div
						class="flex flex-col items-center gap-2.5 border-b border-white/[0.06] pb-5 text-center"
					>
						{#if phase === 'ready' && exam}
							<h2 class="text-xl leading-snug font-semibold text-white">{exam.title}</h2>
							<div class="text-[13px] text-gray-500 tabular-nums">
								{totalCount} 题 · 满分 {exam.total_points}
							</div>
						{:else}
							<div class="exam-shim h-[22px] w-72 max-w-[80%] rounded-lg" aria-hidden="true"></div>
							<div class="text-[13px] text-gray-500">16~21 题 · 满分 100</div>
						{/if}
					</div>

					<div class="mt-6 flex flex-col gap-6">
						{#each SECTION_META as meta, index (meta.type)}
							{@const section = phase === 'ready' ? paperSections[index] : null}
							<div class="flex flex-col gap-3">
								<div class="flex items-center gap-2.5">
									<span class={`rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.chip}`}>
										{meta.label}
									</span>
									<span class="text-xs text-gray-500 tabular-nums">
										{section
											? `${section.items.length} 道 · ${section.pointsLabel}`
											: `${meta.range[0]}~${meta.range[1]} 道`}
									</span>

									{#if section}
										<span class="ml-auto text-sm font-semibold text-white tabular-nums">
											{section.points} 分
										</span>
									{:else}
										<span class="ml-auto inline-flex items-center gap-1.5 text-xs text-gray-400">
											<span
												class={`size-1.5 animate-pulse rounded-full ${slow ? 'bg-amber-300' : 'bg-sky-300'}`}
												style={`animation-delay: ${index * 300}ms`}
											></span>
											{slow ? '还在出' : '出题中'}
										</span>
									{/if}
								</div>

								<div class="flex flex-wrap gap-2">
									{#if section}
										{#each section.items as question, offset (question.id)}
											<button
												type="button"
												class="h-8 min-w-10 rounded-[10px] border border-white/[0.08] bg-white/[0.04] px-2 text-xs text-gray-300 tabular-nums transition hover:bg-white/[0.09] hover:text-white"
												onclick={() => startAnswering(section.start + offset)}
												aria-label={`从 ${question.id} 开始作答`}
												title={`从 ${question.id} 开始作答`}
											>
												{question.id}
											</button>
										{/each}
									{:else}
										<!-- 实线虚框是最少会出的题数，淡的是可能多出来的那几道 -->
										{#each Array.from({ length: meta.range[1] }, (_, slot) => slot) as slot (slot)}
											<span
												class={`h-8 w-10 rounded-[10px] border border-dashed ${
													slot < meta.range[0]
														? 'animate-pulse border-white/[0.16]'
														: 'border-white/[0.06]'
												}`}
												style={`animation-delay: ${index * 300}ms`}
												aria-hidden="true"
											></span>
										{/each}
									{/if}
								</div>

								<div class="text-xs text-gray-500">{meta.judge}</div>
							</div>
						{/each}
					</div>
				</section>

				<!-- 窄屏时这一栏排到卷面上面：状态和「开始作答」不用往下翻才看得到 -->
				<aside class="order-first flex flex-col gap-3 lg:order-none">
					{#if phase === 'ready' && exam}
						<div
							class="flex flex-col gap-2 rounded-3xl border border-white/[0.08] bg-white/[0.035] p-6"
							aria-live="polite"
						>
							<div
								class="mb-2 flex size-10 items-center justify-center rounded-xl bg-emerald-500/15"
							>
								<svg
									class="size-5 text-emerald-300"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									stroke-linecap="round"
									stroke-linejoin="round"
									aria-hidden="true"
								>
									<path d="M20 6 9 17l-5-5"></path>
								</svg>
							</div>
							<div class="text-[17px] font-semibold text-white">卷子出好了</div>
							<p class="text-[13px] leading-relaxed text-gray-500">
								{totalCount} 道题，满分 {exam.total_points}。准备好就开始吧，也可以点题号直接从那一题做起。
							</p>

							<div class="mt-3.5 flex h-1.5 gap-[3px]" aria-hidden="true">
								{#each paperSections as section, index (section.type)}
									{#if section.points > 0}
										<div
											class={`${section.bar} ${index === 0 ? 'rounded-l-full' : 'rounded-l-sm'} ${
												index === paperSections.length - 1 ? 'rounded-r-full' : 'rounded-r-sm'
											}`}
											style={`flex: ${section.points} 1 0%`}
										></div>
									{/if}
								{/each}
							</div>
							<div class="flex gap-[3px] text-[11px] text-gray-500 tabular-nums">
								{#each paperSections as section (section.type)}
									{#if section.points > 0}
										<span class="min-w-0 truncate" style={`flex: ${section.points} 1 0%`}>
											{section.label.slice(0, 2)}
											<span class="text-gray-200">{section.points}</span>
										</span>
									{/if}
								{/each}
							</div>

							<ul
								class="mt-3.5 flex flex-col gap-2.5 border-t border-white/[0.06] pt-3.5 text-[13px] text-gray-400"
							>
								<li class="flex items-center gap-2">
									<svg
										class="size-3.5 shrink-0 text-gray-500"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.6"
										stroke-linecap="round"
										stroke-linejoin="round"
										aria-hidden="true"
									>
										<path d="M7 7h10"></path>
										<path d="M7 12h10"></path>
										<path d="M7 17h6"></path>
									</svg>
									可以跳着做，题号条随时跳
								</li>
								<li class="flex items-center gap-2">
									<svg
										class="size-3.5 shrink-0 text-gray-500"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.6"
										stroke-linecap="round"
										stroke-linejoin="round"
										aria-hidden="true"
									>
										<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"
										></path>
										<path d="M17 21v-8H7v8"></path>
										<path d="M7 3v5h8"></path>
									</svg>
									答案自动保存，刷新不丢
								</li>
								<li class="flex items-center gap-2">
									<svg
										class="size-3.5 shrink-0 text-gray-500"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.6"
										stroke-linecap="round"
										stroke-linejoin="round"
										aria-hidden="true"
									>
										<path d="M12 20h9"></path>
										<path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"></path>
									</svg>
									交卷后大题批改完才出总分
								</li>
							</ul>
						</div>

						<button
							type="button"
							class="min-h-11 rounded-full bg-white text-sm font-medium text-black transition hover:bg-gray-200"
							onclick={() => startAnswering(0)}
						>
							开始作答
						</button>
						<button
							type="button"
							class="min-h-10 rounded-full border border-white/10 bg-white/[0.03] text-[13px] text-gray-300 transition hover:bg-white/[0.08] hover:text-white"
							onclick={startGenerate}
						>
							换一张卷子
						</button>
					{:else if slow}
						<div
							class="flex flex-col gap-2 rounded-3xl border border-amber-500/20 bg-amber-500/[0.05] p-6"
							aria-live="polite"
						>
							<div class="mb-2 flex size-10 items-center justify-center rounded-xl bg-amber-500/15">
								<svg
									class="size-5 text-amber-300"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.6"
									stroke-linecap="round"
									stroke-linejoin="round"
									aria-hidden="true"
								>
									<circle cx="12" cy="12" r="9"></circle>
									<path d="M12 7v5l3 2"></path>
								</svg>
							</div>
							<div class="text-[17px] font-semibold text-white">比平时久一些</div>
							<p class="text-[13px] leading-relaxed text-gray-400">
								还在出，再稍等一下。真出不来的话会直接告诉你原因，不会一直卡在这里。
							</p>
							<div
								class="exam-lane exam-lane-amber mt-3 h-[3px] rounded-full bg-white/[0.06]"
							></div>
						</div>

						<div
							class="flex flex-col gap-1.5 rounded-3xl border border-white/10 bg-white/[0.05] px-6 py-5"
						>
							<div class="text-sm font-medium text-white">不想再等了？</div>
							<p class="text-[13px] leading-relaxed text-gray-500">
								换成闪卡，几乎不用等。这张卷子会停掉，不再出了。
							</p>
							<button
								type="button"
								class="mt-3 inline-flex min-h-10 items-center justify-center gap-1.5 rounded-full bg-white px-5 text-sm font-medium text-black transition hover:bg-gray-200"
								onclick={onSwitchToFlash}
							>
								改用闪卡，马上开刷
								<svg
									class="size-3.5"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									stroke-linecap="round"
									stroke-linejoin="round"
									aria-hidden="true"
								>
									<path d="M5 12h14"></path>
									<path d="m13 6 6 6-6 6"></path>
								</svg>
							</button>
						</div>

						<div class="flex flex-wrap gap-1">
							<button
								type="button"
								class="min-h-9 rounded-full border border-white/10 bg-white/[0.03] px-4 text-[13px] text-gray-300 transition hover:bg-white/[0.08] hover:text-white"
								onclick={() => (slowDismissed = true)}
							>
								继续等
							</button>
							<button
								type="button"
								class="hover:bg-gray-850 min-h-9 rounded-full px-4 text-[13px] text-gray-500 transition hover:text-white"
								onclick={cancel}
							>
								取消出卷
							</button>
						</div>
					{:else}
						<div
							class="flex flex-col gap-2 rounded-3xl border border-white/[0.08] bg-white/[0.035] p-6"
							aria-live="polite"
						>
							<div class="mb-2 flex size-10 items-center justify-center rounded-xl bg-white/[0.06]">
								<svg
									class="size-5 text-gray-100"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.5"
									stroke-linecap="round"
									stroke-linejoin="round"
									aria-hidden="true"
								>
									<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
									<path d="M14 2v6h6"></path>
									<path d="m9 15 2 2 4-4"></path>
								</svg>
							</div>
							<div class="text-[17px] font-semibold text-white">正在出卷</div>
							<p class="text-[13px] leading-relaxed text-gray-500">
								填空、选择、解答三种题型出齐了，会一起交给你。
							</p>
							<div class="exam-lane mt-3 h-[3px] rounded-full bg-white/[0.06]"></div>
							<div class="mt-3 flex items-start gap-2 text-xs leading-relaxed text-gray-500">
								<svg
									class="mt-0.5 size-3.5 shrink-0"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.6"
									stroke-linecap="round"
									stroke-linejoin="round"
									aria-hidden="true"
								>
									<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"></path>
									<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"></path>
								</svg>
								可以先切到别的标签页，出好了这页的标题会提醒你。
							</div>
						</div>

						<div
							class="flex flex-col gap-1.5 rounded-3xl border border-white/[0.08] bg-white/[0.035] px-6 py-5"
						>
							<div class="text-sm font-medium text-white">想先刷几道？</div>
							<p class="text-[13px] leading-relaxed text-gray-500">
								闪卡只有填空和选择，几乎不用等，答完当场知道对错。
							</p>
							<button
								type="button"
								class="mt-2.5 inline-flex min-h-9 items-center gap-1.5 self-start rounded-full border border-white/10 bg-white/[0.03] px-4 text-[13px] text-gray-200 transition hover:bg-white/[0.08] hover:text-white"
								onclick={onSwitchToFlash}
							>
								改用闪卡
								<svg
									class="size-3.5"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.8"
									stroke-linecap="round"
									stroke-linejoin="round"
									aria-hidden="true"
								>
									<path d="M5 12h14"></path>
									<path d="m13 6 6 6-6 6"></path>
								</svg>
							</button>
						</div>

						<button
							type="button"
							class="hover:bg-gray-850 min-h-9 self-start rounded-full px-4 text-[13px] text-gray-500 transition hover:text-white"
							onclick={cancel}
						>
							取消出卷
						</button>
					{/if}
				</aside>
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

			<div class="text-[17px] font-medium text-white">
				{paperGone ? '这张卷子已经交不了了' : '这一轮没能出卷'}
			</div>

			<p class="max-w-sm text-sm leading-relaxed text-gray-400">{failure}</p>

			{#if failure.includes('过多')}
				<p class="max-w-sm text-xs leading-relaxed text-gray-500">
					同时在出卷、判卷的人有点多，过一会儿再点重试就好。
				</p>
			{/if}

			<div class="mt-3 flex flex-wrap justify-center gap-2">
				<button
					type="button"
					class="min-h-10 rounded-full bg-white px-5 text-sm font-medium text-black transition hover:bg-gray-200"
					onclick={startGenerate}
				>
					{paperGone ? '重新出卷' : '重试'}
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
	{:else}
		<div
			class="mx-auto flex h-full min-h-0 w-full max-w-[1080px] flex-col px-4 py-4 sm:px-6 sm:py-5"
		>
			{#if phase === 'answering' || phase === 'submitting'}
				<div class="shrink-0 pb-3">
					<div class="h-1 overflow-hidden rounded-full bg-white/[0.06]">
						<div
							class="h-full rounded-full bg-sky-400 transition-all duration-300"
							style={`width: ${progressPct}%`}
						></div>
					</div>

					<div class="mt-1.5 flex justify-between text-[11px] text-gray-500 tabular-nums">
						<span>已作答 {answeredCount} / {totalCount}</span>
						<span>{progressPct}%</span>
					</div>
				</div>
			{/if}

			<div class="flex min-h-0 flex-1 flex-col">
				{#if (phase === 'answering' || phase === 'submitting') && exam && currentQuestion}
					<div class="flex min-h-0 flex-1 items-stretch gap-2">
						<button
							type="button"
							class="hover:bg-gray-850 flex size-11 shrink-0 items-center justify-center self-center rounded-xl text-gray-400 transition hover:text-white disabled:pointer-events-none disabled:text-gray-600"
							disabled={pageIndex === 0}
							onclick={() => goToQuestion(pageIndex - 1)}
							aria-label="上一题"
							title="上一题"
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
								<path d="m15 18-6-6 6-6"></path>
							</svg>
						</button>

						<div class="flex min-h-0 min-w-0 flex-1 items-center justify-center">
							{#key currentQuestion.id}
								<div
									class="relative h-full max-h-[640px] min-h-0 w-full overflow-hidden rounded-3xl border border-white/[0.08] bg-[#1d1d1d] shadow-[0_24px_48px_-24px_rgba(0,0,0,0.6)]"
								>
									<div
										class={`h-full min-h-0 ${
											wide ? 'grid grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]' : 'flex flex-col'
										}`}
									>
										<section
											class={`min-h-0 min-w-0 overflow-y-auto p-4 ${
												wide
													? 'border-r border-white/[0.06]'
													: 'max-h-[46%] shrink-0 border-b border-white/[0.06]'
											}`}
										>
											<div class="mb-4 flex items-center gap-2">
												<span
													class={`rounded-full px-2.5 py-0.5 text-xs font-medium ${TYPE_CHIP[currentQuestion.type]}`}
												>
													{SECTION_LABELS[currentQuestion.type]}
												</span>

												<span class="text-xs text-gray-500 tabular-nums">
													{currentQuestion.id} · {currentQuestion.points} 分 ·
													{pageIndex + 1}/{totalCount}
												</span>
											</div>

											{#if currentQuestion.type === 'cloze'}
												{#if !cueRepeatsText(currentQuestion.cue, currentQuestion.text)}
													<div class="mb-3 text-sm text-gray-400">
														<!-- 填空题的提示句里也常有公式（$\lambda$ 之类），同样要渲染，不能原样露出 TeX -->
														<MathText value={currentQuestion.cue} />
													</div>
												{/if}

												<div class="text-lg leading-relaxed font-medium text-white">
													{#each currentQuestion.text.split('____') as part, index (index)}
														<MathText value={part} />

														{#if index < currentQuestion.text.split('____').length - 1}
															<span
																class="mx-1.5 inline-block min-w-20 border-b-2 border-sky-300 px-2 text-center text-sky-300"
															>
																{(answers[currentQuestion.id] as string) || ' '}
															</span>
														{/if}
													{/each}
												</div>
											{:else}
												<div class="text-lg leading-relaxed font-medium text-white">
													<MathText value={currentQuestion.question} />
												</div>
											{/if}
										</section>

										<section
											class="flex min-h-0 min-w-0 flex-1 flex-col justify-center overflow-y-auto p-4"
										>
											{#if currentQuestion.type === 'cloze'}
												<label
													class="mb-2 text-xs text-gray-500"
													for={`answer-${currentQuestion.id}`}
												>
													你的答案
												</label>

												<input
													id={`answer-${currentQuestion.id}`}
													class="w-full rounded-2xl border border-white/[0.08] bg-white/[0.035] px-4 py-3 text-base text-gray-100 transition outline-none placeholder:text-gray-500 focus:border-white/20 disabled:opacity-60"
													placeholder="输入你的答案"
													value={(answers[currentQuestion.id] as string) ?? ''}
													disabled={phase === 'submitting'}
													oninput={(event) => {
														answers = {
															...answers,
															[currentQuestion.id]: event.currentTarget.value
														};
													}}
												/>
											{:else if currentQuestion.type === 'choice'}
												<div class="flex flex-col gap-2">
													{#each currentQuestion.options as option, index (index)}
														<button
															type="button"
															class={`rounded-2xl border px-4 py-3 text-left text-sm transition disabled:opacity-60 ${
																answers[currentQuestion.id] === index
																	? 'border-sky-400/50 bg-sky-500/10 text-sky-100'
																	: 'border-white/[0.08] text-gray-200 hover:bg-white/[0.04]'
															}`}
															disabled={phase === 'submitting'}
															onclick={() => {
																answers = {
																	...answers,
																	[currentQuestion.id]:
																		answers[currentQuestion.id] === index ? null : index
																};
															}}
														>
															<span class="mr-2 font-medium text-gray-400">
																{LETTERS[index]}
															</span>

															<MathText value={option} />
														</button>
													{/each}
												</div>
											{:else}
												<label
													class="mb-2 text-xs text-gray-500"
													for={`answer-${currentQuestion.id}`}
												>
													你的回答
												</label>

												<textarea
													id={`answer-${currentQuestion.id}`}
													class="min-h-40 w-full flex-1 resize-none rounded-2xl border border-white/[0.08] bg-white/[0.035] px-4 py-3 text-sm leading-relaxed text-gray-100 transition outline-none placeholder:text-gray-500 focus:border-white/20 disabled:opacity-60"
													placeholder="输入你的回答（判分时会结合课程知识库评审）"
													maxlength="5000"
													value={(answers[currentQuestion.id] as string) ?? ''}
													disabled={phase === 'submitting'}
													oninput={(event) => {
														answers = {
															...answers,
															[currentQuestion.id]: event.currentTarget.value
														};
													}}></textarea>
											{/if}
										</section>
									</div>
								</div>
							{/key}
						</div>

						<button
							type="button"
							class="hover:bg-gray-850 flex size-11 shrink-0 items-center justify-center self-center rounded-xl text-gray-400 transition hover:text-white disabled:pointer-events-none disabled:text-gray-600"
							disabled={pageIndex >= totalCount - 1}
							onclick={() => goToQuestion(pageIndex + 1)}
							aria-label="下一题"
							title="下一题"
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
								<path d="m9 18 6-6-6-6"></path>
							</svg>
						</button>
					</div>

					<div class="mt-3 flex shrink-0 items-center gap-2 border-t border-white/[0.06] pt-3">
						<!--
					题号换行而不是横向滚动：21 个按钮放不下时，滚动条会压在 h-8 的按钮上，
					而且首尾两个（C1、E3）会被滚出视野——实测点不到。折成两行就全看得见。
				-->
						<div class="min-w-0 flex-1">
							<div class="flex flex-wrap items-center gap-1.5">
								{#each allQuestions as question, index (question.id)}
									<button
										type="button"
										class={`h-8 rounded-[10px] border text-xs tabular-nums transition ${
											wide ? 'min-w-10 px-2' : 'min-w-7 px-1'
										} ${answerNavClass(question, index, pageIndex, answers)}`}
										onclick={() => goToQuestion(index)}
										aria-current={index === pageIndex ? 'page' : undefined}
										aria-label={`跳到第 ${index + 1} 题 ${question.id}`}
										title={`${question.id} · ${hasAnswer(question, answers) ? '已作答' : '未作答'}`}
									>
										{#if wide}
											{question.id}
										{:else}
											<span class="inline-block size-2 rounded-full bg-current"></span>
										{/if}
									</button>
								{/each}
							</div>
						</div>

						<!-- 答完了就把确认条收起来，别留着显示「还有 0 题没答」 -->
						{#if pendingSubmit && unanswered > 0}
							<div
								class="flex shrink-0 items-center gap-1.5 rounded-full bg-amber-500/15 py-1 pr-1 pl-3"
							>
								<span class="text-xs text-amber-200">还有 {unanswered} 题没答，确定交卷？</span>
								<button
									type="button"
									class="rounded-full bg-white px-3 py-1.5 text-xs font-medium text-black transition hover:bg-gray-200"
									onclick={() => submit(true)}
								>
									仍然交卷
								</button>
								<button
									type="button"
									class="rounded-full px-3 py-1.5 text-xs text-amber-100 transition hover:bg-white/10"
									onclick={() => (pendingSubmit = false)}
								>
									再检查一下
								</button>
							</div>
						{:else}
							<button
								type="button"
								class="min-h-10 shrink-0 rounded-full bg-white px-5 text-sm font-medium text-black transition hover:bg-gray-200 disabled:opacity-60"
								disabled={phase === 'submitting'}
								onclick={() => submit()}
							>
								{phase === 'submitting' ? '正在判分…' : '提交试卷'}
							</button>
						{/if}
					</div>
				{:else if phase === 'result' && review}
					<div class="flex min-h-0 flex-1 items-stretch gap-2">
						<button
							type="button"
							class="hover:bg-gray-850 flex size-11 shrink-0 items-center justify-center self-center rounded-xl text-gray-400 transition hover:text-white disabled:pointer-events-none disabled:text-gray-600"
							disabled={resultIndex === 0}
							onclick={() => goToResult(resultIndex - 1)}
							aria-label="上一页"
							title="上一页"
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
								<path d="m15 18-6-6 6-6"></path>
							</svg>
						</button>

						<div class="flex min-h-0 min-w-0 flex-1 items-center justify-center">
							{#if resultIndex === 0}
								<div
									class="flex h-full max-h-[640px] w-full flex-col items-center justify-center overflow-y-auto rounded-3xl border border-white/[0.08] bg-white/[0.035] px-5 text-center"
								>
									<div class="mb-3 text-xs tracking-[0.2em] text-gray-500">本卷已完成</div>

									<div class="text-6xl font-semibold text-white tabular-nums">
										{review.total_score}

										<span class="text-lg text-gray-400">
											/ {review.total_points}
										</span>
									</div>

									<p class="mt-3 max-w-2xl text-sm leading-6 text-gray-400">
										{review.overall_comment}
									</p>

									<div
										class="mt-5 flex flex-wrap justify-center gap-2 text-xs text-gray-400 tabular-nums"
									>
										{#each Object.entries(review.sections) as [sectionType, section] (sectionType)}
											<div class="rounded-full bg-white/[0.05] px-3.5 py-1.5">
												{sectionType === 'cloze'
													? '填空题'
													: sectionType === 'choice'
														? '选择题'
														: '大题'}

												<b>{section.earned}</b>/{section.max}
											</div>
										{/each}
									</div>
								</div>
							{:else if currentResult}
								<div
									class="h-full max-h-[640px] min-h-0 w-full overflow-hidden rounded-3xl border border-white/[0.08] bg-[#1d1d1d] shadow-[0_24px_48px_-24px_rgba(0,0,0,0.6)]"
								>
									<div
										class={`h-full min-h-0 ${
											wide ? 'grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)]' : 'flex flex-col'
										}`}
									>
										<section
											class={`min-h-0 min-w-0 overflow-y-auto p-4 ${
												wide
													? 'border-r border-white/[0.06]'
													: 'max-h-[48%] shrink-0 border-b border-white/[0.06]'
											}`}
										>
											<div class="mb-4 flex items-center justify-between gap-2">
												<span class="text-xs text-gray-500 tabular-nums">
													{currentResult.id} ·
													{SECTION_LABELS[currentResult.type]}
												</span>

												<span
													class={`text-xs font-semibold ${verdictClass(currentResult.verdict)}`}
												>
													{verdictLabel(currentResult.verdict)} ·
													{currentResult.score}/{currentResult.points}
												</span>
											</div>

											{#if currentResultQuestion}
												{#if currentResultQuestion.type === 'cloze'}
													{#if !cueRepeatsText(currentResultQuestion.cue, currentResultQuestion.text)}
														<div class="mb-2 text-sm text-gray-400">
															<MathText value={currentResultQuestion.cue} />
														</div>
													{/if}

													<div class="leading-relaxed font-medium">
														<MathText value={currentResultQuestion.text} />
													</div>
												{:else if currentResultQuestion.type === 'choice'}
													<div class="leading-relaxed font-medium">
														<MathText value={currentResultQuestion.question} />
													</div>

													<div class="mt-3 space-y-1 text-xs text-gray-400">
														{#each currentResultQuestion.options as option, index (index)}
															<div>
																<span class="mr-2">
																	{LETTERS[index]}
																</span>

																<MathText value={option} />
															</div>
														{/each}
													</div>
												{:else}
													<div class="leading-relaxed font-medium">
														<MathText value={currentResultQuestion.question} />
													</div>
												{/if}
											{:else}
												<div class="font-medium">
													题目 {currentResult.id}
												</div>
											{/if}

											<div class="mt-5 rounded-2xl bg-white/[0.04] p-3.5">
												<div class="mb-1 flex items-center justify-between gap-2">
													<span class="text-[11px] text-gray-500">我的答案</span>

													{#if currentResult.type === 'essay' && canAnnotate && currentNotes?.status !== 'done'}
														<button
															type="button"
															class="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-0.5 text-[11px] text-gray-300 transition hover:bg-white/[0.08] disabled:opacity-60"
															disabled={currentNotes?.status === 'loading'}
															onclick={requestCurrentNotes}
															title="挑出这道题作答里最该改的一两句，画线并说明"
														>
															{currentNotes?.status === 'loading'
																? '正在逐句批注…'
																: currentNotes?.status === 'failed'
																	? '重试逐句批注'
																	: '逐句批注'}
														</button>
													{/if}
												</div>

												{#if currentPlacement && currentPlacement.placed.length > 0}
													<div class="text-sm leading-7">
														<AnnotatedText
															paragraphs={currentPlacement.paragraphs}
															active={activeNote}
															onActivate={(n) => (activeNote = n)}
														/>
													</div>

													<ol class="mt-3 space-y-1 border-t border-white/[0.08] pt-2.5">
														{#each currentPlacement.placed as note (note.n)}
															<li
																id={`note-${note.n}`}
																class={`rounded-lg px-2 py-1 text-xs leading-relaxed text-gray-300 transition ${
																	activeNote === note.n ? 'bg-red-500/10' : ''
																}`}
															>
																<span class="mr-1 text-red-400">
																	{circled(note.n)}
																	{annotationLabel(note.kind)}
																</span>
																{humanizeRefs(note.comment)}
															</li>
														{/each}
													</ol>
												{:else}
													<div class="text-sm leading-relaxed whitespace-pre-wrap">
														{currentResult.my_answer !== null &&
														currentResult.my_answer !== undefined &&
														currentResult.my_answer !== ''
															? currentResult.my_answer
															: '未作答'}
													</div>
												{/if}

												{#if currentNotes?.status === 'failed'}
													<p class="mt-2 text-xs text-red-400">{currentNotes.error}</p>
												{:else if currentPlacement && currentPlacement.unplaced.length > 0}
													<p class="mt-2 text-xs text-gray-500">
														有 {currentPlacement.unplaced.length} 条批注对不上作答原文的位置，没有画线。
													</p>
												{:else if currentPlacement && currentPlacement.placed.length === 0}
													<p class="mt-2 text-xs text-gray-500">
														没有挑出需要单独指出的句子，看右侧评语即可。
													</p>
												{:else if currentResult.type === 'essay' && currentSource && !canAnnotate}
													<p class="mt-2 text-[11px] text-gray-500">
														作答不足 {ANNOTATE_MIN_ANSWER_CHARS} 字，不做逐句批注。
													</p>
												{/if}
											</div>
										</section>

										<section class="min-h-0 min-w-0 flex-1 space-y-3 overflow-y-auto p-4">
											<div class="rounded-2xl bg-emerald-500/10 p-3.5">
												<div class="mb-1 text-[11px] font-medium text-emerald-300">参考答案</div>

												<div class="text-sm leading-relaxed">
													<MathText value={currentResult.correct_answer} />
												</div>
											</div>

											{#if currentResult.feedback}
												<div class="rounded-2xl bg-white/[0.04] p-3.5">
													<div class="mb-1 text-[11px] text-gray-500">评语</div>

													<div class="text-sm leading-relaxed">
														<MathText value={currentResult.feedback} />
													</div>
												</div>
											{/if}

											{#if currentResult.explanation}
												<div class="rounded-2xl bg-white/[0.04] p-3.5">
													<div class="mb-1 text-[11px] font-medium text-sky-300">解析</div>

													<div class="text-sm leading-relaxed text-gray-300">
														<MathText value={currentResult.explanation} />
													</div>
												</div>
											{/if}
										</section>
									</div>
								</div>
							{/if}
						</div>

						<button
							type="button"
							class="hover:bg-gray-850 flex size-11 shrink-0 items-center justify-center self-center rounded-xl text-gray-400 transition hover:text-white disabled:pointer-events-none disabled:text-gray-600"
							disabled={resultIndex >= review.results.length}
							onclick={() => goToResult(resultIndex + 1)}
							aria-label="下一页"
							title="下一页"
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
								<path d="m9 18 6-6-6-6"></path>
							</svg>
						</button>
					</div>

					<div class="mt-3 flex shrink-0 items-center gap-2 border-t border-white/[0.06] pt-3">
						<!--
					题号换行而不是横向滚动：21 个按钮放不下时，滚动条会压在 h-8 的按钮上，
					而且首尾两个（C1、E3）会被滚出视野——实测点不到。折成两行就全看得见。
				-->
						<div class="min-w-0 flex-1">
							<div class="flex flex-wrap items-center gap-1.5">
								<button
									type="button"
									class={`h-8 rounded-[10px] border px-2.5 text-xs transition ${
										resultIndex === 0
											? 'border-white bg-white text-black'
											: 'border-white/[0.08] bg-white/[0.04] text-gray-400'
									}`}
									onclick={() => goToResult(0)}
									aria-current={resultIndex === 0 ? 'page' : undefined}
								>
									总览
								</button>

								{#each review.results as item, index (item.id)}
									<button
										type="button"
										class={`h-8 min-w-10 rounded-[10px] border px-2 text-xs tabular-nums transition ${resultNavClass(
											item
										)} ${
											resultIndex === index + 1
												? 'ring-2 ring-white ring-offset-2 ring-offset-gray-900'
												: ''
										}`}
										onclick={() => goToResult(index + 1)}
										aria-current={resultIndex === index + 1 ? 'page' : undefined}
										title={`${item.id} · ${verdictLabel(item.verdict)}`}
									>
										{item.id}
									</button>
								{/each}
							</div>
						</div>

						<button
							type="button"
							class="min-h-10 shrink-0 rounded-full bg-white px-5 text-sm font-medium text-black transition hover:bg-gray-200"
							onclick={onExit}
						>
							再来一套
						</button>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	/* 卷面标题的骨架条：只表达「在出」，不假装知道出到哪了 */
	.exam-shim {
		background: linear-gradient(
			90deg,
			rgb(255 255 255 / 0.05) 0%,
			rgb(255 255 255 / 0.11) 50%,
			rgb(255 255 255 / 0.05) 100%
		);
		background-size: 800px 100%;
		animation: exam-shimmer 2s linear infinite;
	}

	/* 三段是真并行、服务端又不分段回报，所以用不定进度条：能表达"在跑"，
	   又不假装知道跑到哪了。 */
	.exam-lane {
		position: relative;
		overflow: hidden;
	}

	.exam-lane::after {
		content: '';
		position: absolute;
		inset: 0 auto 0 0;
		width: 32%;
		border-radius: 999px;
		background: #74d4ff;
		animation: exam-lane-slide 1.8s ease-in-out infinite;
	}

	.exam-lane-amber::after {
		background: #ffd230;
		animation-duration: 2.4s;
	}

	@keyframes exam-shimmer {
		0% {
			background-position: -400px 0;
		}
		100% {
			background-position: 400px 0;
		}
	}

	@keyframes exam-lane-slide {
		0% {
			transform: translateX(-105%);
		}
		100% {
			transform: translateX(320%);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.exam-shim {
			animation: none;
		}

		.exam-lane::after {
			animation-duration: 6s;
		}
	}
</style>
