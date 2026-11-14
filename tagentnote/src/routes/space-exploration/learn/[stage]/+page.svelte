<script lang="ts">
	import { resolve } from '$app/paths';
	import { spaceStages, spaceTopics } from '$lib/data/spaceLearning';
	import StageContent from './StageContent.svelte';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
	let level = $derived(spaceStages[data.stage]);
	let stagePath = $derived(resolve('/space-exploration/learn/[stage]', { stage: data.stage }));
</script>

<svelte:head><title>{level.label}航天探索 · 航天探索实验室</title></svelte:head>
<main class="learn-frame learn-workspace">
	<div class="learn-workspace-heading">
		<div>
			{#if data.topic}<a class="learn-back" href={stagePath}>← 返回{level.label}专题</a>{/if}
			<h1>{data.topic?.title ?? `${level.label}航天专题`}</h1>
			<p>{level.approach}</p>
		</div>
	</div>
	{#if data.topic}
		<div class="learn-workspace-grid">
			{#key `${data.stage}/${data.topic.id}/${data.lesson?.id}/${data.assessment}`}
				<StageContent
					stage={data.stage}
					topic={data.topic}
					lesson={data.lesson}
					assessment={data.assessment}
				/>
			{/key}
		</div>
	{:else}
		<div class="learn-topic-grid">
			{#each spaceTopics[data.stage] as topic (topic.id)}
				<article class="learn-panel">
					<h2>{topic.title}</h2>
					<ul class="learn-topic-lessons">
						{#each topic.lessons as lesson (lesson.id)}
							<li>
								<a href={`${stagePath}?topic=${topic.id}&lesson=${lesson.id}`}
									>{lesson.title} <span aria-hidden="true">→</span></a
								>
							</li>
						{/each}
						<li>
							<a href={`${stagePath}?topic=${topic.id}&lesson=review`}
								>专题闯关测评 <span aria-hidden="true">→</span></a
							>
						</li>
					</ul>
				</article>
			{/each}
		</div>
	{/if}
</main>
