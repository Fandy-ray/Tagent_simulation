<script lang="ts">
	import { goto, replaceState } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/stores';

	import ExamShell from '$lib/components/quiz/ExamShell.svelte';
	import { type ExamMode } from '$lib/data/exam';

	const modelId = $derived($page.url.searchParams.get('model') ?? '');
	const initialTopic = $derived($page.url.searchParams.get('topic') ?? '');

	// ?mode= 只预选模式卡，不代表已经开跑（见 ExamShell 里 running 的注释）
	const initialMode = $derived<ExamMode>(
		$page.url.searchParams.get('mode') === 'full' ? 'full' : 'flash'
	);

	// 这里只放路径，跳转时再 resolve 一次（原来这里和跳转处各 resolve 一次，配了 base 路径就会加两遍前缀）
	const returnPath = $derived(
		$page.url.searchParams.get('from') === 'qa'
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
<div class="h-[100dvh] w-full bg-gray-900 text-gray-100">
	<ExamShell
		fullPage={true}
		{modelId}
		{initialTopic}
		{initialMode}
		onModeChange={rememberMode}
		onLeave={() => goto(resolve(returnPath))}
	/>
</div>
