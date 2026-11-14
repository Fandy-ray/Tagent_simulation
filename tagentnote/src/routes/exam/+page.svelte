<script lang="ts">
	import { goto, replaceState } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/stores';

	import ExamShell from '$lib/components/quiz/ExamShell.svelte';
	import { learningContext, spaceStages } from '$lib/data/spaceLearning';
	import { saveSpaceRecord } from '$lib/data/spaceRecords';
	import { type ExamMode } from '$lib/data/exam';

	const exploration = $derived(learningContext($page.url.searchParams));
	let recordMessage = $state('');
	function recordResult(score: number, examId: string) {
		if (!exploration) return;
		const { stage, topic } = exploration;
		try {
			saveSpaceRecord({
				id: `exam/${stage}/${topic.id}/${examId}`,
				kind: '测评',
				title: topic.title,
				context: spaceStages[stage].label,
				content: `整卷得分 ${score} 分。`
			});
			recordMessage = '整卷成绩已存入我的笔记本。';
		} catch {
			recordMessage = '无法保存整卷成绩，请检查浏览器存储设置。';
		}
	}

	const modelId = $derived($page.url.searchParams.get('model') ?? '');
	const initialTopic = $derived($page.url.searchParams.get('topic') ?? '');

	// ?mode= 只预选模式卡，不代表已经开跑（见 ExamShell 里 running 的注释）
	const initialMode = $derived<ExamMode>(
		exploration || $page.url.searchParams.get('mode') === 'full' ? 'full' : 'flash'
	);

	// 这里只放路径，跳转时再 resolve 一次（原来这里和跳转处各 resolve 一次，配了 base 路径就会加两遍前缀）
	const returnPath = $derived(
		exploration
			? `/space-exploration/learn/${exploration.stage}?topic=${exploration.topic.id}&lesson=review`
			: $page.url.searchParams.get('from') === 'qa'
				? `/qa?model=${encodeURIComponent(modelId)}`
				: '/agent-select'
	);

	// 只是把选择记在地址栏里，不触发导航：用浅路由的 replaceState，
	// 免得 goto 白跑一遍 load、还把焦点和滚动位置重置掉。
	const rememberMode = (mode: ExamMode) => {
		const url = new URL($page.url);
		url.searchParams.set('mode', mode);
		replaceState(resolve(`/exam?${url.searchParams.toString()}`), $page.state);
	};
</script>

<svelte:head>
	<title>智能测评 | TAgent</title>
</svelte:head>

<!-- 和答疑页一样整页铺满、不套外框；离开这一页的 ‹ 在 ExamShell 顶栏里（停在首屏时） -->
<div
	class:space-exam={Boolean(exploration)}
	class="relative h-[100dvh] w-full bg-gray-900 text-gray-100"
>
	<ExamShell
		fullPage={true}
		spaceContext={exploration ? `${exploration.stage}/${exploration.topic.id}` : ''}
		onFullResult={recordResult}
		{modelId}
		{initialTopic}
		{initialMode}
		onModeChange={rememberMode}
		onLeave={() => goto(resolve(returnPath))}
	/>
	{#if recordMessage}<p
			class="bg-gray-850 pointer-events-none absolute right-4 bottom-3 z-10 rounded-lg p-2 text-sm"
			role="status"
		>
			{recordMessage}
		</p>{/if}
</div>
