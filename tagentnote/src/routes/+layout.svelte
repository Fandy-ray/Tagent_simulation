<script lang="ts">
	import { onMount } from 'svelte';

	import '../app.css';
	import '$lib/styles/space-theme.css';
	import { page } from '$app/state';
	import SpaceAssistant from '$lib/components/space/SpaceAssistant.svelte';
	import { learningContext, spaceTopics, stageKeys } from '$lib/data/spaceLearning';

	const context = $derived.by(() => {
		const params = page.url.searchParams;
		if (page.route.id === '/qa' || page.route.id === '/exam') return learningContext(params);
		if (page.route.id !== '/space-exploration/learn/[stage]') return null;
		const stage = stageKeys.find((key) => key === page.params.stage);
		if (!stage) return null;
		const topic = spaceTopics[stage].find(({ id }) => id === params.get('topic'));
		return { stage, topic, lesson: topic?.lessons.find(({ id }) => id === params.get('lesson')) };
	});
	const hasAssistant = $derived(
		page.route.id?.startsWith('/space-exploration') || Boolean(context)
	);

	import { initI18n, setI18nContext } from '$lib/i18n';
	import { loadUserSettings } from '$lib/data/userSettings';

	// 初始化 i18n 并设置 context（在组件初始化时同步执行）。
	// 默认语言取设置里的（默认简体中文），不按浏览器语言猜：页面上大量文字本来就是写死的中文，
	// 英文系统的电脑上按浏览器猜成英文，就会一半中文一半英文。学生在设置里改了语言照样生效。
	initI18n(loadUserSettings().language || 'zh-CN');
	setI18nContext();

	let { children } = $props();

	// 断网时顶部一条提示：学生知道是网的问题，也知道已经写的东西没丢（压测 F4）
	let online = $state(true);

	onMount(() => {
		const update = () => (online = navigator.onLine);
		update();
		window.addEventListener('online', update);
		window.addEventListener('offline', update);
		return () => {
			window.removeEventListener('online', update);
			window.removeEventListener('offline', update);
		};
	});
</script>

<svelte:head>
	<meta name="description" content="TAgent 系统建模与仿真智能教学平台" />
</svelte:head>

{#if !online}
	<div
		role="status"
		class="fixed inset-x-0 top-0 z-[100] bg-amber-400 px-4 py-1.5 text-center text-xs font-medium text-gray-950 shadow"
	>
		网络已断开：已经写的内容都还在，恢复连接后再继续。
	</div>
{/if}

{@render children()}

{#if hasAssistant}
	<SpaceAssistant
		stage={context?.stage}
		topic={context?.topic?.title}
		topicId={context?.topic?.id}
		lesson={context?.lesson?.title}
		lessonId={context?.lesson?.id}
		preferredModel={page.url.searchParams.get('model') ?? undefined}
	/>
{/if}
