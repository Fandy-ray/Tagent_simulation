<script lang="ts">
	import type { spaceTopics, SpaceStage } from '$lib/data/spaceLearning';

	type Topic = (typeof spaceTopics)[SpaceStage][number];
	let { topic, stagePath, completed }: { topic: Topic; stagePath: string; completed: string[] } =
		$props();
	const defaultPositions = [23, 43, 32, 14];
	const courses: Record<string, number[]> = {
		satellites: defaultPositions,
		station: [43, 26, 14, 32],
		motion: [15, 29, 44, 26],
		moonlight: [37, 15, 26, 44],
		model: [16, 40, 19, 43],
		observations: [43, 35, 24, 15]
	};
	let positions = $derived(courses[topic.id] ?? defaultPositions);
	let nodes = $derived([...topic.lessons, { id: 'review', title: '专题闯关测评' }]);
	let waypoints = $derived(
		nodes.map((_, index) => ({
			x: positions[index % positions.length],
			y: index * 100 + 50
		}))
	);
	let coursePath = $derived(
		waypoints
			.map(({ x, y }, index) => {
				if (index === 0) return `M${x} ${y}`;
				const previous = waypoints[index - 1];
				return `C${previous.x} ${previous.y + 44} ${x} ${y - 44} ${x} ${y}`;
			})
			.join(' ')
	);
	let next = $derived(nodes.findIndex(({ id }) => !completed.includes(id)));
</script>

<section class="flight" id={topic.id} aria-labelledby={`flight-${topic.id}`}>
	<header class="flight-header">
		<h2 id={`flight-${topic.id}`}>{topic.title}</h2>
		<p>已完成 {nodes.filter(({ id }) => completed.includes(id)).length} / {nodes.length} 关</p>
	</header>
	<div class="flight-course">
		<svg
			class="flight-line"
			viewBox={`0 0 100 ${nodes.length * 100}`}
			preserveAspectRatio="none"
			aria-hidden="true"
		>
			<path d={coursePath} />
		</svg>
		<ol>
			{#each nodes as node, i (node.id)}
				{@const state = completed.includes(node.id) ? 'done' : i === next ? 'next' : 'locked'}
				<li style:--node-x={`${waypoints[i].x}%`} class={state}>
					{#snippet emblem()}
						<span class="flight-emblem" aria-hidden="true">
							{#if node.id === 'review'}
								<svg viewBox="0 0 64 64" fill="none">
									<path d="M9 32H55M32 10V54" stroke="currentColor" stroke-width="2.5" />
									<path
										d="M8 22h13v20H8zM43 22h13v20H43z"
										fill="#504471"
										stroke="currentColor"
										stroke-width="1.5"
									/>
									<rect x="25" y="20" width="14" height="24" rx="5" fill="currentColor" />
									<circle cx="32" cy="31" r="3" fill="#191628" />
									<path
										d="M26 13h12m-12 38h12"
										stroke="currentColor"
										stroke-width="3"
										stroke-linecap="round"
									/>
								</svg>
							{:else}
								<svg viewBox="0 0 64 64" fill="none">
									<ellipse
										cx="32"
										cy="32"
										rx="30"
										ry="12"
										transform="rotate(-31 32 32)"
										stroke="currentColor"
										stroke-opacity=".48"
										stroke-dasharray="3 4"
									/>
									<g transform="rotate(-22 32 32)">
										<path
											d="M5 26h18v12H5zM41 26h18v12H41z"
											fill="#423669"
											stroke="currentColor"
											stroke-width="1.3"
										/>
										<path
											d="M11 26v12m6-12v12m30-12v12m6-12v12M5 32h18m18 0h18"
											stroke="currentColor"
											stroke-opacity=".6"
										/>
										<rect x="23" y="22" width="18" height="20" rx="5" fill="currentColor" />
										<path
											d="M32 22v-6m-4 0h8"
											stroke="currentColor"
											stroke-width="1.7"
											stroke-linecap="round"
										/>
										<circle cx="32" cy="32" r="3" fill="#342844" />
									</g>
								</svg>
							{/if}
						</span>
						<span class="flight-node-text">
							<small>{state === 'done' ? '已完成' : state === 'next' ? '下一关' : '待解锁'}</small>
							<strong>{node.title}</strong>
						</span>
					{/snippet}
					{#if state === 'locked'}
						<span class="flight-node">{@render emblem()}</span>
					{:else}
						<a class="flight-node" href={`${stagePath}?topic=${topic.id}&lesson=${node.id}`}
							>{@render emblem()}</a
						>
					{/if}
				</li>
			{/each}
		</ol>
	</div>
</section>

<style>
	.flight {
		max-width: 660px;
		margin-inline: auto;
		scroll-margin-top: 16px;
	}
	.flight + .flight {
		margin-top: 20px;
	}
	.flight-header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 6px 16px;
		padding: 13px 16px;
		border-block: 1px solid var(--m3-outline-variant);
		background: #1d1b20e8;
	}
	.flight-header h2 {
		font-size: 19px;
		font-weight: 600;
	}
	.flight-header p {
		color: var(--m3-on-surface-variant);
		font-size: 13px;
		font-variant-numeric: tabular-nums;
	}
	.flight-course {
		position: relative;
	}
	.flight-line {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
	}
	.flight-line path {
		fill: none;
		stroke: #a996d2;
		stroke-opacity: 0.7;
		stroke-width: 1.5;
		stroke-dasharray: 3 6;
		vector-effect: non-scaling-stroke;
	}
	ol {
		position: relative;
		list-style: none;
	}
	li {
		position: relative;
		height: 108px;
	}
	.flight-node {
		position: absolute;
		top: 50%;
		left: var(--node-x);
		display: flex;
		align-items: center;
		gap: 11px;
		width: fit-content;
		max-width: calc(100% - var(--node-x) + 40px);
		transform: translate(-40px, -50%);
		border-radius: 12px;
	}
	.flight-emblem {
		display: grid;
		width: 80px;
		height: 80px;
		flex: none;
		place-items: center;
		color: var(--m3-primary);
	}
	.flight-emblem svg {
		width: 76px;
		height: 76px;
	}
	.next .flight-emblem {
		color: #ffe2ad;
	}
	.next .flight-emblem svg {
		filter: drop-shadow(0 0 9px #f6b45f55);
		animation: satellite-pulse 2.8s ease-in-out infinite;
	}
	.locked .flight-emblem {
		color: #9b91aa;
	}
	@keyframes satellite-pulse {
		0%,
		100% {
			transform: scale(1);
		}
		48% {
			transform: scale(0.86);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.next .flight-emblem svg {
			animation: none;
		}
	}
	.flight-node-text {
		min-width: 0;
		display: grid;
		gap: 2px;
		text-shadow: 0 2px 5px #090711;
	}
	.flight-node-text small {
		color: var(--m3-on-surface-variant);
		font-size: 12px;
	}
	.flight-node-text strong {
		font-size: 15px;
		line-height: 1.35;
	}
	.next .flight-node-text small {
		color: var(--space-amber);
	}
	a.flight-node:hover strong {
		color: var(--m3-primary);
	}
</style>
