<script lang="ts">
	import { onMount } from 'svelte';
	import Switch from '$lib/components/common/Switch.svelte';

	type Field = { id: string; label: string; type?: 'password' | 'textarea'; options?: string[] };
	const engines = {
		openai: 'OpenAI（默认）',
		comfyui: 'ComfyUI',
		automatic1111: 'Automatic1111',
		gemini: 'Gemini'
	};
	type Engine = keyof typeof engines;
	const address: Field = { id: 'url', label: '服务地址' };
	const key: Field = { id: 'key', label: 'API Key', type: 'password' };
	const version: Field = { id: 'version', label: 'API 版本' };
	const params: Field = { id: 'params', label: '额外请求参数（JSON）', type: 'textarea' };

	function providerFields(engine: Engine, generation: boolean): Field[] {
		switch (engine) {
			case 'openai':
				return generation ? [address, key, version, params] : [address, key, version];
			case 'automatic1111':
				return [address, { id: 'auth', label: 'API 认证（用户名:密码）', type: 'password' }, params];
			case 'comfyui':
				return [
					address, key,
					{ id: 'workflow', label: 'ComfyUI 工作流（API 格式 JSON）', type: 'textarea' },
					{ id: 'nodes', label: '工作流节点映射（字段与节点 ID，JSON）', type: 'textarea' }
				];
			case 'gemini':
				return generation
					? [address, key, { id: 'method', label: '端点方法', options: ['predict', 'generateContent'] }]
					: [address, key];
		}
	}

	const sections = [
		{ id: 'generation', label: '图像生成', engines: ['openai', 'comfyui', 'automatic1111', 'gemini'] },
		{ id: 'edit', label: '图像编辑', engines: ['openai', 'comfyui', 'gemini'] }
	] as const;
	const defaults = { enabled: false, engine: 'openai' as Engine, model: '', size: '1024x1024' };
	const storageKey = 'admin-image-settings';
	const inputClass = 'w-full rounded-lg border border-[var(--qa-line)] bg-[var(--qa-raised)] px-3 py-2 text-sm text-[color:var(--qa-text)]';
	let generation = $state({ ...defaults });
	let edit = $state({ ...defaults });
	let steps = $state(20);
	let generatePrompt = $state(false);
	let options = $state<Record<string, string>>({});
	let secrets = $state<Record<string, string>>({});
	let notice = $state('');

	onMount(() => {
		try {
			const saved = JSON.parse(localStorage.getItem(storageKey) ?? '{}');
			generation = { ...defaults, ...saved.generation };
			edit = { ...defaults, ...saved.edit };
			if (!sections[0].engines.some((engine) => engine === generation.engine)) generation.engine = 'openai';
			if (!sections[1].engines.some((engine) => engine === edit.engine)) edit.engine = 'openai';
			steps = saved.steps ?? 20;
			generatePrompt = saved.generatePrompt ?? false;
			options = saved.options ?? {};
		} catch {
			notice = '无法读取本地配置。';
		}
	});

	function save(event: SubmitEvent) {
		event.preventDefault();
		for (const section of sections) {
			const config = section.id === 'generation' ? generation : edit;
			if (!config.enabled) continue;
			const prefix = section.id + ':' + config.engine + ':';
			for (const field of providerFields(config.engine, section.id === 'generation')) {
				const value = options[prefix + field.id]?.trim();
				if (field.type !== 'textarea' || !value) continue;
				try {
					JSON.parse(value);
				} catch {
					notice = section.label + '的「' + field.label + '」格式有误。';
					return;
				}
			}
		}
		try {
			localStorage.setItem(storageKey, JSON.stringify({ generation, edit, steps, generatePrompt, options }));
			notice = '图像配置已保存。密钥和认证信息仅保留在当前页面。';
		} catch {
			notice = '无法保存配置，请检查浏览器存储设置。';
		}
	}
</script>

<form class="space-y-5 pb-5 text-sm" onsubmit={save}>
	<header class="pt-2">
		<h2 class="text-base font-semibold">图像</h2>
		<p class="mt-1 text-xs text-gray-400">配置保存在当前浏览器。图像生成和编辑服务尚未接入。</p>
	</header>

	{#each sections as section (section.id)}
		{@const isGeneration = section.id === 'generation'}
		{@const config = isGeneration ? generation : edit}
		<section class="space-y-4 rounded-xl border border-[var(--qa-line)] bg-[var(--qa-panel)] p-4">
			<h3 class="font-medium">{section.label}</h3>
			<div class="flex items-center justify-between">
				<span id={'image-enable-' + section.id}>启用{section.label}</span>
				<Switch ariaLabelledbyId={'image-enable-' + section.id} bind:state={config.enabled} />
			</div>

			{#if config.enabled}
				<label class="grid gap-1">
					<span>{section.label}引擎</span>
					<select class={inputClass} bind:value={config.engine}>
						{#each section.engines as engine (engine)}
							<option value={engine}>{engines[engine]}</option>
						{/each}
					</select>
				</label>
				<div class="grid gap-3 sm:grid-cols-2">
					<label class="grid gap-1">模型<input class={inputClass} placeholder="输入模型名称或 ID" bind:value={config.model} /></label>
					<label class="grid gap-1">图像尺寸<input class={inputClass} placeholder="例如 1024x1024" bind:value={config.size} /></label>
				</div>
				{#if isGeneration}
					{#if config.engine === 'comfyui' || config.engine === 'automatic1111'}
						<label class="grid gap-1">生成步数<input class={inputClass} type="number" min="1" required bind:value={steps} /></label>
					{/if}
					<div class="flex items-center justify-between">
						<span id="image-generate-prompt">自动生成图像提示词</span>
						<Switch ariaLabelledbyId="image-generate-prompt" bind:state={generatePrompt} />
					</div>
				{/if}
				{#each providerFields(config.engine, isGeneration) as field (field.id)}
					{@const id = section.id + ':' + config.engine + ':' + field.id}
					<label class="grid gap-1">
						<span>{field.label}</span>
						{#if field.options}
							<select class={inputClass} value={options[id] ?? field.options[0]} onchange={(event) => (options[id] = event.currentTarget.value)}>
								{#each field.options as option (option)}
									<option value={option}>{option}</option>
								{/each}
							</select>
						{:else if field.type === 'textarea'}
							<textarea class={inputClass} rows="4" bind:value={options[id]}></textarea>
						{:else if field.type === 'password'}
							<input class={inputClass} type="password" autocomplete="off" bind:value={secrets[id]} />
						{:else}
							<input class={inputClass} bind:value={options[id]} />
						{/if}
					</label>
				{/each}
			{/if}
		</section>
	{/each}

	<div class="flex flex-wrap items-center justify-end gap-3">
		<p role="status" class="text-xs text-gray-400">{notice}</p>
		<button type="submit" class="rounded-lg bg-[var(--qa-active)] px-4 py-2 font-medium text-[color:var(--qa-on-active)]">保存</button>
	</div>
</form>
