<script lang="ts">
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { markSpaceComplete, readSpaceProgress } from '$lib/data/spaceProgress';
	import TopicFlightPath from './TopicFlightPath.svelte';
	import { spaceStages, spaceTopics } from '$lib/data/spaceLearning';
	import StageContent from './StageContent.svelte';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
	let level = $derived(spaceStages[data.stage]);
	let progress = $state<string[]>([]);
	let ready = $state(false);
	const selectedTopic = $derived(data.topic);
	const lessonIndex = $derived(
		selectedTopic?.lessons.findIndex(({ id }) => id === data.lesson?.id) ?? -1
	);
	const canEnter = $derived(
		!selectedTopic ||
			selectedTopic.lessons
				.slice(0, data.assessment ? selectedTopic.lessons.length : Math.max(0, lessonIndex))
				.every(({ id }) => progress.includes(progressKey(selectedTopic.id, id)))
	);
	function progressKey(topicId: string, lessonId: string) {
		return `${data.stage}/${topicId}/${lessonId}`;
	}
	function complete(topicId: string, lessonId: string) {
		progress = markSpaceComplete(progressKey(topicId, lessonId));
	}
	onMount(() => {
		const reload = () => {
			progress = readSpaceProgress();
			ready = true;
		};
		reload();
		window.addEventListener('storage', reload);
		window.addEventListener('pageshow', reload);
		return () => {
			window.removeEventListener('storage', reload);
			window.removeEventListener('pageshow', reload);
		};
	});
	const topicId = $derived(data.topic?.id ?? '');
	let stagePath = $derived(resolve('/space-exploration/learn/[stage]', { stage: data.stage }));
</script>

<svelte:head><title>{level.label}航天探索 · 航天探索实验室</title></svelte:head>
<main class="learn-frame learn-workspace">
	<div class="learn-workspace-heading" class:flight-heading={!data.topic}>
		<div>
			{#if data.topic}<a class="learn-back" href={stagePath}>← 返回{level.label}专题</a>{/if}
			<h1>{data.topic?.title ?? `${level.label}航天专题`}</h1>
			<p>{level.approach}</p>
		</div>
	</div>
	{#if data.topic && ready && !canEnter}
		<section class="learn-panel">
			<h2>这一关还未解锁</h2>
			<p>沿航线完成前面的小节，就能到达这里。</p>
			<a class="learn-button" href={`${stagePath}#${data.topic.id}`}>返回航线</a>
		</section>
	{:else if data.topic && ready}
		<div class="learn-workspace-grid">
			{#key `${data.stage}/${data.topic.id}/${data.lesson?.id}/${data.assessment}`}
				<StageContent
					stage={data.stage}
					topic={data.topic}
					lesson={data.lesson}
					assessment={data.assessment}
					completed={data.topic.lessons
						.filter(({ id }) => progress.includes(progressKey(topicId, id)))
						.map(({ id }) => id)}
					onComplete={(lessonId) => complete(topicId, lessonId)}
				/>
			{/key}
		</div>
	{:else if !data.topic}
		<div class="learn-flight-paths">
			{#each spaceTopics[data.stage] as topic (topic.id)}
				<TopicFlightPath
					{topic}
					{stagePath}
					completed={progress
						.filter((key) => key.startsWith(`${data.stage}/${topic.id}/`))
						.map((key) => key.split('/')[2])}
				/>
			{/each}
		</div>
	{/if}
</main>
