<script lang="ts">
	import { onMount } from 'svelte';
	import Switch from '$lib/components/common/Switch.svelte';

	type Field = { label: string; type?: 'password' | 'url' | 'number'; options?: string[] };
	const key: Field = { label: 'API Key', type: 'password' };
	const endpoint: Field = { label: '服务地址', type: 'url' };
	const searchEngines: Record<string, Field[]> = {
		DDGS: [
			{
				label: '搜索后端',
				options: [
					'auto',
					'bing',
					'brave',
					'duckduckgo',
					'google',
					'grokipedia',
					'mojeek',
					'wikipedia',
					'yahoo',
					'yandex'
				]
			}
		],
		SearXNG: [{ label: '查询 URL 模板' }, { label: '搜索语言' }],
		YaCy: [endpoint, { label: '用户名' }, { label: '密码', type: 'password' }],
		'Google PSE': [key, { label: '搜索引擎 ID' }],
		Brave: [key],
		Kagi: [key],
		Mojeek: [key],
		Bocha: [key],
		Serpstack: [key],
		Serper: [key],
		Serply: [key],
		SearchAPI: [key, { label: '搜索引擎参数' }],
		SerpAPI: [key, { label: '搜索引擎参数' }],
		Tavily: [key],
		Jina: [endpoint, key],
		Bing: [endpoint, key],
		Exa: [key],
		'Ollama Cloud': [key],
		'Perplexity Search': [endpoint, key],
		Perplexity: [
			key,
			{
				label: '模型',
				options: [
					'sonar',
					'sonar-pro',
					'sonar-reasoning',
					'sonar-reasoning-pro',
					'sonar-deep-research'
				]
			},
			{ label: '搜索上下文大小', options: ['low', 'medium', 'high'] }
		],
		搜狗: [{ label: 'API SID' }, { label: 'API SK', type: 'password' }],
		Firecrawl: [endpoint, key, { label: '请求超时（秒）', type: 'number' }],
		外部搜索: [endpoint, key],
		Yandex: [endpoint, key, { label: '搜索配置' }],
		'You.com': [key]
	};
	const loaderEngines: Record<string, Field[]> = {
		默认: [],
		Playwright: [
			{ label: 'WebSocket 地址', type: 'url' },
			{ label: '请求超时（秒）', type: 'number' }
		],
		Firecrawl: [endpoint, key, { label: '请求超时（秒）', type: 'number' }],
		Tavily: [key, { label: '提取深度', options: ['basic', 'advanced'] }],
		外部加载器: [endpoint, key]
	};

	const storageKey = 'admin-web-search-settings';
	const inputClass =
		'w-full rounded-lg border border-[var(--qa-line)] bg-[var(--qa-raised)] px-3 py-2 text-sm text-[color:var(--qa-text)]';
	const defaults = {
		enabled: false,
		engine: 'DDGS',
		resultCount: 5,
		searchConcurrency: 4,
		domains: '',
		maxContentLength: 0,
		bypassRetrieval: false,
		bypassLoader: false,
		trustEnvironment: false,
		loader: '默认',
		loaderTimeout: 10,
		verifySsl: true,
		loaderConcurrency: 4,
		youtubeLanguage: '',
		youtubeProxy: ''
	};
	let config = $state({ ...defaults });
	let options = $state<Record<string, string>>({});
	let secrets = $state<Record<string, string>>({});
	let notice = $state('');

	onMount(() => {
		try {
			const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
			if (!saved) return;
			config = { ...defaults, ...saved.config };
			options = saved.options ?? {};
		} catch {
			notice = '本地配置无法读取，已使用默认值。';
		}
	});

	function save(event: SubmitEvent) {
		event.preventDefault();
		try {
			localStorage.setItem(storageKey, JSON.stringify({ config, options }));
			notice = '配置已保存到当前浏览器。密钥仅保留在当前页面。';
		} catch {
			notice = '无法保存配置，请检查浏览器的存储设置。';
		}
	}
</script>

