<script lang="ts">
	import MathText from '$lib/components/MathText.svelte';
	import { cueRepeatsText } from '$lib/data/cue';
	import { LETTERS } from '$lib/data/exam';
	import type { FlashCard } from '$lib/data/flash';

	type Props = {
		card: FlashCard;
		/** flip = 翻卡自评；type = 输入作答。只对填空卡有意义，选择卡一律点选作答 */
		inputMode: 'flip' | 'type';
		flipped: boolean;
		typed: string;
		picked: number | null;
		graded: 'correct' | 'wrong' | null;
		position: string;
		onReveal: () => void;
		onTyped: (value: string) => void;
		onSubmit: () => void;
		onPick: (index: number) => void;
	};

	let {
		card,
		inputMode,
		flipped,
		typed,
		picked,
		graded,
		position,
		onReveal,
		onTyped,
		onSubmit,
		onPick
	}: Props = $props();

	// 后端保证 text 恰好含一个 ____（app/schema/exam.py:_exactly_one_blank）
	let before = $derived(card.type === 'cloze' ? (card.text.split('____')[0] ?? '') : '');
	let after = $derived(card.type === 'cloze' ? (card.text.split('____')[1] ?? '') : '');
	let answerText = $derived(card.type === 'cloze' ? (card.accept[0] ?? '') : '');

	let blankText = $derived(inputMode === 'type' && typed.trim() !== '' ? typed : ' ');

	// 正面在翻卡模式下整张可点；有输入框或选项时不能再套一层按钮
	let coverClickable = $derived(card.type === 'cloze' && inputMode === 'flip' && !flipped);

	const optionClass = (index: number) => {
		if (!flipped) {
			return picked === index
				? 'border-sky-400/50 bg-sky-500/10 text-sky-100'
				: 'border-white/[0.08] text-gray-200 hover:bg-white/[0.04]';
		}

		if (card.type === 'choice' && index === card.correct_index) {
			return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200';
		}

		return picked === index
			? 'border-red-500/40 bg-red-500/10 text-red-200'
			: 'border-white/[0.05] text-gray-500';
	};
</script>

