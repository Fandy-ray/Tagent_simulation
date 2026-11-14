<script lang="ts">
	import KnowledgeCombobox from '$lib/components/quiz/KnowledgeCombobox.svelte';
	import { type ExamMode } from '$lib/data/exam';
	import { type KnowledgeCollection } from '$lib/data/knowledge';

	type Props = {
		mode: ExamMode;
		fullOnly?: boolean;
		topic: string;
		selectedKeys: string[];
		collections: KnowledgeCollection[];
		onPick: (mode: ExamMode) => void;
		onStart: () => void;
	};

	let {
		mode = $bindable(),
		fullOnly = false,
		topic = $bindable(),
		selectedKeys = $bindable(),
		collections = $bindable(),
		onPick,
		onStart
	}: Props = $props();

	const pick = (value: ExamMode) => {
		mode = value;
		onPick(value);
	};
</script>

{#snippet checkmark(on: boolean)}
	<span class="mode-check" class:checked={on} aria-hidden="true">
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

<div class="picker-scroll">
	<main class="picker">
		<header>
			<h1>{fullOnly ? '专题整卷测评' : '选择测评模式'}</h1>
			<p>{fullOnly ? '确认专题范围后，再生成试卷。' : '选择练习方式，再设置出题范围。'}</p>
		</header>

		<div class="mode-list" class:full-only={fullOnly} role="group" aria-label="测评模式">
			{#if !fullOnly}
				<button
					type="button"
					class="mode-card"
					onclick={() => pick('flash')}
					aria-pressed={mode === 'flash'}
				>
					<div class="flex items-center gap-2.5">
						<svg
							class="mode-icon"
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

						<div class="mode-title">闪卡模式</div>

						<span class="ml-auto">{@render checkmark(mode === 'flash')}</span>
					</div>

					<p class="mode-description">填空可翻面自评或输入答案，练习可随时暂停。</p>

					<div class="mode-details"><strong>6–12 张</strong><span>填空与选择 · 即时判定</span></div>
				</button>
			{/if}
			<button
				type="button"
				class="mode-card"
				onclick={() => pick('full')}
				aria-pressed={mode === 'full'}
			>
				<div class="flex items-center gap-2.5">
					<svg
						class="mode-icon"
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

					<div class="mode-title">整卷模式</div>

					<span class="ml-auto">{@render checkmark(mode === 'full')}</span>
				</div>

				<p class="mode-description">包含填空、选择和大题。交卷后，模型按评分要点批改大题。</p>

				<div class="mode-details"><strong>16–21 题</strong><span>满分 100 分</span></div>
			</button>
		</div>

		<section class="scope" aria-labelledby="scope-title">
			<h2 id="scope-title">出题范围</h2>
			<div class="scope-row">
				<KnowledgeCombobox
					bind:value={topic}
					bind:selectedKeys
					bind:collections
					placeholder="输入主题，或选择笔记本与来源"
					onSubmit={onStart}
				/>
				<button type="button" class="start-button" onclick={onStart}>
					{mode === 'flash' ? '开始刷闪卡' : '生成整卷'}
					<svg
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.8"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" /></svg
					>
				</button>
			</div>
			<p>笔记本和来源可多选。未选择时检索全部。</p>
		</section>
	</main>
</div>

<style>
	.picker-scroll {
		min-height: 0;
		flex: 1;
		overflow-y: auto;
	}
	.picker {
		width: min(800px, 100% - 40px);
		margin-inline: auto;
		padding-block: clamp(28px, 6vh, 56px) 44px;
	}
	header {
		margin-bottom: 22px;
	}
	h1 {
		margin: 0;
		font-size: clamp(25px, 3.3vw, 32px);
		font-weight: 600;
		line-height: 1.25;
	}
	header p,
	.scope p {
		margin: 8px 0 0;
		color: var(--m3-on-surface-variant);
		line-height: 1.65;
		font-size: 14px;
	}
	.mode-list {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 14px;
	}
	.mode-list.full-only {
		grid-template-columns: 1fr;
	}
	.mode-card {
		display: flex;
		min-width: 0;
		flex-direction: column;
		padding: 16px 18px;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 15px;
		background: var(--m3-surface-low);
		color: var(--m3-on-surface);
		text-align: start;
		transition:
			background-color 180ms ease,
			border-color 180ms ease;
	}
	.mode-card:hover {
		background: var(--m3-surface-high);
	}
	.mode-card[aria-pressed='true'] {
		border-color: var(--m3-primary);
		background: #282135;
	}
	.mode-title {
		font-size: 17px;
		font-weight: 600;
	}
	.mode-icon {
		box-sizing: content-box;
		width: 18px;
		height: 18px;
		flex: none;
		padding: 7px;
		border-radius: 10px;
		background: var(--m3-surface-high);
		color: var(--m3-on-surface-variant);
	}
	.mode-card[aria-pressed='true'] .mode-icon {
		background: #342844;
		color: var(--m3-primary);
	}
	.mode-check {
		display: grid;
		width: 21px;
		height: 21px;
		place-items: center;
		border: 1px solid var(--m3-on-surface-variant);
		border-radius: 50%;
	}
	.mode-check.checked {
		border-color: var(--m3-primary);
		background: var(--m3-primary);
		color: var(--m3-on-primary);
	}
	.mode-description {
		margin: 10px 0 12px;
		color: var(--m3-on-surface-variant);
		font-size: 14px;
		line-height: 1.65;
	}
	.mode-details {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 10px;
		margin-top: auto;
		padding-top: 10px;
		border-top: 1px solid var(--m3-outline-variant);
		color: var(--m3-on-surface-variant);
		font-size: 12px;
	}
	.mode-details strong {
		color: var(--m3-on-surface);
		font-weight: 600;
		font-variant-numeric: tabular-nums;
	}
	.scope {
		margin-top: 22px;
		padding-top: 16px;
		border-top: 1px solid var(--m3-outline-variant);
	}
	.scope-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: start;
		gap: 10px;
	}
	.scope h2 {
		margin: 0 0 8px;
		font-size: 15px;
		font-weight: 600;
	}
	.scope p {
		font-size: 12px;
	}
	.start-button {
		display: inline-flex;
		min-height: 42px;
		flex: none;
		align-items: center;
		justify-content: center;
		gap: 8px;
		padding-inline: 16px;
		border-radius: 10px;
		background: var(--m3-primary);
		color: var(--m3-on-primary);
		font-size: 14px;
		font-weight: 600;
	}
	.start-button:hover {
		background: #e1d1ff;
	}
	.start-button svg {
		width: 17px;
		height: 17px;
	}
	@media (max-width: 610px) {
		.picker {
			width: calc(100% - 32px);
		}
		.mode-list {
			grid-template-columns: 1fr;
		}
		.scope-row {
			grid-template-columns: 1fr;
		}
		.start-button {
			justify-self: start;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.mode-card {
			transition: none;
		}
	}
</style>
