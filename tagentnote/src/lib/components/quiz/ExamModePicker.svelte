<script lang="ts">
	import KnowledgeCombobox from '$lib/components/quiz/KnowledgeCombobox.svelte';
	import { type ExamMode } from '$lib/data/exam';
	import { type KnowledgeCollection } from '$lib/data/knowledge';

	type Props = {
		mode: ExamMode;
		topic: string;
		selectedKeys: string[];
		collections: KnowledgeCollection[];
		onPick: (mode: ExamMode) => void;
		onStart: () => void;
	};

	let {
		mode = $bindable(),
		topic = $bindable(),
		selectedKeys = $bindable(),
		collections = $bindable(),
		onPick,
		onStart
	}: Props = $props();

	const cardClass = (value: ExamMode) =>
		`rounded-3xl border p-5 text-left transition ${
			mode === value
				? 'border-white/50 bg-white/[0.06]'
				: 'border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.05]'
		}`;

	const pick = (value: ExamMode) => {
		mode = value;
		onPick(value);
	};
</script>

<!-- 选中标记：以前靠蓝框一眼看出选的是哪张，换成白灰配色后光靠边框太淡，补一个勾。
     状态本身由按钮的 aria-pressed 报给读屏，这里只是给眼睛看的 -->
{#snippet checkmark(on: boolean)}
	<span
		class={`flex size-5 shrink-0 items-center justify-center rounded-full border transition ${
			on ? 'border-white bg-white text-black' : 'border-white/25'
		}`}
		aria-hidden="true"
	>
		{#if on}
			<svg
				class="size-3"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="3"
				stroke-linecap="round"
				stroke-linejoin="round"
			>
				<path d="M20 6 9 17l-5-5"></path>
			</svg>
		{/if}
	</span>
{/snippet}

<div class="flex h-full flex-col items-center justify-center overflow-y-auto px-4 py-4 text-center">
	<div class="text-xl font-semibold tracking-tight text-white">今天想怎么练？</div>

	<p class="mt-2 max-w-md text-sm leading-relaxed text-gray-400">
		两种模式用同一套课程知识库，区别在题型、判定方式和一次要花多久。
	</p>

	<div class="mt-6 grid w-full max-w-3xl grid-cols-1 gap-3.5 sm:grid-cols-2">
		<button
			type="button"
			class={cardClass('flash')}
			onclick={() => pick('flash')}
			aria-pressed={mode === 'flash'}
		>
			<div class="flex items-center gap-2.5">
				<svg
					class="size-5 shrink-0"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
					stroke-linecap="round"
					stroke-linejoin="round"
					aria-hidden="true"
				>
					<rect x="2.5" y="7.5" width="14" height="13" rx="2"></rect>
					<path d="M6.5 7.5v-2a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"></path>
				</svg>

				<div class="text-[15px] font-semibold">闪卡模式</div>

				<span
					class="ml-auto rounded-full bg-sky-500/15 px-2 py-0.5 text-[11px] font-medium text-sky-300"
				>
					推荐
				</span>

				{@render checkmark(mode === 'flash')}
			</div>

			<p class="mt-2.5 text-[13px] leading-relaxed text-gray-400">
				填空和选择混着来。填空可以翻面自评，也可以打字作答；选择点一下就判 ——
				对错当场就知道。随时开、随时停。
			</p>

			<div class="mt-3 flex flex-wrap gap-1.5">
				<!--
					6~12：分片各出 3~4 张、共 9~12 张，去重后会掉几张，低于 6 张
					（FLASH_DECK_MIN_CARDS）才算失败。写 9~12 是拿去重前的上限当承诺。
				-->
				<span class="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-gray-300">
					6~12 张
				</span>
				<span class="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-gray-300">
					填空 + 选择
				</span>
				<span class="rounded-full bg-emerald-500/15 px-2.5 py-1 text-[11px] text-emerald-300">
					判定即时 · 不调模型
				</span>
			</div>
		</button>

		<button
			type="button"
			class={cardClass('full')}
			onclick={() => pick('full')}
			aria-pressed={mode === 'full'}
		>
			<div class="flex items-center gap-2.5">
				<svg
					class="size-5 shrink-0"
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

				<div class="text-[15px] font-semibold">整卷模式</div>

				<span class="ml-auto">{@render checkmark(mode === 'full')}</span>
			</div>

			<p class="mt-2.5 text-[13px] leading-relaxed text-gray-400">
				填空 + 选择 + 大题，按 100
				分计。大题由出卷的同一个模型逐条对着评分要点批改。一次坐下来做完。
			</p>

			<div class="mt-3 flex flex-wrap gap-1.5">
				<span class="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-gray-300">
					16~21 题 · 100 分
				</span>
				<span class="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-gray-300">
					含大题
				</span>
				<span class="rounded-full bg-amber-500/15 px-2.5 py-1 text-[11px] text-amber-300">
					提交后还要等模型批改
				</span>
			</div>
		</button>
	</div>

	<div class="mt-5 flex w-full max-w-3xl flex-col items-center">
		<KnowledgeCombobox
			bind:value={topic}
			bind:selectedKeys
			bind:collections
			placeholder="输入主题，或选择笔记本与来源"
			onSubmit={onStart}
		/>

		<p class="mt-2 max-w-md text-[11px] text-gray-500">
			选项来自笔记本模块里已有的笔记本和来源，可多选。不选则检索全部。
		</p>
	</div>

	<button
		type="button"
		class="mt-5 min-h-10 rounded-full bg-white px-6 text-sm font-medium text-black transition hover:bg-gray-200"
		onclick={onStart}
	>
		{mode === 'flash' ? '开始刷闪卡' : '生成整卷'}
	</button>
</div>
