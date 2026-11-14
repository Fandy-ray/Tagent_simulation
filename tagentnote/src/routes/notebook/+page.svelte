<script lang="ts">
	import '$lib/styles/space-theme.css';
	import OrbitMark from '$lib/components/icons/OrbitMark.svelte';
	import { resolve } from '$app/paths';
	import { page } from '$app/stores';
	import { env } from '$env/dynamic/public';
	import { onMount } from 'svelte';
	import { SvelteURLSearchParams } from 'svelte/reactivity';

	import { listNotebookKnowledge, listNotebooks } from '$lib/apis/opennotebook';
	import { findCollection, type KnowledgeCollection } from '$lib/data/knowledge';

	const DEFAULT_NOTEBOOK_URL = 'http://localhost:8502/notebooks';

	const normalizeNotebookUrl = (raw: string) => {
		const trimmed = raw.trim().replace(/\/$/, '');

		if (trimmed === 'http://localhost:8502' || trimmed === 'https://localhost:8502') {
			return `${trimmed}/notebooks`;
		}

		return raw.trim() || DEFAULT_NOTEBOOK_URL;
	};

	const openNotebookUrl = normalizeNotebookUrl(env.PUBLIC_OPENNOTEBOOK_URL || DEFAULT_NOTEBOOK_URL);

	let iframeKey = $state(0);
	let status = $state<'checking' | 'ready' | 'offline'>('checking');
	let serviceUp = $state(false);
	let section = $state<'notebooks' | 'sources'>('notebooks');
	let collections = $state<KnowledgeCollection[]>([]);

	const sourcesUrl = $derived.by(() => {
		const url = new URL(openNotebookUrl, $page.url);
		const path = url.pathname.replace(/\/$/, '');
		if (path && !path.endsWith('/notebooks')) return null;
		url.pathname = path ? path.slice(0, -'notebooks'.length) + 'sources' : '/sources';
		url.search = '';
		url.hash = '';
		return url.href;
	});
	const frameUrl = $derived(section === 'sources' && sourcesUrl ? sourcesUrl : openNotebookUrl);

	const sourceFile = $derived($page.url.searchParams.get('file'));
	const sourceCollection = $derived(
		findCollection($page.url.searchParams.get('collection') ?? '', collections)
	);
	const sourceFileTitle = $derived(
		sourceCollection?.files.find((file) => file.id === sourceFile)?.title ?? sourceFile
	);

	const returnPath = $derived.by(() => {
		const from = $page.url.searchParams.get('from');
		const model = $page.url.searchParams.get('model') ?? '';
		const notebook = $page.url.searchParams.get('notebook') ?? '';
		const chat = $page.url.searchParams.get('chat') ?? '';
		const mode = $page.url.searchParams.get('mode') ?? '';

		if (from === 'qa') {
			const params = new SvelteURLSearchParams();
			if (model) params.set('model', model);
			if (notebook) params.set('notebook', notebook);
			if (chat) params.set('chat', chat);
			if (mode === 'paper') params.set('mode', 'paper');
			const search = params.toString();
			return search ? `/qa?${search}` : '/qa';
		}

		if (from === 'workspace') {
			const params = new SvelteURLSearchParams();
			if (model) params.set('model', model);
			if (chat) params.set('chat', chat);
			const search = params.toString();
			return search ? `/workspace/knowledge?${search}` : '/workspace/knowledge';
		}

		if (from === 'exam') {
			return `/exam?model=${encodeURIComponent(model)}`;
		}

		return '/agent-select';
	});

	const returnLabel = $derived(
		$page.url.searchParams.get('from') === 'qa'
			? '返回答疑'
			: $page.url.searchParams.get('from') === 'workspace'
				? '返回工作空间'
				: $page.url.searchParams.get('from') === 'exam'
					? '返回测评'
					: '返回学习入口'
	);

	const checkNotebook = async () => {
		status = 'checking';
		try {
			const origin = new URL(openNotebookUrl, window.location.origin).origin;
			await fetch(origin, { mode: 'no-cors', signal: AbortSignal.timeout(2500) });
			status = 'ready';
		} catch {
			status = 'offline';
		}
	};

	const refresh = () => {
		if (status === 'checking') return;
		section = 'notebooks';
		iframeKey += 1;
		void checkNotebook();
	};

	const openSources = () => {
		section = 'sources';
		iframeKey += 1;
	};

	onMount(() => {
		const controller = new AbortController();
		void checkNotebook();
		const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]);
		if ($page.url.searchParams.has('collection')) {
			void listNotebookKnowledge(signal)
				.then((items) => {
					collections = items;
					serviceUp = true;
				})
				.catch(() => {});
		} else {
			void listNotebooks(signal)
				.then(() => (serviceUp = true))
				.catch(() => {});
		}
		return () => controller.abort();
	});
