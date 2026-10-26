<script lang="ts">
	import {
		DIMENSIONS,
		dimensionPoints,
		formatPoints,
		fullMarks,
		humanizeRefs,
		integerPoints,
		rubricLines,
		type DimensionName,
		type DimensionResult
	} from '$lib/data/essay';

	type Props = {
		/** null = 还没批完，只印满分那一行 */
		dimensions: DimensionResult[] | null;
		score: number | null;
		pending?: boolean;
		/** 展开细则的那一维 */
		selected?: DimensionName | null;
		/** 结果刚到时让分数依次写上去；只演一次 */
		animate?: boolean;
	};

	let {
		dimensions,
		score,
		pending = false,
		selected = $bindable(null),
		animate = false
	}: Props = $props();

	// 交稿前用前端抄的那份维度表；拿到结果后一律以后端下发的为准
	const columns = $derived(
		dimensions
			? dimensions.map((item) => ({
					name: item.name,
					label: item.label,
					weight: item.weight,
					result: item as DimensionResult | null
				}))
			: DIMENSIONS.map((item) => ({ ...item, result: null as DimensionResult | null }))
	);

	const totalFull = $derived(columns.reduce((sum, column) => sum + fullMarks(column.weight), 0));

	// 格子里显示整数，三格加起来等于总分；精确值在点开的细则里
	const points = $derived(dimensions ? integerPoints(dimensions, score) : null);

	const current = $derived(dimensions?.find((item) => item.name === selected) ?? null);

	const toggle = (name: DimensionName) => {
		selected = selected === name ? null : name;
	};
</script>

