<script lang="ts">
	import { onMount } from 'svelte';
	import { downloadSpaceRecords, readSpaceRecords, type SpaceRecord } from '$lib/data/spaceRecords';
	let entries = $state<SpaceRecord[]>([]);
	let oldNote = $state('');
	onMount(() => {
		entries = readSpaceRecords();
		try {
			oldNote = localStorage.getItem('space-learning.orbit-note') ?? '';
		} catch {
			/* unavailable */
		}
	});
</script>

<svelte:head><title>我的笔记本 · 航天探索实验室</title></svelte:head>
<main class="learn-frame learn-workspace">
	<div class="learn-workspace-heading">
		<div>
			<h1>我的笔记本</h1>
			<p>查看保存在本机的问答、观察和测评记录。</p>
		</div>
		<button
			class="learn-button"
			type="button"
			disabled={!entries.length && !oldNote}
			onclick={() =>
				downloadSpaceRecords(
					oldNote
						? [
								...entries,
								{
									id: 'legacy',
									kind: '笔记',
									title: '卫星轨道',
									content: oldNote,
									context: '早期体验笔记',
									date: new Date().toISOString()
								}
							]
						: entries
				)}>导出学案</button
		>
	</div>
	<div class="learn-records">
		{#each entries as entry (entry.id)}
			<article class="learn-panel">
				<p class="learn-muted">{entry.kind} · {entry.context}</p>
				<h2>{entry.title}</h2>
				<p class="learn-record-text">{entry.content}</p>
			</article>
		{/each}
		{#if oldNote}<article class="learn-panel">
				<h2>卫星轨道</h2>
				<p class="learn-record-text">{oldNote}</p>
			</article>{/if}
		{#if !entries.length && !oldNote}<p class="learn-panel">
				还没有学习记录。做一次实验或把回答加入笔记，记录就会出现在这里。
			</p>{/if}
	</div>
</main>
