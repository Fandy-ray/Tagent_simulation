<script lang="ts">
	import { resolve } from '$app/paths';
	import {
		learningContextParams,
		spaceStages,
		spaceTopics,
		type SpaceStage
	} from '$lib/data/spaceLearning';
	import { saveSpaceRecord } from '$lib/data/spaceRecords';
	import OrbitExperiment from './OrbitExperiment.svelte';

	type Topic = (typeof spaceTopics)[SpaceStage][number];
	type Lesson = Topic['lessons'][number];
	let {
		stage,
		topic,
		lesson,
		assessment
	}: { stage: SpaceStage; topic: Topic; lesson?: Lesson; assessment: boolean } = $props();
	let context = $derived(`${spaceStages[stage].label} / ${topic.title}`);
	let id = $derived(`${stage}/${topic.id}/${lesson?.id ?? 'review'}`);
	let panel = $state<'read' | 'observe'>('read');
	let answerOpen = $state(false);
	let reviewing = $state(false);
	let queue = $state<number[]>([]);
	let checks = $state(0);
	let feedback = $state('');
	let recordStatus = $state('');
	let observation = $state('');
	let answerPending = $state(false);
	let answeredWrong = $state(false);

	const hrefForLesson = (lessonId: string) =>
		`${resolve('/space-exploration/learn/[stage]', { stage })}?topic=${topic.id}&lesson=${lessonId}`;

	function toolHref(route: '/qa' | '/exam', extra: Record<string, string>) {
		const params = learningContextParams(stage, topic.id, lesson?.id);
		for (const [key, value] of Object.entries(extra)) params.set(key, value);
		return `${resolve(route)}?${params}`;
	}

	function save(kind: '笔记' | '实验' | '测评', title: string, content: string) {
		try {
			saveSpaceRecord({ id: `${id}/${kind}`, kind, context, title, content });
			recordStatus = '已存入我的笔记本。';
		} catch {
			recordStatus = '无法保存记录，请检查浏览器存储设置。';
		}
	}

	function startFlash() {
		queue = topic.lessons.map((_, index) => index);
		checks = 0;
		feedback = '';
		answerPending = false;
		reviewing = true;
	}

	function checkFlash(index: number) {
		const card = topic.lessons[queue[0]];
		answeredWrong = index !== card.correct;
		feedback = answeredWrong
			? `答错了。正确选项是「${card.options[card.correct]}」，这张卡会回到队尾。`
			: '答对了。';
		checks += 1;
		answerPending = true;
	}

	function nextFlash() {
		const [current, ...rest] = queue;
		queue = answeredWrong ? [...rest, current] : rest;
		answerPending = false;
		feedback = queue.length ? '' : '本专题的闪卡全部通过。';
		if (!queue.length)
			save('测评', topic.title, `完成 ${topic.lessons.length} 张闪卡，作答 ${checks} 次。`);
	}
</script>

