<script lang="ts">
	import { browser } from '$app/environment';
	import { onDestroy, onMount } from 'svelte';

	import { getAgentModels } from '$lib/apis/agent';
	import { clearFullExam, loadFullExam, type ExamMode, type SavedFullExam } from '$lib/data/exam';
	import { clearFlashDeck, loadFlashDeck, type SavedFlashDeck } from '$lib/data/flash';
	import ExamModePicker from '$lib/components/quiz/ExamModePicker.svelte';
	import FlashcardPanel from '$lib/components/quiz/FlashcardPanel.svelte';
	import FullExamPanel from '$lib/components/quiz/FullExamPanel.svelte';
	import {
		findCollection,
		parseSourceKey,
		sourceKeysForCollection,
		type KnowledgeCollection
	} from '$lib/data/knowledge';

	type AgentModelOption = {
		id: string;
		name: string;
	};

	type Props = {
		fullPage?: boolean;
		onClose?: (() => void) | null;
		modelId?: string;
		initialTopic?: string;
		/** URL 上的 ?mode=，只用来预选模式卡；真正在跑哪个模式由 running 决定 */
		initialMode?: ExamMode;
		onModeChange?: ((mode: ExamMode) => void) | null;
		/** 停在模式选择首屏时，顶栏的 ‹ 交给外层：整页模式下就是离开测评页 */
		onLeave?: (() => void) | null;
	};

	let {
		fullPage = false,
		onClose = null,
		modelId = '',
		initialTopic = '',
		initialMode = 'flash',
		onModeChange = null,
		onLeave = null
	}: Props = $props();

	// 模型列表只认 basic-agent 的 /v1/models，没登记就是空的。
	let availableModels = $state<AgentModelOption[]>([]);
	let modelsLoading = $state(false);

	// 可写 $derived：跟着 props 走，模型列表回来后也能就地改（$state + $effect 的替代写法）
	let selectedModelId = $derived(modelId);

	// URL 上的 ?mode= 变了就重新预选；pickMode 会把选择写回 URL，两边不会打架
	let mode = $derived(initialMode);
	/**
	 * 正在跑的模式。空串 = 停在模式选择首屏。
	 *
	 * 刻意不从 URL 读：刷新页面时如果照着 ?mode= 直接开跑，一次误刷新就是
	 * 一整轮 LLM 调用。URL 上的 mode 只负责预选那张卡，开跑永远要用户点一下。
	 */
	let running = $state<'' | ExamMode>('');
	/** 只用来强制重挂面板：同一个模式再来一局时 {#if} 分支不变，靠它触发重建 */
	let runToken = $state(0);
	/** 刷新前正在做的整卷（同一标签页的存档）。有它就直接回到那张卷，不回首屏、不重新出卷 */
	let resume = $state<SavedFullExam | null>(null);
	/** 上次退出时的闪卡（同一标签页的存档）。有它就接着刷，不重新出卡 */
	let resumeFlash = $state<SavedFlashDeck | null>(null);
	/** 闪卡的作答方式。开关放在顶栏，出卡的那几秒里就能先选好 */
	let flashInputMode = $state<'flip' | 'type'>('flip');

	let topic = $state('');
	let selectedSourceKeys = $state<string[]>([]);
	let notebooks = $state<KnowledgeCollection[]>([]);
	let errorMsg = $state('');
	let panelTitle = $state('');

	let panelWidth = $state(0);
	let isFullscreen = $state(false);
	let rootEl = $state<HTMLElement>();
	let resizeObserver: ResizeObserver | null = null;

	let wide = $derived(panelWidth >= 760);

	// 来源（file）粒度在这里被折叠成笔记本 id —— 后端 notebook_ids 只认笔记本。
	// 这是既有行为，闪卡沿用同一套，没有在这次改动里悄悄改语义。
	let notebookIds = $derived([
		...new Set(
			selectedSourceKeys
				.map((key) => parseSourceKey(key)?.collectionId)
				.filter((id): id is string => Boolean(id))
		)
	]);

	let headerTitle = $derived(running === '' ? '智能测评' : panelTitle || '智能测评');

	let headerSubtitle = $derived(
		running === 'flash' ? '闪卡模式' : running === 'full' ? '整卷模式' : '基于课程知识库'
	);

	// 接着做的那一轮按存档里的范围和模型显示，不按首屏现在选着的
	let activeSaved = $derived(
		running === 'full' ? resume : running === 'flash' ? resumeFlash : null
	);
	let activeTopic = $derived((activeSaved?.topic ?? topic).trim());
	let activeNotebookIds = $derived(activeSaved?.notebookIds ?? notebookIds);
	let activeModelName = $derived.by(() => {
		const id = activeSaved?.modelId ?? selectedModelId;
		return availableModels.find((model) => model.id === id)?.name || id;
	});

	// 顶栏「出题范围」胶囊：第一个笔记本名 +N；没选笔记本就是主题或全部
	let scopeNames = $derived(
		activeNotebookIds
			.map((id) => notebooks.find((item) => item.id === id)?.name)
			.filter((name): name is string => Boolean(name))
	);
	let scopeLabel = $derived(
		scopeNames.length > 0
			? `${scopeNames[0]}${scopeNames.length > 1 ? ` +${scopeNames.length - 1}` : ''}`
			: activeNotebookIds.length > 0
				? `${activeNotebookIds.length} 个笔记本`
				: activeTopic || '全部笔记本'
	);
	let scopeTitle = $derived(
		[
			activeTopic ? `主题：${activeTopic}` : '',
			scopeNames.length > 0 ? `笔记本：${scopeNames.join('、')}` : '',
			activeNotebookIds.length === 0 ? '检索全部笔记本' : ''
		]
			.filter(Boolean)
			.join('\n')
	);

	$effect(() => {
		if (!initialTopic || notebooks.length === 0) {
			return;
		}

		if (!topic) {
			topic = initialTopic;
		}

		if (selectedSourceKeys.length > 0) {
			return;
		}

		const collection = findCollection(initialTopic, notebooks);

		if (collection) {
			selectedSourceKeys = sourceKeysForCollection(collection.id, notebooks);
		}
	});

	const pickMode = (next: ExamMode) => {
		mode = next;
		onModeChange?.(next);
	};

	const startSelected = () => {
		if (!selectedModelId) {
			errorMsg = '请先选择可用模型。';
			return;
		}

		errorMsg = '';
		panelTitle = '';
		leavingCost = '';
		confirmLeave = false;
		forgetSaved();
		running = mode;
		runToken += 1;
	};

	/** 开始新一轮或明确放弃时清掉存档；同一时间只留一份，进来时接哪个才不会有歧义 */
	const forgetSaved = () => {
		resume = null;
		resumeFlash = null;
		clearFullExam();
		clearFlashDeck();
	};

	/**
	 * 面板报上来的「现在结束这一轮会丢什么」。结束会清掉本标签页的存档（刷了一半的卡组、
	 * 答了一半的卷子），所以有进度时先问一句——不然点一下就全没了。
	 */
	let leavingCost = $state('');
	let confirmLeave = $state(false);

	const backToPicker = (confirmed = false) => {
		if (!confirmed && leavingCost) {
			confirmLeave = true;
			return;
		}
		confirmLeave = false;
		leavingCost = '';
		// 主动回到首屏：之后刷新、再进来都不该再把人拉回去
		forgetSaved();
		running = '';
		panelTitle = '';
		// 这一轮留下的报错（比如判卷失败）跟着这一轮一起收掉，别挂在首屏上
		errorMsg = '';
	};

	/**
	 * 顶栏的 ‹。整页模式（有 onLeave）下它永远是「离开测评」：进度留在本标签页的存档里，
	 * 下次进来接着做（闪卡存档就是按「点返回离开不丢」设计的）。放弃这一轮是另一个动作，
	 * 在顶栏右侧的「结束这一轮」。嵌在别处、没有 onLeave 时，‹ 才兼做结束。
	 */
	const goBack = () => {
		if (onLeave) {
			onLeave();
			return;
		}
		backToPicker();
	};

	let backLabel = $derived(
		onLeave ? (running === '' ? '返回' : '离开测评，进度会保留') : '回到模式选择'
	);

	/**
	 * 换模式重开一局。
	 *
	 * 用 runToken 强制重挂面板，而不是「先置空再用 microtask 设回去」——后者能不能
	 * 触发重挂，取决于它和 Svelte 的 flush 谁先跑到，属于碰运气。
	 */
	const switchRunningMode = (next: ExamMode) => {
		forgetSaved();
		pickMode(next);
		panelTitle = '';
		errorMsg = '';
		leavingCost = '';
		confirmLeave = false;
		running = next;
		runToken += 1;
	};

	const onFullscreenChange = () => {
		isFullscreen = document.fullscreenElement === rootEl;
	};

	const toggleFullscreen = async () => {
		if (!rootEl) {
			return;
		}

		if (document.fullscreenElement === rootEl) {
			await document.exitFullscreen().catch(() => {});
			return;
		}

		await rootEl.requestFullscreen().catch(() => {});
	};

	onMount(() => {
		document.addEventListener('fullscreenchange', onFullscreenChange);

		// 整卷答到一半刷新了：接着做。这和「刷新不自动开跑」不冲突——那条是怕误刷新白花一轮
		// 模型调用，这里只是把本地存档摆回来，一次调用都不花
		const saved = loadFullExam();
		const savedFlash = saved ? null : loadFlashDeck();
		if (saved) {
			resume = saved;
			mode = 'full';
			running = 'full';
			runToken += 1;
		} else if (savedFlash) {
			resumeFlash = savedFlash;
			mode = 'flash';
			running = 'flash';
			runToken += 1;
		}

		if (rootEl) {
			resizeObserver = new ResizeObserver(([entry]) => {
				panelWidth = Math.round(entry.contentRect.width);
			});

			resizeObserver.observe(rootEl);
			panelWidth = Math.round(rootEl.getBoundingClientRect().width);
		}

		modelsLoading = true;
		void getAgentModels()
			.then((list) => {
				availableModels = list.data.map((model) => ({
					id: model.id,
					name: model.name || model.id
				}));

				if (!availableModels.some((model) => model.id === selectedModelId)) {
					selectedModelId = availableModels[0]?.id ?? '';
				}
			})
			.catch(() => {
				availableModels = [];
				selectedModelId = '';
				errorMsg = '读不到 basic-agent 的模型列表，请确认它已经启动。';
			})
			.finally(() => {
				modelsLoading = false;
			});
	});

	onDestroy(() => {
		resizeObserver?.disconnect();

		// onDestroy 在 SSR 渲染完也会跑一次，那边没有 document。
		if (!browser) {
			return;
		}

		document.removeEventListener('fullscreenchange', onFullscreenChange);

		if (document.fullscreenElement === rootEl) {
			document.exitFullscreen().catch(() => {});
		}
	});
