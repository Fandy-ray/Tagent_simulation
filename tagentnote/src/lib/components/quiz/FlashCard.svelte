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

	const stripeClass = $derived(
		graded === 'correct' ? 'bg-emerald-500' : graded === 'wrong' ? 'bg-red-500' : 'bg-blue-500'
	);

	const optionClass = (index: number) => {
		if (!flipped) {
			return picked === index
				? 'border-blue-500 bg-blue-950/40 text-blue-300'
				: 'border-gray-700 hover:bg-gray-800';
		}

		if (card.type === 'choice' && index === card.correct_index) {
			return 'border-emerald-800 bg-emerald-950/40 text-emerald-300';
		}

		return picked === index
			? 'border-red-900 bg-red-950/40 text-red-300'
			: 'border-gray-800 text-gray-500';
	};
</script>

<div class="flip-scene h-full max-h-[560px] min-h-0 w-full">
	<div class="flip-inner" class:is-flipped={flipped}>
		<!-- 正面 -->
		<section
			class="flip-face bg-gray-850 rounded-2xl border border-gray-700 shadow-sm"
			aria-hidden={flipped}
		>
			<!-- 竖条要被圆角裁住，但 overflow-hidden 不能待在 .flip-face 上（见 <style> 里的说明），
			     所以单独套一层只管裁剪的壳。 -->
			<div class="pointer-events-none absolute inset-0 overflow-hidden rounded-2xl">
				<div class="absolute top-0 bottom-0 left-0 w-1 bg-blue-500"></div>
			</div>

			{#if coverClickable}
				<button
					type="button"
					class="absolute inset-0 z-10 cursor-pointer"
					onclick={onReveal}
					aria-label="翻面看答案"
					title="翻面看答案（空格）"
				></button>
			{/if}

			<div class="flex h-full min-h-0 flex-col p-5 pl-7">
				<div class="flex shrink-0 items-center gap-2">
					<span class="rounded-lg bg-blue-950/40 px-2 py-1 text-xs font-semibold text-blue-300">
						{card.type === 'choice' ? '闪卡选择' : '闪卡填空'}
					</span>

					<span class="font-mono text-xs text-gray-500">{card.id} · {position}</span>
				</div>

				{#if card.type === 'cloze'}
					<!-- safe center：内容短就居中，长了照样从顶上开始滚，不会把开头切掉 -->
					<div
						class="flex min-h-0 flex-1 flex-col [justify-content:safe_center] overflow-y-auto py-4"
					>
						{#if !cueRepeatsText(card.cue, card.text)}
							<div class="shrink-0 text-sm text-gray-400">
								<MathText value={card.cue} />
							</div>
						{/if}

						<div class="mt-2.5 shrink-0 text-lg leading-relaxed font-medium">
							<MathText value={before} /><span
								class="mx-1 inline-block min-w-20 border-b-2 border-blue-500 px-2 text-center text-blue-500"
								>{blankText}</span
							><MathText value={after} />
						</div>
					</div>

					{#if inputMode === 'type'}
						<div class="relative z-20 shrink-0">
							<label
								class="mb-2 block text-xs font-semibold text-gray-500"
								for={`flash-answer-${card.id}`}
							>
								你的答案
							</label>

							<div class="flex gap-2">
								<input
									id={`flash-answer-${card.id}`}
									class="min-w-0 flex-1 rounded-xl border border-gray-700 bg-transparent px-4 py-3 text-base outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-500/10 disabled:opacity-60"
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
									class="shrink-0 rounded-xl bg-white px-5 text-sm font-medium text-gray-900 transition hover:bg-gray-200 disabled:opacity-60"
									disabled={flipped}
									onclick={onSubmit}
								>
									提交
								</button>
							</div>
						</div>
					{:else}
						<div class="shrink-0 font-mono text-xs text-gray-600">点击卡片或按 空格 翻面看答案</div>
					{/if}
				{:else}
					<div class="mt-4 shrink-0 text-lg leading-relaxed font-medium">
						<MathText value={card.question} />
					</div>

					<div class="relative z-20 mt-4 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
						{#each card.options as option, index (index)}
							<button
								type="button"
								class={`rounded-xl border px-3.5 py-2.5 text-left text-sm transition disabled:cursor-default ${optionClass(index)}`}
								disabled={flipped}
								onclick={() => onPick(index)}
							>
								<span class="mr-2 font-mono font-semibold text-gray-400">{LETTERS[index]}</span>
								<MathText value={option} />
							</button>
						{/each}
					</div>

					<div class="mt-2 shrink-0 font-mono text-xs text-gray-600">选一个，当场判定</div>
				{/if}
			</div>
		</section>

		<!-- 反面 -->
		<section
			class="flip-face flip-back bg-gray-850 rounded-2xl border border-gray-700 shadow-sm"
			aria-hidden={!flipped}
		>
			<div class="pointer-events-none absolute inset-0 overflow-hidden rounded-2xl">
				<div class={`absolute top-0 bottom-0 left-0 w-1 ${stripeClass}`}></div>
			</div>

			<div
				class="flex h-full min-h-0 flex-col [justify-content:safe_center] overflow-y-auto p-5 pl-7"
			>
				<div class="flex shrink-0 items-center justify-between gap-2">
					<span class="font-mono text-xs text-gray-500">{card.id} · {position}</span>

					{#if graded === 'correct'}
						<span
							class="rounded-lg border border-emerald-900 bg-emerald-950/40 px-2.5 py-1 text-xs font-semibold text-emerald-300"
						>
							答对了
						</span>
					{:else if graded === 'wrong'}
						<span
							class="rounded-lg border border-red-900 bg-red-950/40 px-2.5 py-1 text-xs font-semibold text-red-300"
						>
							答错了
						</span>
					{/if}
				</div>

				{#if card.type === 'cloze'}
					<div class="mt-3.5 text-sm leading-relaxed text-gray-400">
						<MathText value={before} /><span class="font-semibold text-blue-300"
							><MathText value={answerText} /></span
						><MathText value={after} />
					</div>

					{#if inputMode === 'type' && graded !== null}
						<div class="mt-3.5 rounded-xl bg-gray-800 p-3">
							<div class="mb-1 text-[11px] font-semibold text-gray-500">我的答案</div>
							<div class="text-sm leading-relaxed">{typed.trim() || '未作答'}</div>
						</div>
					{/if}

					<div class="mt-3.5 rounded-xl border border-emerald-900/60 bg-emerald-950/30 p-3">
						<div class="mb-1 text-[11px] font-semibold text-emerald-400">参考答案</div>
						<!-- 逐条渲染而不是 join 成一个字符串：accept 里常常混着
						     LaTeX 写法和纯文字写法，拼在一起就没法各自判定了 -->
						<div
							class="flex flex-wrap items-center gap-x-2 gap-y-1 text-base leading-relaxed font-medium"
						>
							{#each card.accept as item, index (index)}
								{#if index > 0}
									<span class="text-gray-600">/</span>
								{/if}
								<MathText value={item} />
							{/each}
						</div>
					</div>
				{:else}
					<div class="mt-3.5 text-sm leading-relaxed text-gray-400">
						<MathText value={card.question} />
					</div>

					<div class="mt-3.5 rounded-xl border border-emerald-900/60 bg-emerald-950/30 p-3">
						<div class="mb-1 text-[11px] font-semibold text-emerald-400">正确答案</div>
						<div class="text-base leading-relaxed font-medium">
							<span class="mr-1.5 font-mono">{LETTERS[card.correct_index]}</span>
							<MathText value={card.options[card.correct_index] ?? ''} />
						</div>
					</div>

					{#if picked !== null && picked !== card.correct_index}
						<div class="mt-2.5 rounded-xl bg-gray-800 p-3">
							<div class="mb-1 text-[11px] font-semibold text-gray-500">我选的</div>
							<div class="text-sm leading-relaxed">
								<span class="mr-1.5 font-mono">{LETTERS[picked]}</span>
								<MathText value={card.options[picked] ?? ''} />
							</div>
						</div>
					{/if}
				{/if}

				{#if card.explanation}
					<div class="mt-2.5 rounded-xl border border-blue-900/60 bg-blue-950/30 p-3">
						<div class="mb-1 text-[11px] font-semibold text-blue-400">解析</div>
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
	   需要裁剪的东西请套一层自己的壳，见上面那两个 .pointer-events-none 的裁剪层。

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
