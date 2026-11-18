<script lang="ts">
	import { onMount } from 'svelte';

	type Pipeline = { id: string; name: string; source: string; valves: string };
	type Server = { url: string; pipelines: Pipeline[] };
	let { connectionUrls = [] }: { connectionUrls?: string[] } = $props();

	const storageKey = 'admin-pipeline-settings';
	const inputClass =
		'w-full rounded-lg border border-[var(--qa-line)] bg-[var(--qa-raised)] px-3 py-2 text-sm text-[color:var(--qa-text)]';
	const buttonClass =
		'shrink-0 rounded-lg border border-[var(--qa-line)] px-3 py-2 text-sm hover:bg-[var(--qa-raised)] disabled:opacity-50';

	let servers = $state<Server[]>([]);
	let serverUrl = $state('');
	let newServer = $state('');
	let pipelineId = $state('');
	let remoteUrl = $state('');
	let file = $state<File | null>(null);
	let notice = $state('');

	const urls = $derived([...new Set([...connectionUrls, ...servers.map(({ url }) => url)])]);
	const server = $derived(servers.find(({ url }) => url === serverUrl));
	const pipeline = $derived(server?.pipelines.find(({ id }) => id === pipelineId));

	onMount(() => {
		try {
			const saved = JSON.parse(localStorage.getItem(storageKey) ?? '[]');
			if (Array.isArray(saved)) servers = saved;
		} catch {
			notice = '无法读取本地管道配置。';
		}
	});

	function addServer(event: SubmitEvent) {
		event.preventDefault();
		const url = newServer.trim();
		if (!url) return;
		if (!servers.some((entry) => entry.url === url)) servers.push({ url, pipelines: [] });
		serverUrl = url;
		pipelineId = '';
		newServer = '';
	}

	function addPipeline(name: string, source: string) {
		if (!serverUrl) return;
		const id = crypto.randomUUID();
		const entry = { id, name, source, valves: '{}' };
		if (server) server.pipelines.push(entry);
		else servers.push({ url: serverUrl, pipelines: [entry] });
		pipelineId = id;
		notice = '已添加到本地配置，点击「保存」保留本次修改。';
	}

	function addFile(event: SubmitEvent) {
		event.preventDefault();
		if (!file?.name.toLowerCase().endsWith('.py')) {
			notice = '请选择一个 .py 文件。';
			return;
		}
		addPipeline(file.name, '本地文件');
	}

	function addRemote(event: SubmitEvent) {
		event.preventDefault();
		let url: URL;
		try {
			url = new URL(remoteUrl.trim());
			if (
				url.origin !== 'https://raw.githubusercontent.com' ||
				!url.pathname.toLowerCase().endsWith('.py') ||
				url.username ||
				url.password
			)
				throw new Error();
		} catch {
			notice = '请输入指向 .py 文件的 GitHub Raw HTTPS 地址。';
			return;
		}
		addPipeline(url.pathname.split('/').at(-1) ?? '管道', url.origin + url.pathname);
		remoteUrl = '';
	}

	function removePipeline() {
		if (!server || !pipeline) return;
		server.pipelines = server.pipelines.filter(({ id }) => id !== pipelineId);
		pipelineId = '';
	}

	function save() {
		for (const entry of servers) {
			for (const item of entry.pipelines) {
				try {
					const value = JSON.parse(item.valves);
					if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
				} catch {
					notice = '「' + item.name + '」的 Valve 参数需要填写为 JSON 对象。';
					return;
				}
			}
		}
		try {
			localStorage.setItem(storageKey, JSON.stringify(servers));
			notice = '管道配置已保存到当前浏览器。';
		} catch {
			notice = '无法保存管道配置，请检查浏览器存储设置。';
		}
	}
</script>

<div class="space-y-5 pb-5 text-sm">
	<header class="pt-2">
		<h2 class="text-base font-semibold">管理管道</h2>
		<p class="mt-1 text-xs text-gray-400">
			当前为本地配置。添加文件或 GitHub 地址只记录来源，管道服务器尚未接入。
		</p>
	</header>

	<section class="space-y-4 rounded-xl border border-[var(--qa-line)] bg-[var(--qa-panel)] p-4">
		<label class="grid gap-1">
			<span>管道服务</span>
			<select class={inputClass} bind:value={serverUrl} onchange={() => (pipelineId = '')}>
				<option value="">选择管道服务地址</option>
				{#each urls as url (url)}
					<option value={url}>{url}</option>
				{/each}
			</select>
		</label>
		<form class="flex items-end gap-2" onsubmit={addServer}>
			<label class="grid min-w-0 flex-1 gap-1"
				>新增服务地址<input
					class={inputClass}
					type="url"
					placeholder="http://localhost:9099"
					required
					bind:value={newServer}
				/></label
			>
			<button class={buttonClass} type="submit">添加</button>
		</form>

		{#if serverUrl}
			<form class="flex flex-wrap items-end gap-2" onsubmit={addFile}>
				<label class="grid min-w-0 flex-1 gap-1"
					>管道文件（.py）<input
						class={inputClass}
						type="file"
						accept=".py"
						required
						onchange={(event) => (file = event.currentTarget.files?.[0] ?? null)}
					/></label
				>
				<button class={buttonClass} type="submit">记录文件</button>
			</form>
			<form class="flex items-end gap-2" onsubmit={addRemote}>
				<label class="grid min-w-0 flex-1 gap-1"
					>GitHub 管道来源<input
						class={inputClass}
						type="url"
						placeholder="GitHub Raw URL"
						required
						bind:value={remoteUrl}
					/></label
				>
				<button class={buttonClass} type="submit">记录地址</button>
			</form>
		{/if}
	</section>

	<section class="space-y-4 rounded-xl border border-[var(--qa-line)] bg-[var(--qa-panel)] p-4">
		<h3 class="font-medium">管道参数（Valves）</h3>
		{#if server?.pipelines.length}
			<label class="grid gap-1">
				<span>选择管道</span>
				<select class={inputClass} bind:value={pipelineId}>
					<option value="">选择管道</option>
					{#each server.pipelines as entry (entry.id)}
						<option value={entry.id}>{entry.name}</option>
					{/each}
				</select>
			</label>
			{#if pipeline}
				<p class="text-xs break-all text-gray-400">来源：{pipeline.source}</p>
				<label class="grid gap-1"
					>Valve 参数（JSON）<textarea class={inputClass} rows="6" bind:value={pipeline.valves}
					></textarea></label
				>
				<button class={buttonClass} type="button" onclick={removePipeline}>移除本地记录</button>
			{/if}
		{:else}
			<p class="text-xs text-gray-400">所选服务暂无本地管道记录。</p>
		{/if}
	</section>
	<div class="flex flex-wrap items-center justify-end gap-3">
		<p role="status" class="text-xs text-gray-400">{notice}</p>
		<button
			type="button"
			onclick={save}
			class="rounded-lg bg-[var(--qa-active)] px-4 py-2 font-medium text-[color:var(--qa-on-active)]"
			>保存</button
		>
	</div>
</div>