<!-- relative：让卡片画在面板里那道「一叠卡」的边上面 -->
<div class="flip-scene relative h-full min-h-0 w-full">
	<div class="flip-inner" class:is-flipped={flipped}>
		<!-- 正面 -->
		<section
			class="flip-face rounded-3xl border border-white/[0.08] bg-[#1d1d1d] shadow-[0_24px_48px_-24px_rgba(0,0,0,0.6)]"
			aria-hidden={flipped}
		>
			{#if coverClickable}
				<button
					type="button"
					class="absolute inset-0 z-10 cursor-pointer rounded-3xl"
					onclick={onReveal}
					aria-label="翻面看答案"
					title="翻面看答案（空格）"
				></button>
			{/if}

			<div class="flex h-full min-h-0 flex-col p-6 sm:px-8 sm:py-7">
				<div class="flex shrink-0 items-center justify-between gap-2">
					<span
						class={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
							card.type === 'choice'
								? 'bg-violet-500/15 text-violet-300'
								: 'bg-sky-500/15 text-sky-300'
						}`}
					>
						{card.type === 'choice' ? '选择' : '填空'}
					</span>

					<span class="text-[11px] text-gray-500 tabular-nums">{card.id}</span>
				</div>

				{#if card.type === 'cloze'}
					<!-- safe center：内容短就居中，长了照样从顶上开始滚，不会把开头切掉 -->
					<div
						class="flex min-h-0 flex-1 flex-col [justify-content:safe_center] overflow-y-auto py-4"
					>
						{#if !cueRepeatsText(card.cue, card.text)}
							<div class="shrink-0 text-[13px] text-gray-500">
								<MathText value={card.cue} />
							</div>
						{/if}

						<div class="mt-3 shrink-0 text-xl leading-[1.85] font-medium text-white">
							<MathText value={before} /><span
								class="mx-1.5 inline-block min-w-[88px] border-b-2 border-sky-300 px-2 text-center text-sky-300"
								>{blankText}</span
							><MathText value={after} />
						</div>
					</div>

					{#if inputMode === 'type'}
						<div class="relative z-20 shrink-0">
							<label class="mb-2 block text-xs text-gray-500" for={`flash-answer-${card.id}`}>
								你的答案
							</label>

							<div class="flex gap-2">
								<input
									id={`flash-answer-${card.id}`}
									class="min-w-0 flex-1 rounded-2xl border border-white/[0.08] bg-white/[0.035] px-4 py-3 text-base text-gray-100 transition outline-none placeholder:text-gray-500 focus:border-white/20 disabled:opacity-60"
									placeholder="输入后回车，当场判定"
									autocomplete="off"
									value={typed}
									disabled={flipped}
									oninput={(event) => onTyped(event.currentTarget.value)}
									onkeydown={(event) => {
										// 中文输入法按回车是在确认候选词，不是提交
										if (event.key === 'Enter' && !event.isComposing) {
											event.preventDefault();
											onSubmit();
										}
									}}
								/>

								<button
									type="button"
									class="shrink-0 rounded-full bg-white px-5 text-sm font-medium text-black transition hover:bg-gray-200 disabled:opacity-60"
									disabled={flipped}
									onclick={onSubmit}
								>
									提交
								</button>
							</div>
						</div>
					{:else}
						<div class="flex shrink-0 items-center justify-center gap-1.5 text-xs text-gray-500">
							点卡片或按<kbd
								class="rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-px font-sans text-[11px] text-gray-300"
								>空格</kbd
							>翻面
						</div>
					{/if}
				{:else}
					<div class="mt-4 shrink-0 text-xl leading-[1.75] font-medium text-white">
						<MathText value={card.question} />
					</div>

					<div class="relative z-20 mt-4 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
						{#each card.options as option, index (index)}
							<button
								type="button"
								class={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-left text-sm transition disabled:cursor-default ${optionClass(index)}`}
								disabled={flipped}
								onclick={() => onPick(index)}
							>
								<span class="shrink-0 font-medium text-gray-400">{LETTERS[index]}</span>
								<span class="min-w-0"><MathText value={option} /></span>
							</button>
						{/each}
					</div>

					<div class="mt-3 flex shrink-0 items-center justify-center gap-1.5 text-xs text-gray-500">
						点选或按<kbd
							class="rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-px font-sans text-[11px] text-gray-300"
							>A–D</kbd
						>，当场判定
					</div>
				{/if}
			</div>
		</section>

		<!-- 反面 -->
		<section
			class="flip-face flip-back rounded-3xl border border-white/[0.08] bg-[#1d1d1d] shadow-[0_24px_48px_-24px_rgba(0,0,0,0.6)]"
			aria-hidden={!flipped}
		>
			<div
				class="flex h-full min-h-0 flex-col [justify-content:safe_center] overflow-y-auto p-6 sm:px-8 sm:py-7"
			>
				<div class="flex shrink-0 items-center justify-between gap-2">
					<span class="text-[11px] text-gray-500 tabular-nums">{card.id} · {position}</span>

					{#if graded === 'correct'}
						<span
							class="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-medium text-emerald-300"
						>
							答对了
						</span>
					{:else if graded === 'wrong'}
						<span class="rounded-full bg-red-500/15 px-2.5 py-0.5 text-xs font-medium text-red-300">
							答错了
						</span>
					{/if}
				</div>

				{#if card.type === 'cloze'}
					<div class="mt-4 text-sm leading-relaxed text-gray-400">
						<MathText value={before} /><span class="font-medium text-sky-300"
							><MathText value={answerText} /></span
						><MathText value={after} />
					</div>

					{#if inputMode === 'type' && graded !== null}
						<div class="mt-3 rounded-2xl bg-white/[0.04] p-3.5">
							<div class="mb-1 text-[11px] text-gray-500">我的答案</div>
							<div class="text-sm leading-relaxed text-gray-200">{typed.trim() || '未作答'}</div>
						</div>
					{/if}

					<div class="mt-3 rounded-2xl bg-emerald-500/10 p-3.5">
						<div class="mb-1 text-[11px] font-medium text-emerald-300">参考答案</div>
						<!-- 逐条渲染而不是 join 成一个字符串：accept 里常常混着
						     LaTeX 写法和纯文字写法，拼在一起就没法各自判定了 -->
						<div
							class="flex flex-wrap items-center gap-x-2 gap-y-1 text-base leading-relaxed font-medium text-white"
						>
							{#each card.accept as item, index (index)}
								{#if index > 0}
									<span class="text-gray-500">/</span>
								{/if}
								<MathText value={item} />
							{/each}
						</div>
					</div>
				{:else}
					<div class="mt-4 text-sm leading-relaxed text-gray-400">
						<MathText value={card.question} />
					</div>

					<div class="mt-3 rounded-2xl bg-emerald-500/10 p-3.5">
						<div class="mb-1 text-[11px] font-medium text-emerald-300">正确答案</div>
						<div class="text-base leading-relaxed font-medium text-white">
							<span class="mr-1.5">{LETTERS[card.correct_index]}</span>
							<MathText value={card.options[card.correct_index] ?? ''} />
						</div>
					</div>

					{#if picked !== null && picked !== card.correct_index}
						<div class="mt-2.5 rounded-2xl bg-white/[0.04] p-3.5">
							<div class="mb-1 text-[11px] text-gray-500">我选的</div>
							<div class="text-sm leading-relaxed text-gray-200">
								<span class="mr-1.5">{LETTERS[picked]}</span>
								<MathText value={card.options[picked] ?? ''} />
							</div>
						</div>
					{/if}
				{/if}

				{#if card.explanation}
					<div class="mt-2.5 rounded-2xl bg-white/[0.04] p-3.5">
						<div class="mb-1 text-[11px] font-medium text-sky-300">解析</div>
						<div class="text-sm leading-relaxed text-gray-300">
							<MathText value={card.explanation} />
						</div>
					</div>
				{/if}
			</div>
		</section>
	</div>
</div>

<style>
	/* 翻卡是这个模式的主要手感，值得一点 3D。Tailwind 里没有现成的
	   preserve-3d / backface-visibility，写成 scoped CSS 比一串任意值可读。 */
	.flip-scene {
		perspective: 1800px;
	}

	.flip-inner {
		position: relative;
		height: 100%;
		transform-style: preserve-3d;
		transition: transform 0.45s cubic-bezier(0.2, 0.7, 0.3, 1);
	}

	.flip-inner.is-flipped {
		transform: rotateY(180deg);
	}

	/*
	   这两面**不能**自己带 overflow:hidden。Safari 上一旦 backface-visibility:hidden
	   的元素同时有 overflow:hidden（或自带裁剪的圆角），backface 就会失效：正面不
	   藏起来，而是**镜像着**叠在反面上——选项和「答对了」反着写，还和反面文字错位
	   （用户实拍到过；Chromium 同视口复现不出来，所以只在部分浏览器上能看见）。
	   需要裁剪的东西请在面里另套一层只管裁剪的壳，别加在 .flip-face 上。

	   也别改用 opacity/visibility 去兜底藏另一面：试过，Chromium 会有一两秒画不出
	   刚露出来的那一面（opacity 已经是 1、位置也对，就是不画），整张卡空白。
	*/
	.flip-face {
		position: absolute;
		inset: 0;
		backface-visibility: hidden;
		-webkit-backface-visibility: hidden;
	}

	.flip-back {
		transform: rotateY(180deg);
	}

	@media (prefers-reduced-motion: reduce) {
		/* 不做 3D 翻转，改成瞬时切换：正反面靠 backface 仍然互斥 */
		.flip-inner {
			transition: none;
		}
	}
</style>