</script>

<svelte:head>
	<title>知识笔记本 | TAgent</title>
</svelte:head>

<div class="space-theme notebook-page">
	<header class="topbar">
		<a class="brand" href={resolve('/space-exploration')}>
			<span class="brand-mark"><OrbitMark /></span>
			<span>知识笔记本</span>
		</a>

		<nav aria-label="笔记本工作区">
			<a class="button" href={resolve(returnPath)}>{returnLabel}</a>
			{#if sourcesUrl}
				<button
					type="button"
					class="button sources"
					onclick={openSources}
					disabled={status !== 'ready'}>来源</button
				>
			{/if}
			<button type="button" class="button" onclick={refresh} disabled={status === 'checking'}
				>刷新</button
			>
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- configured OpenNotebook URL -->
			<a class="button external" href={openNotebookUrl} target="_blank" rel="noreferrer"
				>新页面打开</a
			>
		</nav>
	</header>

	{#if sourceCollection}
		<p class="source-context">
			笔记本 <strong>{sourceCollection.name}</strong>
			{#if sourceFileTitle}
				· {sourceFileTitle}{/if}
		</p>
	{/if}

	<main>
		{#key iframeKey}
			<iframe
				title="OpenNotebook 知识工作区"
				src={frameUrl}
				allow="clipboard-read; clipboard-write"
				class:hidden={status !== 'ready'}
			></iframe>
		{/key}

		{#if status === 'checking'}
			<div class="state" role="status">正在连接 OpenNotebook…</div>
		{:else if status === 'offline'}
			<div class="state">
				<div>
					<h1>{serviceUp ? '暂时无法打开笔记本工作区' : '无法连接 OpenNotebook'}</h1>
					<p>
						{serviceUp
							? '笔记本接口仍可用，请检查工作区地址后重试。'
							: '请启动 OpenNotebook 服务，然后重试。'}
					</p>
					<code>{openNotebookUrl}</code>
					<button type="button" class="button sources" onclick={refresh}>重新连接</button>
				</div>
			</div>
		{/if}
	</main>
</div>

<style>
	.notebook-page {
		display: flex;
		flex-direction: column;
		height: 100dvh;
		background: var(--m3-background);
		color: var(--m3-on-surface);
		color-scheme: dark;
		font-family: var(--space-font);
	}
	.topbar {
		display: flex;
		min-height: 60px;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 8px 16px;
		padding: 8px clamp(12px, 3vw, 32px);
		border-bottom: 1px solid var(--m3-outline-variant);
		background: var(--m3-surface-low);
	}
	.brand,
	nav,
	.button {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.brand {
		font-size: 15px;
		font-weight: 600;
	}
	.brand-mark {
		display: grid;
		width: 34px;
		height: 34px;
		flex: none;
		place-items: center;
		border: 1px solid color-mix(in srgb, var(--space-amber), transparent 48%);
		border-radius: 50%;
		color: var(--space-amber);
		font-size: 21px;
	}
	nav {
		flex-wrap: wrap;
	}
	.button {
		min-height: 36px;
		padding-inline: 11px;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 999px;
		font-size: 13px;
		white-space: nowrap;
	}
	.button:hover:not(:disabled) {
		background: var(--m3-surface-high);
	}
	.button:disabled {
		cursor: default;
		opacity: 0.5;
	}
	.sources {
		background: var(--m3-primary);
		color: var(--m3-on-primary);
		border-color: transparent;
	}
	.sources:hover:not(:disabled) {
		background: #e1d1ff;
	}
	.external {
		color: var(--m3-primary);
	}
	a:focus-visible,
	button:focus-visible {
		outline: 2px solid var(--m3-primary);
		outline-offset: 2px;
	}
	.source-context {
		margin: 0;
		padding: 8px 16px;
		border-bottom: 1px solid var(--m3-outline-variant);
		color: var(--m3-on-surface-variant);
		font-size: 13px;
		overflow-wrap: anywhere;
	}
	.source-context strong {
		color: var(--m3-primary);
	}
	main {
		display: grid;
		min-height: 0;
		flex: 1;
	}
	iframe {
		display: block;
		width: 100%;
		height: 100%;
		border: 0;
	}
	iframe.hidden {
		display: none;
	}
	.state {
		display: grid;
		place-items: center;
		padding: 24px;
	}
	.state > div {
		display: grid;
		justify-items: start;
		gap: 12px;
	}
	.state h1 {
		font-size: 22px;
		font-weight: 600;
	}
	.state p,
	code {
		color: var(--m3-on-surface-variant);
		overflow-wrap: anywhere;
	}
	@media (max-width: 610px) {
		.topbar {
			gap: 6px;
		}
		nav {
			gap: 4px;
		}
		.button {
			padding-inline: 7px;
			font-size: 12px;
		}
	}
</style>