<aside class="learn-catalog" aria-labelledby="lessons-heading">
	<h2 id="lessons-heading">专题小节</h2>
	<ul>
		{#each topic.lessons as item, index (item.id)}
			<li>
				<a
					class="learn-catalog-link"
					aria-current={lesson?.id === item.id ? 'page' : undefined}
					href={hrefForLesson(item.id)}><span>{index + 1}</span>{item.title}</a
				>
			</li>
		{/each}
		<li>
			<a
				class="learn-catalog-link"
				aria-current={assessment ? 'page' : undefined}
				href={hrefForLesson('review')}>专题闯关测评</a
			>
		</li>
	</ul>
</aside>

<section class="learn-panel" aria-labelledby="mission-title">
	{#if assessment}
		<h2 id="mission-title">专题闯关测评</h2>
		<div class="learn-body">
			<p>{topic.title}</p>
			<div class="learn-assessment">
				<article class="learn-answer">
					<h3>闪卡练习</h3>
					<p>{topic.lessons.length} 张卡 · 即时反馈 · 错题回队尾</p>
					<button class="learn-button" type="button" onclick={startFlash}
						>{reviewing ? '重新练习' : '开始闪卡'}</button
					>
				</article>
				<article class="learn-answer">
					<h3>整卷测评</h3>
					<p>按专题出卷，支持公式和大题批改。</p>
					<a
						class="learn-button secondary"
						href={toolHref('/exam', { mode: 'full', topic: topic.title })}>前往整卷测评</a
					>
				</article>
			</div>
			{#if reviewing && queue.length}
				{@const card = topic.lessons[queue[0]]}
				<h3>{card.title}</h3>
				<p class="learn-muted">还剩 {queue.length} 张</p>
				<div class="learn-options">
					{#each card.options as option, index (option)}
						<button
							class="learn-button secondary"
							disabled={answerPending}
							type="button"
							onclick={() => checkFlash(index)}>{option}</button
						>
					{/each}
				</div>
				{#if answerPending}<button class="learn-button" type="button" onclick={nextFlash}
						>{queue.length === 1 && !answeredWrong ? '完成测评' : '下一张'}</button
					>{/if}
			{/if}
			<p role="status">{feedback}</p>
			<a
				class="learn-button secondary"
				href={toolHref('/qa', { mode: 'paper', paper_title: topic.title })}>打开科普小论文批改</a
			>
		</div>
	{:else if lesson}
		<h2 id="mission-title">{lesson.title}</h2>
		<nav class="learn-steps" aria-label="小节内容">
			<button type="button" aria-pressed={panel === 'read'} onclick={() => (panel = 'read')}
				>阅读讲解</button
			>
			<button type="button" aria-pressed={panel === 'observe'} onclick={() => (panel = 'observe')}
				>观察与实验</button
			>
		</nav>
		<div class="learn-body">
			{#if panel === 'read'}
				<div class="learn-reading">
					<details class="learn-answer learn-disclosure" bind:open={answerOpen}>
						<summary>
							<span>
								<strong>{answerOpen ? '收起答案' : '查看答案'}</strong>
								{#if !answerOpen}<small>先想一想，用自己的话说说你的猜想。</small>{/if}
							</span>
							<svg
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.8"
								stroke-linecap="round"
								stroke-linejoin="round"
								aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg
							>
						</summary>
						<div class="learn-revealed-answer">
							<h3>{spaceStages[stage].label}讲解</h3>
							<p>{lesson.explanation}</p>
						</div>
					</details>
					<div class="learn-actions learn-reading-actions">
						<a class="learn-button secondary" href={toolHref('/qa', {})}
							>问航天智能体 <span aria-hidden="true">↗</span></a
						>
						{#if answerOpen}
							<button
								class="learn-button secondary"
								type="button"
								onclick={() =>
									save('笔记', lesson?.title ?? topic.title, lesson?.explanation ?? '')}
								>加入我的笔记本</button
							>
						{/if}
					</div>
				</div>
			{:else if lesson.id === 'orbit' || (['motion', 'model'].includes(topic.id) && ['gravity', 'period', 'speed'].includes(lesson.id))}
				<OrbitExperiment
					{stage}
					onSave={(text) => save('实验', lesson?.title ?? topic.title, text)}
				/>
			{:else}
				<label for="observation">我的观察</label>
				<textarea
					id="observation"
					rows="3"
					bind:value={observation}
					placeholder="用自己的话写下这个小节的一个发现"
					oninput={() => (recordStatus = '')}></textarea>
				<button
					class="learn-button secondary"
					type="button"
					onclick={() => {
						if (observation.trim()) save('实验', lesson?.title ?? topic.title, observation.trim());
						else recordStatus = '先写下你的观察。';
					}}>保存观察</button
				>
			{/if}
		</div>
	{:else}
		<h2 id="mission-title">{topic.title}</h2>
		<div class="learn-body">
			<p>从第一个小节开始，也可以直接选择你感兴趣的问题。</p>
			<a class="learn-button" href={hrefForLesson(topic.lessons[0].id)}>开始第一个小节</a>
		</div>
	{/if}
	{#if recordStatus}<p class="learn-muted learn-record-status" role="status">{recordStatus}</p>{/if}
</section>