<div class="score-sheet" class:animate>
	<div class="table-wrap">
		<table>
			<caption class="sr-only">评分栏：三个评分项的满分与得分</caption>

			<thead>
				<tr>
					<th scope="col" class="corner">评分项</th>

					{#each columns as column (column.name)}
						<th scope="col">
							{#if column.result}
								<button
									type="button"
									class:selected={selected === column.name}
									aria-expanded={selected === column.name}
									aria-controls={selected === column.name ? 'rubric-detail' : undefined}
									onclick={() => toggle(column.name)}
								>
									{column.label}
								</button>
							{:else}
								{column.label}
							{/if}
						</th>
					{/each}

					<th scope="col">总分</th>
				</tr>
			</thead>

			<tbody>
				<tr>
					<th scope="row">满分</th>

					{#each columns as column (column.name)}
						<td>{fullMarks(column.weight)}</td>
					{/each}

					<td>{totalFull}</td>
				</tr>

				<tr class="earned">
					<th scope="row">得分</th>

					{#each columns as column, index (column.name)}
						<td>
							{#if column.result}
								<span
									class="hand"
									style={`--order: ${index}`}
									title={`按要点折算 ${formatPoints(dimensionPoints(column.result))} 分`}
								>
									{points?.get(column.name) ?? formatPoints(dimensionPoints(column.result))}
								</span>
							{:else if pending}
								<span class="pending" aria-label="批改中">…</span>
							{/if}
						</td>
					{/each}

					<td class="total">
						{#if score !== null}
							<span class="hand total-num" style={`--order: ${columns.length}`}>{score}</span>
						{:else if pending}
							<span class="pending" aria-label="批改中">…</span>
						{/if}
					</td>
				</tr>
			</tbody>
		</table>
	</div>

	{#if current}
		<div id="rubric-detail" class="rubric">
			<p class="rubric-head">
				{current.label}：{current.hits.length + current.misses.length} 条要点命中
				{current.hits.length} 条，{current.hits.length}/{current.hits.length +
					current.misses.length} × {fullMarks(current.weight)} =
				{formatPoints(dimensionPoints(current))} 分{#if points?.has(current.name) && String(points.get(current.name)) !== formatPoints(dimensionPoints(current))}，记
					{points.get(current.name)} 分（三项取整后加起来等于总分）{/if}
			</p>

			<!-- 编号是评语里「第几条」的出处，不是装饰：只有和后端顺序对得上时才有 -->
			<ul>
				{#each rubricLines(current) as line (line.point)}
					<li>
						<span class="tick" aria-hidden="true">{line.hit ? '✓' : '✗'}</span>
						<span class="sr-only">{line.hit ? '命中：' : '未命中：'}</span>
						<span>
							{#if line.n}<span class="num">{line.n}.</span>{/if}{line.point}
						</span>
					</li>
				{/each}
			</ul>

			{#if current.comment}
				<p class="comment">{humanizeRefs(current.comment)}</p>
			{/if}
		</div>
	{:else if dimensions}
		<p class="note">点评分项的名字，可以看这一项逐条勾了哪些要点。</p>
	{/if}
</div>

<style>
	/* 颜色与字体变量由稿纸（EssayWorkbench 的 .paper）提供 */
	.table-wrap {
		overflow-x: auto;
	}

	table {
		width: 100%;
		min-width: 30rem;
		border-collapse: collapse;
		font-family: var(--song);
		font-size: 0.875rem;
		color: var(--ink);
		table-layout: fixed;
	}

	th,
	td {
		height: 2.75rem;
		padding: 0.25rem 0.5rem;
		border: 1px solid var(--rule-strong);
		text-align: center;
		font-weight: 400;
	}

	thead th {
		height: 2.5rem;
		color: var(--ink-soft);
	}

	.corner,
	tbody th {
		width: 4.5rem;
		color: var(--ink-soft);
	}

	thead button {
		padding: 0.25rem 0.375rem;
		border-radius: 2px;
		color: var(--ink);
		text-decoration: underline dotted var(--rule-strong);
		text-underline-offset: 0.3em;
	}

	thead button:hover,
	thead button.selected {
		background: var(--rule-wash);
	}

	thead button.selected {
		text-decoration-style: solid;
		text-decoration-color: var(--ink);
	}

	thead button:focus-visible {
		outline: 2px solid var(--ink);
		outline-offset: 1px;
	}

	.earned td {
		height: 3.5rem;
	}

	.total {
		width: 7rem;
	}

	.hand {
		display: inline-block;
		font-family: var(--kai);
		font-size: 1.375rem;
		line-height: 1;
		color: var(--vermilion);
	}

	/* 总分是整张稿纸上唯一「写大」的字，略歪一点，像手写上去的 */
	.total-num {
		font-size: 2.25rem;
		transform: rotate(-4deg);
	}

	.animate .hand {
		animation: ink-in 0.5s ease-out both;
		animation-delay: calc(var(--order) * 160ms);
	}

	.animate .total-num {
		animation-name: ink-in-total;
	}

	@keyframes ink-in {
		from {
			opacity: 0;
			transform: scale(1.15);
		}
	}

	@keyframes ink-in-total {
		from {
			opacity: 0;
			transform: rotate(-4deg) scale(1.2);
		}
		to {
			transform: rotate(-4deg);
		}
	}

	.pending {
		color: var(--rule-strong);
		animation: breathe 1.6s ease-in-out infinite;
	}

	@keyframes breathe {
		50% {
			opacity: 0.35;
		}
	}

	.note {
		margin: 0.625rem 0 0;
		font-family: var(--song);
		font-size: 0.8125rem;
		color: var(--ink-soft);
	}

	.rubric {
		margin-top: 1rem;
		padding: 0.875rem 1rem 1rem;
		border-left: 2px solid var(--rule-strong);
		background: var(--rule-wash);
		font-family: var(--song);
	}

	.rubric-head {
		margin: 0 0 0.5rem;
		font-size: 0.8125rem;
		color: var(--ink-soft);
	}

	ul {
		margin: 0;
		padding: 0;
		list-style: none;
		font-size: 0.9375rem;
		line-height: 1.9;
	}

	li {
		display: flex;
		gap: 0.625rem;
	}

	.tick {
		flex: none;
		width: 1em;
		font-family: var(--kai);
		font-size: 1.125rem;
		color: var(--vermilion);
		text-align: center;
	}

	.num {
		margin-right: 0.375em;
		color: var(--ink-soft);
		font-variant-numeric: tabular-nums;
	}

	.comment {
		margin: 0.625rem 0 0;
		font-family: var(--kai);
		font-size: 1rem;
		line-height: 1.75;
		color: var(--vermilion);
	}

	@media (prefers-reduced-motion: reduce) {
		.animate .hand,
		.pending {
			animation: none;
		}
	}
</style>
