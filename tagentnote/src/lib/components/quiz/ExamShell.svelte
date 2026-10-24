<script lang="ts">
	import { browser } from '$app/environment';
	import { onDestroy, onMount } from 'svelte';

	import { getAgentModels } from '$lib/apis/agent';
	import { clearFullExam, loadFullExam, type ExamMode, type SavedFullExam } from '$lib/data/exam';
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
	};

	let {
		fullPage = false,
		onClose = null,
		modelId = '',
		initialTopic = '',
		initialMode = 'flash',
		onModeChange = null
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
		running = mode;
		runToken += 1;
	};

	/**
	 * 面板报上来的「现在离开会丢东西」。闪卡的进度只在内存里，整卷有草稿要清，
	 * 都该在离开前问一句——不然点一下 ‹ 就把刷了一半的卡组丢了。
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
		// 主动离开这张卷：之后刷新不该再把人拉回来
		resume = null;
		clearFullExam();
		running = '';
		panelTitle = '';
	};

	/**
	 * 换模式重开一局。
	 *
	 * 用 runToken 强制重挂面板，而不是「先置空再用 microtask 设回去」——后者能不能
	 * 触发重挂，取决于它和 Svelte 的 flush 谁先跑到，属于碰运气。
	 */
	const switchRunningMode = (next: ExamMode) => {
		resume = null;
		clearFullExam();
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
		if (saved) {
			resume = saved;
			mode = 'full';
			running = 'full';
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

<div bind:this={rootEl} class="bg-gray-850 flex h-full min-h-0 flex-col text-gray-100">
	<div
		class="flex shrink-0 items-center justify-between border-b border-white/[0.08] px-3.5 pt-3 pb-2"
	>
		<div class="flex min-w-0 items-baseline gap-2">
			{#if running !== ''}
				<button
					type="button"
					class="shrink-0 rounded-lg px-1 text-sm text-gray-400 transition hover:text-gray-200"
					onclick={() => backToPicker()}
					title="回到模式选择"
				>
					‹
				</button>

				{#if confirmLeave}
					<div
						class="flex min-w-0 items-center gap-2 rounded-lg border border-amber-900 bg-amber-950/50 px-2.5 py-1"
					>
						<span class="truncate text-[11px] text-amber-200">{leavingCost}</span>
						<button
							type="button"
							class="shrink-0 rounded-md bg-white px-2 py-1 text-[11px] font-medium text-gray-900 transition hover:bg-gray-200"
							onclick={() => backToPicker(true)}
						>
							仍然返回
						</button>
						<button
							type="button"
							class="shrink-0 rounded-md border border-gray-700 px-2 py-1 text-[11px] text-gray-300 transition hover:bg-white/5"
							onclick={() => (confirmLeave = false)}
						>
							继续刷
						</button>
					</div>
				{/if}
			{/if}

			<div class="truncate font-semibold">{headerTitle}</div>

			<div class="text-xs whitespace-nowrap text-gray-500">{headerSubtitle}</div>
		</div>

		<div class="flex min-w-0 items-center gap-1.5">
			<select
				class="bg-gray-850 h-8 max-w-52 min-w-0 rounded-lg border border-white/[0.18] px-2 text-xs text-gray-100 outline-none focus:border-blue-400 disabled:cursor-not-allowed disabled:opacity-60"
				bind:value={selectedModelId}
				disabled={modelsLoading || running !== '' || availableModels.length === 0}
				aria-label="测评模型"
				title={running === '' ? '选择测评模型' : '本次已锁定出题模型'}
			>
				{#each availableModels as model (model.id)}
					<option value={model.id}>{model.name || model.id}</option>
				{/each}
			</select>

			{#if !fullPage}
				<button
					type="button"
					class="rounded-lg p-1.5 text-gray-400 transition hover:bg-gray-800 hover:text-white"
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
						class="rounded-lg p-1.5 text-gray-400 transition hover:bg-gray-800 hover:text-white"
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
	</div>

	{#if errorMsg}
		<div class="mx-3.5 mt-2 shrink-0 rounded-lg bg-red-950/40 px-3 py-2 text-sm text-red-400">
			{errorMsg}
		</div>
	{/if}

	<div class="flex min-h-0 flex-1 flex-col px-3.5 py-3">
		{#key runToken}
			{#if running === 'flash'}
				<FlashcardPanel
					modelId={selectedModelId}
					{topic}
					{notebookIds}
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
