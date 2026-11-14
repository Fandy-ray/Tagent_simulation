<script lang="ts">
	import '$lib/styles/space-theme.css';
	import './learning.css';
	import CosmicLayer from '$lib/components/space/CosmicLayer.svelte';
	import OrbitMark from '$lib/components/icons/OrbitMark.svelte';
	import { resolve } from '$app/paths';
	let { children } = $props();
</script>

<div class="space-theme space-learning">
	<CosmicLayer />
	<header class="learn-header">
		<div class="learn-frame">
			<a class="learn-brand" href={resolve('/space-exploration')}>
				<span class="learn-orbit"><OrbitMark /></span>
				航天探索实验室
			</a>
			<nav class="learn-actions" aria-label="航天学习导航">
				<a class="learn-button secondary" href={resolve('/space-exploration/learn/notebook')}
					>我的笔记本</a
				>
				<a class="learn-button secondary" href={resolve('/space-exploration/learn')}>选择学段</a>
			</nav>
		</div>
	</header>
	{@render children()}
</div>