{#snippet engineFields(fields: Field[], scope: string)}
	{#each fields as field (field.label)}
		{@const id = scope + ':' + field.label}
		<label class="grid gap-1">
			<span>{field.label}</span>
			{#if field.options}
				<select class={inputClass} bind:value={options[id]}>
					<option value="">请选择</option>
					{#each field.options as option (option)}
						<option value={option}>{option}</option>
					{/each}
				</select>
			{:else if field.type === 'password'}
				<input class={inputClass} type="password" autocomplete="off" bind:value={secrets[id]} />
			{:else}
				<input class={inputClass} type={field.type ?? 'text'} bind:value={options[id]} />
			{/if}
		</label>
	{/each}
{/snippet}

<form class="space-y-5 pb-5 text-sm" onsubmit={save}>
	<header class="pt-2">
		<h2 class="text-base font-semibold">网页搜索</h2>
		<p class="mt-1 text-xs text-gray-400">配置保存在当前浏览器，答疑服务暂未接入网页搜索。</p>
	</header>

	<section class="space-y-4 rounded-xl border border-[var(--qa-line)] bg-[var(--qa-panel)] p-4">
		<h3 class="font-medium">常规</h3>
		<div class="flex items-center justify-between gap-3">
			<span id="web-search-enable">启用网页搜索</span>
			<Switch ariaLabelledbyId="web-search-enable" bind:state={config.enabled} />
		</div>
		{#if config.enabled}
			<label class="grid gap-1">
				<span>搜索引擎</span>
				<select class={inputClass} bind:value={config.engine}>
					{#each Object.keys(searchEngines) as engine (engine)}
						<option value={engine}>{engine}</option>
					{/each}
				</select>
			</label>
			{@render engineFields(searchEngines[config.engine] ?? [], 'search:' + config.engine)}
			<div class="grid gap-3 sm:grid-cols-2">
				<label class="grid gap-1"
					>搜索结果数量<input
						class={inputClass}
						type="number"
						min="1"
						required
						bind:value={config.resultCount}
					/></label
				>
				<label class="grid gap-1"
					>搜索并发请求数<input
						class={inputClass}
						type="number"
						min="1"
						required
						bind:value={config.searchConcurrency}
					/></label
				>
				<label class="grid gap-1"
					>网页内容长度上限（0 表示不限）<input
						class={inputClass}
						type="number"
						min="0"
						required
						bind:value={config.maxContentLength}
					/></label
				>
				<label class="grid gap-1"
					>域名过滤列表<input
						class={inputClass}
						placeholder="多个域名用逗号分隔"
						bind:value={config.domains}
					/></label
				>
			</div>
			{#each Object.entries( { bypassRetrieval: '跳过嵌入与检索', bypassLoader: '跳过网页加载器', trustEnvironment: '使用环境代理配置' } as const ) as [field, label] (field)}
				<div class="flex items-center justify-between gap-3">
					<span id={'web-search-' + field}>{label}</span>
					<Switch
						ariaLabelledbyId={'web-search-' + field}
						bind:state={config[field as 'bypassRetrieval' | 'bypassLoader' | 'trustEnvironment']}
					/>
				</div>
			{/each}
		{/if}
	</section>

	<section class="space-y-4 rounded-xl border border-[var(--qa-line)] bg-[var(--qa-panel)] p-4">
		<h3 class="font-medium">网页加载器</h3>
		<label class="grid gap-1">
			<span>加载器引擎</span>
			<select class={inputClass} bind:value={config.loader}>
				{#each Object.keys(loaderEngines) as engine (engine)}
					<option value={engine}>{engine}</option>
				{/each}
			</select>
		</label>
		{@render engineFields(loaderEngines[config.loader] ?? [], 'loader:' + config.loader)}
		<div class="grid gap-3 sm:grid-cols-2">
			<label class="grid gap-1"
				>加载超时（秒）<input
					class={inputClass}
					type="number"
					min="1"
					required
					bind:value={config.loaderTimeout}
				/></label
			>
			<label class="grid gap-1"
				>加载并发请求数<input
					class={inputClass}
					type="number"
					min="1"
					required
					bind:value={config.loaderConcurrency}
				/></label
			>
		</div>
		<div class="flex items-center justify-between gap-3">
			<span id="web-loader-ssl">验证 SSL 证书</span>
			<Switch ariaLabelledbyId="web-loader-ssl" bind:state={config.verifySsl} />
		</div>
	</section>

	<section class="space-y-4 rounded-xl border border-[var(--qa-line)] bg-[var(--qa-panel)] p-4">
		<h3 class="font-medium">YouTube 加载器</h3>
		<label class="grid gap-1"
			>字幕语言<input
				class={inputClass}
				placeholder="例如 zh,en"
				bind:value={config.youtubeLanguage}
			/></label
		>
		<label class="grid gap-1"
			>代理 URL<input class={inputClass} type="url" bind:value={config.youtubeProxy} /></label
		>
	</section>

	<div class="flex flex-wrap items-center justify-end gap-3">
		<p role="status" class="text-xs text-gray-400">{notice}</p>
		<button
			type="submit"
			class="rounded-lg bg-[var(--qa-active)] px-4 py-2 font-medium text-[color:var(--qa-on-active)]"
			>保存</button
		>
	</div>
</form>
