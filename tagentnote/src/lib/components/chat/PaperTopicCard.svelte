<script lang="ts">
	import '$lib/components/essay/paper.css';

	import type { EssayTopic, PaperCard } from '$lib/data/essay';

	type Props = {
		card: Extract<PaperCard, { kind: 'topic' }>;
		/** 出题请求还没回来 */
		pending: boolean;
		/** 这道题已经是任务卡上的论文题目了 */
		adopted: boolean;
		onAdopt: (topic: EssayTopic) => void;
		onRetry: () => void;
	};

	let { card, pending, adopted, onAdopt, onRetry }: Props = $props();
</script>

<!-- 题签：和批改卡同一张纸，学生一眼看出「这是一道题」而不是一段聊天 -->
<article class="essay-paper slip" aria-label="小论文题目">
	<p class="paper-eyebrow">小论文题目</p>

	{#if card.topic}
		{@const topic = card.topic}
		<h3 class="title">{topic.title}</h3>

		<ol class="requirements">
			{#each topic.requirements as item, index (index)}
				<li>{item}</li>
			{/each}
		</ol>

		<p class="meta">
			建议篇幅 {topic.suggested_chars.toLocaleString()} 字左右{#if !topic.grounded}
				· 没检索到笔记本材料，这道题按课程通用内容出{/if}
		</p>

		<div class="actions">
			<button type="button" class="paper-button" disabled={adopted} onclick={() => onAdopt(topic)}>
				{adopted ? '已设为本次题目' : '设为本次题目'}
			</button>
			<span class="hint">
				{adopted
					? '写好后把正文粘进输入框，点「交稿批改」。'
					: '设好后，交稿批改就按这道题判「切题与内容」。'}
			</span>
		</div>
	{:else if card.error}
		<div class="paper-notice" role="alert">
			<p>{card.error}</p>
			<button type="button" class="paper-button" onclick={onRetry}>重新出题</button>
		</div>
	{:else if pending}
		<p class="paper-status" role="status">正在按课程材料出题……</p>
	{:else}
		<div class="paper-notice">
			<p>这次出题没有完成：已停止，或页面在出题时刷新了。</p>
			<button type="button" class="paper-button" onclick={onRetry}>重新出题</button>
		</div>
	{/if}
</article>

<style>
	.slip {
		max-width: 36rem;
		padding: 1.125rem 1.25rem 1.25rem;
	}

	.title {
		margin: 0.5rem 0 0;
		font-family: var(--song);
		font-size: 1.1875rem;
		font-weight: 700;
		line-height: 1.55;
		color: var(--ink);
	}

	.requirements {
		margin: 0.875rem 0 0;
		padding: 0.625rem 0 0 1.5rem;
		border-top: 1px solid var(--rule-strong);
		list-style: decimal;
		font-family: var(--song);
		font-size: 0.9375rem;
		line-height: 1.85;
		color: var(--ink);
	}

	.requirements li::marker {
		color: var(--ink-soft);
	}

	.meta {
		margin: 0.625rem 0 0;
		font-family: var(--song);
		font-size: 0.8125rem;
		color: var(--ink-soft);
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.875rem;
		margin-top: 1rem;
	}

	.hint {
		font-family: var(--kai);
		font-size: 0.875rem;
		color: var(--vermilion);
	}
</style>