</script>

<div bind:this={rootEl} class="flex h-full min-h-0 flex-col bg-gray-900 text-gray-100">
	<!-- 顶栏照答疑页的样子：细边、胶囊、左边标题右边范围和模型 -->
	<nav
		class="flex shrink-0 flex-wrap items-center gap-x-2.5 gap-y-2 border-b border-white/[0.04] px-3 py-2"
	>
		{#if running !== '' || onLeave}
			<button
				type="button"
				class="hover:bg-gray-850 flex size-9 shrink-0 items-center justify-center rounded-xl text-gray-400 transition hover:text-white"
				onclick={goBack}
				aria-label={backLabel}
				title={backLabel}
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
		{/if}

		<div class="flex min-w-0 items-center gap-2 text-sm">
			<span class="truncate font-medium text-white">{headerTitle}</span>
			<span class="text-gray-600" aria-hidden="true">/</span>
			<span class="shrink-0 text-gray-400">{headerSubtitle}</span>
		</div>

		{#if confirmLeave}
			<div class="flex min-w-0 items-center gap-1.5 rounded-full bg-amber-500/15 py-1 pr-1 pl-3">
				<span class="truncate text-xs text-amber-200">{leavingCost}</span>
				<button
					type="button"
					class="shrink-0 rounded-full bg-white px-2.5 py-1 text-xs font-medium text-black transition hover:bg-gray-200"
					onclick={() => backToPicker(true)}
				>
					仍然结束
				</button>
				<button
					type="button"
					class="shrink-0 rounded-full px-2.5 py-1 text-xs text-amber-100 transition hover:bg-white/10"
					onclick={() => (confirmLeave = false)}
				>
					继续
				</button>
			</div>
		{/if}

		<div class="ml-auto flex min-w-0 flex-wrap items-center gap-2">
			{#if running !== ''}
				<span
					class="inline-flex max-w-56 min-w-0 items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-gray-200"
					title={scopeTitle}
				>
					<svg
						class="size-3 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.8"
						aria-hidden="true"
					>
						<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
						></path>
					</svg>
					<span class="truncate">{scopeLabel}</span>
				</span>

				<span
					class="hidden min-w-0 items-center gap-1.5 px-1 text-xs text-gray-500 sm:inline-flex"
					title="本次已锁定出题模型"
				>
					<svg
						class="size-3 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<rect x="5" y="11" width="14" height="10" rx="2"></rect>
						<path d="M8 11V7a4 4 0 0 1 8 0v4"></path>
					</svg>
					<span class="max-w-40 truncate">{activeModelName}</span>
				</span>
			{:else}
				<select
					class="hover:bg-gray-850 h-8 max-w-52 min-w-0 cursor-pointer rounded-lg bg-gray-900 px-1.5 text-sm text-gray-200 transition outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60 disabled:cursor-not-allowed disabled:opacity-60"
					bind:value={selectedModelId}
					disabled={modelsLoading || availableModels.length === 0}
					aria-label="测评模型"
					title="选择测评模型"
				>
					{#each availableModels as model (model.id)}
						<option value={model.id}>{model.name || model.id}</option>
					{/each}
				</select>
			{/if}

			{#if running === 'flash'}
				<div
					class="inline-flex rounded-full border border-white/10 bg-white/[0.03] p-0.5 text-[11px]"
					role="group"
					aria-label="作答方式"
					title="只影响填空卡；选择卡一律点选作答"
				>
					<!-- 提示挂在外面这一组上：挂在按钮上会顶掉按钮自己的名字，读屏时两个按钮念出来一模一样 -->
					<button
						type="button"
						class={`rounded-full px-2.5 py-1 transition ${
							flashInputMode === 'flip'
								? 'bg-white/10 text-white'
								: 'text-gray-400 hover:text-gray-200'
						}`}
						aria-pressed={flashInputMode === 'flip'}
						onclick={() => (flashInputMode = 'flip')}
					>
						翻卡自评
					</button>
					<button
						type="button"
						class={`rounded-full px-2.5 py-1 transition ${
							flashInputMode === 'type'
								? 'bg-white/10 text-white'
								: 'text-gray-400 hover:text-gray-200'
						}`}
						aria-pressed={flashInputMode === 'type'}
						onclick={() => (flashInputMode = 'type')}
					>
						输入作答
					</button>
				</div>
			{/if}

			{#if running !== '' && onLeave}
				<!-- 放弃这一轮、回模式选择：和左上角的「离开测评」分开，那个会把进度留着 -->
				<button
					type="button"
					class="hover:bg-gray-850 rounded-full px-3 py-1.5 text-xs text-gray-400 transition hover:text-white"
					onclick={() => backToPicker()}
				>
					结束这一轮
				</button>
			{/if}

			{#if !fullPage}
				<button
					type="button"
					class="hover:bg-gray-850 rounded-xl p-2 text-gray-400 transition hover:text-white"
					onclick={toggleFullscreen}
					aria-label={isFullscreen ? '退出全屏' : '全屏'}
					title={isFullscreen ? '退出全屏' : '全屏'}
				>
					<svg
						class="size-4"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						aria-hidden="true"
					>
						{#if isFullscreen}
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M9 9V4.5M9 9H4.5M9 9 3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5 5.25 5.25"
							></path>
						{:else}
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15"
							></path>
						{/if}
					</svg>
				</button>

				{#if onClose}
					<button
						type="button"
						class="hover:bg-gray-850 rounded-xl p-2 text-gray-400 transition hover:text-white"
						onclick={() => onClose?.()}
						aria-label="关闭"
					>
						<svg
							class="size-4"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="1.5"
							aria-hidden="true"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"></path>
						</svg>
					</button>
				{/if}
			{/if}
		</div>
	</nav>

	{#if errorMsg}
		<div class="mx-auto mt-3 w-full max-w-3xl shrink-0 px-4">
			<div class="rounded-2xl bg-red-500/10 px-4 py-2.5 text-sm text-red-300">{errorMsg}</div>
		</div>
	{/if}

	<div class="flex min-h-0 flex-1 flex-col">
		{#key runToken}
			{#if running === 'flash'}
				<FlashcardPanel
					modelId={resumeFlash?.modelId ?? selectedModelId}
					topic={resumeFlash?.topic ?? topic}
					notebookIds={resumeFlash?.notebookIds ?? notebookIds}
					resume={resumeFlash}
					inputMode={flashInputMode}
					onTitle={(value) => (panelTitle = value)}
					onError={(value) => (errorMsg = value)}
					onExit={() => backToPicker(true)}
					onLeavingCost={(cost) => (leavingCost = cost)}
					onSwitchToFull={() => switchRunningMode('full')}
				/>
			{:else if running === 'full'}
				<FullExamPanel
					modelId={resume?.modelId ?? selectedModelId}
					topic={resume?.topic ?? topic}
					notebookIds={resume?.notebookIds ?? notebookIds}
					{resume}
					{wide}
					onTitle={(value) => (panelTitle = value)}
					onError={(value) => (errorMsg = value)}
					onExit={() => backToPicker(true)}
					onLeavingCost={(cost) => (leavingCost = cost)}
					onSwitchToFlash={() => switchRunningMode('flash')}
				/>
			{:else}
				<ExamModePicker
					bind:mode
					bind:topic
					bind:selectedKeys={selectedSourceKeys}
					bind:collections={notebooks}
					onPick={pickMode}
					onStart={startSelected}
				/>
			{/if}
		{/key}
	</div>
</div>
