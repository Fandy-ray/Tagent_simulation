<script lang="ts">
	import { onMount } from 'svelte';
	import Switch from '$lib/components/common/Switch.svelte';

	const storageKey = 'admin-code-execution-settings';
	const inputClass = 'w-full rounded-lg border border-[var(--qa-line)] bg-[var(--qa-raised)] px-3 py-2 text-sm text-[color:var(--qa-text)]';
	const defaults = { enabled: false, engine: 'pyodide', url: '', auth: '', timeout: 60 };
	const sections = [
		{ id: 'execution', title: '代码执行' },
		{ id: 'interpreter', title: '代码解释器' }
	] as const;

	let execution = $state({ ...defaults });
	let interpreter = $state({ ...defaults });
	let promptTemplate = $state('');
	let credentials = $state({ execution: { token: '', password: '' }, interpreter: { token: '', password: '' } });
	let notice = $state('');

	onMount(() => {
		try {
			const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
			if (!saved) return;
			execution = { ...defaults, ...saved.execution };
			interpreter = { ...defaults, ...saved.interpreter };
			promptTemplate = saved.promptTemplate ?? '';
		} catch {
			notice = '本地配置无法读取，已使用默认值。';
		}
	});

	function save(event: SubmitEvent) {
		event.preventDefault();
		try {
			localStorage.setItem(storageKey, JSON.stringify({ execution, interpreter, promptTemplate }));
			notice = '配置已保存到当前浏览器。令牌和密码仅保留在当前页面。';
		} catch {
			notice = '无法保存配置，请检查浏览器的存储设置。';
		}
	}
</script>

<form class="space-y-5 pb-5 text-sm" onsubmit={save}>
	<header class="pt-2">
		<h2 class="text-base font-semibold">代码执行</h2>
		<p class="mt-1 text-xs text-gray-400">配置保存在当前浏览器，答疑服务暂未接入代码执行或解释器。</p>
	</header>

	{#each sections as section (section.id)}
		{@const config = section.id === 'execution' ? execution : interpreter}
		{@const secret = credentials[section.id]}
		<section class="space-y-4 rounded-xl border border-[var(--qa-line)] bg-[var(--qa-panel)] p-4">
			<h3 class="font-medium">{section.id === 'execution' ? '常规' : section.title}</h3>
			<div class="flex items-center justify-between gap-3">
				<span id={'enable-code-' + section.id}>启用{section.title}</span>
				<Switch ariaLabelledbyId={'enable-code-' + section.id} bind:state={config.enabled} />
			</div>

			{#if config.enabled}
				<label class="grid gap-1">
					<span>{section.title}引擎</span>
					<select class={inputClass} bind:value={config.engine}>
						<option value="pyodide">Pyodide</option>
						<option value="jupyter">Jupyter（旧版）</option>
					</select>
				</label>
				{#if config.engine === 'pyodide'}
					<p class="text-xs text-gray-400">Pyodide 可在浏览器中运行 Python。</p>
				{:else if config.engine === 'jupyter'}
					<label class="grid gap-1">
						<span>Jupyter URL</span>
						<input class={inputClass} type="url" placeholder="http://localhost:8888" bind:value={config.url} />
					</label>
					<label class="grid gap-1">
						<span>Jupyter 认证方式</span>
						<select class={inputClass} bind:value={config.auth}>
							<option value="">无</option>
							<option value="token">令牌</option>
							<option value="password">密码</option>
						</select>
					</label>
					{#if config.auth === 'token'}
						<label class="grid gap-1">Jupyter 令牌<input class={inputClass} type="password" autocomplete="off" bind:value={secret.token} /></label>
					{:else if config.auth === 'password'}
						<label class="grid gap-1">Jupyter 密码<input class={inputClass} type="password" autocomplete="new-password" bind:value={secret.password} /></label>
					{/if}
					<label class="grid gap-1">执行超时（秒）<input class={inputClass} type="number" min="1" required bind:value={config.timeout} /></label>
				{/if}
				{#if section.id === 'interpreter'}
					<label class="grid gap-1">
						<span>代码解释器提示词模板</span>
						<textarea class={inputClass} rows="5" placeholder="留空使用默认模板" bind:value={promptTemplate}></textarea>
					</label>
				{/if}
			{/if}
		</section>
	{/each}

	<div class="flex flex-wrap items-center justify-end gap-3">
		<p role="status" class="text-xs text-gray-400">{notice}</p>
		<button type="submit" class="rounded-lg bg-[var(--qa-active)] px-4 py-2 font-medium text-[color:var(--qa-on-active)]">保存</button>
	</div>
</form>
