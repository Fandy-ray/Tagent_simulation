<script lang="ts">
	import { resolve } from '$app/paths';
	import { spaceStages, stageKeys } from '$lib/data/spaceLearning';
</script>

<svelte:head><title>选择学段 · 航天探索实验室</title></svelte:head>

<main class="learn-frame learn-selection">
	<section class="learn-intro">
		<img src={resolve('/images/hubble-orbit.jpg')} alt="" />
		<div>
			<h1>选择你的学段</h1>
			<p>从适合你的讲解开始，边观察、边动手。进入后可以随时切换学段。</p>
		</div>
	</section>
	<div class="learn-stage-grid">
		{#each stageKeys as stage (stage)}
			{@const level = spaceStages[stage]}
			<a class="learn-stage-card" href={resolve('/space-exploration/learn/[stage]', { stage })}>
				<h2>{level.label}</h2>
				<strong>{level.approach}</strong>
				<p>{level.description}</p>
				<span>进入{level.label}体验 <span aria-hidden="true">→</span></span>
			</a>
		{/each}
	</div>
</main>
