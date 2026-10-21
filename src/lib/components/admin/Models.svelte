<script lang="ts">
	import type { WorkspaceModel } from '$lib/data/workspaceResources';
	import { listModels, upsertModel } from '$lib/data/workspaceResources';
	import ModelEditor from '$lib/components/workspace/Models/ModelEditor.svelte';

	let models = $state<WorkspaceModel[]>(listModels());
	let search = $state('');
	let filter = $state('all');
	let selectedId = $state<string | null>(null);
	let notice = $state('');
	let showManageModal = $state(false);
	let showSettingsModal = $state(false);
	let manageUrl = $state('http://localhost:11434');
	let availableOllamaUrls = $state(['http://localhost:11434']);
	let ollamaModels = $state<string[]>(['llama3.2:latest', 'mistral:7b', 'qwen2.5:latest']);
	let downloadTag = $state('');
	let createTag = $state('');
	let createJson = $state('');
	let deleteTag = $state('');
	let showExperimental = $state(false);
	let settingsTab = $state<'defaults' | 'display'>('defaults');
	let selectedDefaultModels = $state<string[]>([]);
	let pinnedModels = $state<string[]>([]);
	let orderedModelIds = $state<string[]>([]);
	let promptSuggestionsOpen = $state(false);
	let capabilitiesOpen = $state(false);
	let paramsOpen = $state(false);
	let promptSuggestions = $state<{ title: string; content: string }[]>([]);
	let modelCapabilities = $state<Record<string, boolean>>({ vision: true, file_upload: true, file_context: true, web_search: true, image_generation: true, code_interpreter: true, citations: true, status_updates: true, builtin_tools: true, usage: false });
	let modelParams = $state<Record<string, string>>({ temperature: '', top_p: '', max_tokens: '', seed: '' });
	let loadedMockSettings = false;


	const filters = [
		{ id: 'all', label: '全部' },
		{ id: 'enabled', label: '已启用' },
		{ id: 'disabled', label: '已停用' },
		{ id: 'visible', label: '可见' },
		{ id: 'hidden', label: '已隐藏' },
		{ id: 'public', label: '公开' },
		{ id: 'private', label: '私有' }
	];
	let filteredModels = $derived(models
		.filter((model) => model.name.toLowerCase().includes(search.trim().toLowerCase()) || model.id.toLowerCase().includes(search.trim().toLowerCase()))
		.filter((model) => filter === 'all' || (filter === 'enabled' ? model.isActive !== false : filter === 'disabled' ? model.isActive === false : filter === 'hidden' ? model.meta?.hidden === true : filter === 'visible' ? model.meta?.hidden !== true : filter === 'public' ? model.owner === 'shared' : model.owner !== 'shared'))
		.sort((a, b) => a.name.localeCompare(b.name)));

	const inform = (message: string) => {
		notice = message;
		setTimeout(() => notice = '', 2200);
	};

	const loadModelSettings = () => {
		if (loadedMockSettings || typeof localStorage === 'undefined') return;
		loadedMockSettings = true;
		try {
			const saved = JSON.parse(localStorage.getItem('admin-model-settings-mock') || '{}');
			selectedDefaultModels = saved.selectedDefaultModels ?? [];
			pinnedModels = saved.pinnedModels ?? [];
			orderedModelIds = saved.orderedModelIds ?? models.map((model) => model.id);
			promptSuggestions = saved.promptSuggestions ?? [];
			modelCapabilities = { ...modelCapabilities, ...(saved.modelCapabilities ?? {}) };
			modelParams = { ...modelParams, ...(saved.modelParams ?? {}) };
			ollamaModels = saved.ollamaModels ?? ollamaModels;
			availableOllamaUrls = saved.availableOllamaUrls ?? availableOllamaUrls;
		} catch {
			inform('读取本地模型设置失败');
		}
	};

	const persistModelSettings = () => {
		localStorage.setItem('admin-model-settings-mock', JSON.stringify({ selectedDefaultModels, pinnedModels, orderedModelIds, promptSuggestions, modelCapabilities, modelParams, ollamaModels, availableOllamaUrls }));
	};

	const toggleSelection = (ids: string[], id: string) => ids.includes(id) ? ids.filter((entry) => entry !== id) : [...ids, id];

	const mockPullModel = () => {
		const tag = downloadTag.trim().replace(/^ollama\\s+(run|pull)\\s+/, '');
		if (!tag) return;
		if (!ollamaModels.includes(tag)) ollamaModels = [...ollamaModels, tag];
		downloadTag = '';
		persistModelSettings();
		inform(`已添加模型 ${tag}（本地 mock）`);
	};

	const mockCreateModel = () => {
		const tag = createTag.trim();
		if (!tag || !createJson.trim()) return;
		try {
			JSON.parse(createJson);
			if (!ollamaModels.includes(tag)) ollamaModels = [...ollamaModels, tag];
			createTag = '';
			createJson = '';
			persistModelSettings();
			inform(`已创建模型 ${tag}（本地 mock）`);
		} catch {
			inform('模型配置必须是有效的 JSON');
		}
	};

	const mockDeleteModel = () => {
		if (!deleteTag) return;
		ollamaModels = ollamaModels.filter((tag) => tag !== deleteTag);
		deleteTag = '';
		persistModelSettings();
		inform('模型已删除（本地 mock）');
	};

	const saveModelSettings = () => {
		persistModelSettings();
		inform('模型配置已保存（本地 mock）');
		showSettingsModal = false;
	};

	$effect(() => {
		if (showManageModal || showSettingsModal) loadModelSettings();
	});


	const saveModel = (model: WorkspaceModel) => {
		upsertModel(model);
		models = listModels();
		selectedId = null;
		inform('模型已保存（本地 mock）');
	};

	const setActiveForFiltered = (active: boolean) => {
		for (const model of filteredModels) upsertModel({ ...model, isActive: active });
		models = listModels();
		inform(active ? '已启用筛选模型' : '已停用筛选模型');
	};

	const setHiddenForFiltered = (hidden: boolean) => {
		for (const model of filteredModels) upsertModel({ ...model, meta: { ...model.meta, hidden } });
		models = listModels();
		inform(hidden ? '已隐藏筛选模型' : '已显示筛选模型');
	};

	const exportModels = () => {
		const blob = new Blob([JSON.stringify(models, null, 2)], { type: 'application/json' });
		const link = document.createElement('a');
		link.href = URL.createObjectURL(blob);
		link.download = `models-export-${Date.now()}.json`;
		link.click();
		URL.revokeObjectURL(link.href);
	};

	const importModels = (event: Event) => {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		const reader = new FileReader();
		reader.onload = () => {
			try {
				const imported = JSON.parse(String(reader.result));
				if (!Array.isArray(imported)) throw new Error('invalid');
				for (const model of imported) {
					if (model?.id && model?.name) upsertModel({ ...model, createdAt: model.createdAt || Date.now(), updatedAt: Date.now() });
				}
				models = listModels();
				inform('模型导入成功（本地 mock）');
			} catch {
				inform('JSON 文件格式无效');
			}
			input.value = '';
		};
		reader.readAsText(file);
	};
</script>

{#if selectedId}
	<ModelEditor edit initial={models.find((model) => model.id === selectedId) ?? null} onSave={saveModel} onBack={() => selectedId = null} />
{:else}
	<section class="min-h-full">
		<div class="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
			<div class="flex items-center gap-2 px-0.5"><h2 class="text-xl font-medium">模型</h2><span class="text-lg text-gray-500">{filteredModels.length}</span></div>
			<div class="flex flex-wrap items-center justify-end gap-1.5">
				<label class="inline-flex h-8 min-w-16 items-center justify-center rounded-xl bg-gray-100 px-3 text-xs font-medium leading-none transition hover:bg-gray-200 dark:bg-gray-850 dark:hover:bg-gray-800 cursor-pointer">导入<input class="hidden" type="file" accept=".json,application/json" onchange={importModels} /></label>
				<button class="inline-flex h-8 min-w-16 items-center justify-center rounded-xl bg-gray-100 px-3 text-xs font-medium leading-none transition hover:bg-gray-200 dark:bg-gray-850 dark:hover:bg-gray-800" type="button" onclick={exportModels}>导出</button>
				<button class="inline-flex h-8 min-w-16 items-center justify-center rounded-xl bg-gray-100 px-3 text-xs font-medium leading-none transition hover:bg-gray-200 dark:bg-gray-850 dark:hover:bg-gray-800" type="button" onclick={() => showManageModal = true}>管理</button>
				<button class="inline-flex h-8 min-w-16 items-center justify-center rounded-xl bg-gray-100 px-3 text-xs font-medium leading-none transition hover:bg-gray-200 dark:bg-gray-850 dark:hover:bg-gray-800" type="button" onclick={() => showSettingsModal = true}>设置</button>
			</div>
		</div>

		<div class="rounded-3xl border border-gray-200/70 bg-white py-2 dark:border-gray-850/50 dark:bg-gray-900">
			<div class="flex items-center gap-2 px-4 pb-2 pt-1">
				<svg class="size-4 shrink-0 text-gray-500" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M9 3.5a5.5 5.5 0 1 0 3.445 9.788l3.328 3.328a.75.75 0 1 0 1.06-1.06l-3.328-3.329A5.5 5.5 0 0 0 9 3.5ZM5 9a4 4 0 1 1 8 0 4 4 0 0 1-8 0Z" clip-rule="evenodd" /></svg>
				<input class="w-full bg-transparent py-1 text-sm outline-none" bind:value={search} placeholder="搜索模型" aria-label="搜索模型" />
				{#if search}<button type="button" class="text-gray-500" aria-label="清除搜索" onclick={() => search = ''}>×</button>{/if}
			</div>
			<div class="flex items-center gap-2 px-3 pb-1">
				<div class="relative">
					<select class="appearance-none rounded-xl bg-gray-100 py-1.5 pl-3 pr-8 text-xs font-medium outline-none transition hover:bg-gray-200 focus:ring-1 focus:ring-gray-400 dark:bg-gray-850 dark:hover:bg-gray-800" bind:value={filter} aria-label="筛选模型">
						{#each filters as option (option.id)}<option value={option.id}>{option.label}</option>{/each}
					</select>
					<svg class="pointer-events-none absolute right-2.5 top-1/2 size-3 -translate-y-1/2 text-gray-500" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M5.22 7.22a.75.75 0 0 1 1.06 0L10 10.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 8.28a.75.75 0 0 1 0-1.06Z" clip-rule="evenodd" /></svg>
				</div>
				<div class="flex-1"></div>
				<details class="relative">
					<summary class="flex size-8 cursor-pointer list-none items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-850" aria-label="模型操作">⋯</summary>
					<div class="absolute right-0 z-20 mt-1 w-40 rounded-xl border border-gray-200 bg-white p-1 shadow-lg dark:border-gray-800 dark:bg-gray-850">
						<button class="w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-gray-100 dark:hover:bg-gray-800" type="button" onclick={() => setActiveForFiltered(true)}>启用全部</button>
						<button class="w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-gray-100 dark:hover:bg-gray-800" type="button" onclick={() => setActiveForFiltered(false)}>停用全部</button>
						<button class="w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-gray-100 dark:hover:bg-gray-800" type="button" onclick={() => setHiddenForFiltered(false)}>显示全部</button>
						<button class="w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-gray-100 dark:hover:bg-gray-800" type="button" onclick={() => setHiddenForFiltered(true)}>隐藏全部</button>
					</div>
				</details>
			</div>
			<div class="my-2 px-3">
				{#each filteredModels as model (model.id)}
					<div class="flex w-full items-center gap-3 rounded-xl px-3 py-2 transition hover:bg-gray-100/70 dark:hover:bg-white/5 {model.meta?.hidden ? 'opacity-50' : ''}">
						<button type="button" class="flex min-w-0 flex-1 items-center gap-3 text-left" onclick={() => selectedId = model.id}>
							<img src={model.meta?.profileImageUrl || '/favicon.svg'} alt="" class="size-9 shrink-0 rounded-full object-cover" />
							<span class="min-w-0 flex-1"><span class="block truncate text-sm font-medium {model.isActive === false ? 'text-gray-500' : ''}">{model.name}</span><span class="block truncate text-xs text-gray-500">{model.description || model.id}</span></span>
							<span class="hidden rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-500 dark:bg-gray-800 sm:inline">{model.owner === 'shared' ? '公开' : '私有'}</span>
						</button>
						<button type="button" class="rounded-lg p-2 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-800" aria-label="编辑模型" onclick={() => selectedId = model.id}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="size-4"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Z" /></svg></button>
						<button type="button" role="switch" aria-label={`启用 ${model.name}`} aria-checked={model.isActive !== false} class="relative h-5 w-9 shrink-0 rounded-full transition {model.isActive === false ? 'bg-gray-300 dark:bg-gray-700' : 'bg-emerald-600'}" onclick={() => { upsertModel({ ...model, isActive: model.isActive === false }); models = listModels(); }}><span class="absolute top-0.5 size-4 rounded-full bg-white shadow transition-all {model.isActive === false ? 'left-0.5' : 'left-[18px]'}"></span></button>
					</div>
				{:else}
					<div class="flex flex-col items-center justify-center px-4 py-16 text-center"><div class="mb-3 text-3xl">⌕</div><div class="text-base font-medium">没有找到模型</div><p class="mt-1 text-xs text-gray-500">尝试调整搜索条件或筛选器。</p></div>
				{/each}
			</div>
		</div>
	</section>
{/if}

{#if showManageModal}
	<div class="fixed inset-0 z-[9999] flex items-center justify-center overflow-y-auto bg-black/60 p-3" role="presentation" onclick={(event) => { if (event.target === event.currentTarget) showManageModal = false; }}>
		<section class="my-auto max-h-[95dvh] w-full max-w-3xl overflow-y-auto rounded-[1.75rem] border border-white/10 bg-[#171717] text-gray-200 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="manage-models-title" tabindex="-1">
			<header class="flex items-center justify-between px-5 pt-4"><h2 id="manage-models-title" class="text-lg font-medium">管理模型</h2><button type="button" aria-label="关闭" class="rounded-lg p-1 hover:bg-white/10" onclick={() => showManageModal = false}><span class="text-2xl leading-none">×</span></button></header>
			<div class="flex flex-col gap-4 px-4 pb-5 pt-2">
				<h3 class="text-sm font-medium">Ollama</h3>
				<select class="w-full rounded-xl bg-[#262626] px-4 py-3 text-sm outline-none" bind:value={manageUrl} aria-label="选择 Ollama 实例">{#each availableOllamaUrls as url (url)}<option value={url}>{url}</option>{/each}</select>
				<section>
					<div class="mb-2 text-sm font-medium">从 Ollama.com 下载模型 <span aria-hidden="true">⇩</span></div>
					<div class="flex gap-2"><input class="min-w-0 flex-1 rounded-xl bg-[#262626] px-4 py-3 text-sm outline-none placeholder:text-gray-400" bind:value={downloadTag} placeholder="输入模型标签（例如：mistral:7b）" onkeydown={(event) => event.key === 'Enter' && mockPullModel()} /><button type="button" aria-label="下载模型" disabled={!downloadTag.trim()} class="rounded-xl bg-[#262626] px-4 text-lg disabled:opacity-40" onclick={mockPullModel}>⇩</button></div>
					<p class="mt-2 text-xs text-gray-400">访问可下载的模型名称，<a class="font-medium underline" href="https://ollama.com/library" target="_blank" rel="noreferrer">点击此处</a></p>
				</section>
				<section>
					<label for="delete-model" class="mb-2 block text-sm font-medium">删除模型</label>
					<div class="flex gap-2"><select id="delete-model" class="min-w-0 flex-1 rounded-xl bg-[#262626] px-4 py-3 text-sm outline-none" bind:value={deleteTag}><option value="">选择模型</option>{#each ollamaModels as tag (tag)}<option value={tag}>{tag}</option>{/each}</select><button type="button" aria-label="删除模型" disabled={!deleteTag} class="rounded-xl bg-[#262626] px-4 text-lg disabled:opacity-40" onclick={mockDeleteModel}>▤</button></div>
				</section>
				<section>
					<label for="create-model-name" class="mb-2 block text-sm font-medium">创建模型</label>
					<div class="flex gap-2"><div class="flex min-w-0 flex-1 flex-col gap-2"><input id="create-model-name" class="w-full rounded-xl bg-[#262626] px-4 py-3 text-sm outline-none placeholder:text-gray-400" bind:value={createTag} placeholder="输入模型标签（例如：my-modelfile）" /><textarea class="min-h-36 w-full resize-y rounded-xl bg-[#262626] px-4 py-3 text-sm outline-none placeholder:text-gray-400" bind:value={createJson} placeholder="填写模型 JSON 配置"></textarea></div><button type="button" aria-label="创建模型" disabled={!createTag.trim() || !createJson.trim()} class="h-12 rounded-xl bg-[#262626] px-4 text-lg disabled:opacity-40" onclick={mockCreateModel}>⇧</button></div>
				</section>
				<section class="border-t border-white/10 pt-3"><button class="flex w-full items-center justify-between text-sm font-medium" type="button" onclick={() => showExperimental = !showExperimental}><span>实验性</span><span class="text-gray-400">{showExperimental ? '隐藏' : '显示'}</span></button>{#if showExperimental}<p class="mt-3 rounded-xl bg-[#262626] p-3 text-xs text-gray-400">实验性模型上传与 GGUF 管理（mock）</p>{/if}</section>
			</div>
		</section>
	</div>
{/if}

{#if showSettingsModal}
	<div class="fixed inset-0 z-[9999] flex items-center justify-center overflow-y-auto bg-black/60 p-3" role="presentation" onclick={(event) => { if (event.target === event.currentTarget) showSettingsModal = false; }}>
		<section class="my-auto flex max-h-[95dvh] w-full max-w-4xl flex-col rounded-[1.75rem] border border-white/10 bg-[#171717] text-gray-200 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="model-settings-title" tabindex="-1">
			<header class="flex items-center justify-between px-5 pt-4"><h2 id="model-settings-title" class="text-lg font-medium">设置</h2><button type="button" aria-label="关闭" class="rounded-lg p-1 hover:bg-white/10" onclick={() => showSettingsModal = false}><span class="text-2xl leading-none">×</span></button></header>
			<div class="flex flex-1 flex-col gap-3 overflow-hidden px-4 pb-4 pt-2">
				<div class="flex gap-3"><button type="button" class="flex items-center gap-2 text-sm font-medium {settingsTab === 'defaults' ? 'text-white' : 'text-gray-500'}" onclick={() => settingsTab = 'defaults'}>☷ 默认值</button><button type="button" class="flex items-center gap-2 text-sm font-medium {settingsTab === 'display' ? 'text-white' : 'text-gray-500'}" onclick={() => settingsTab = 'display'}>◉ 显示</button></div>
				<div class="min-h-0 flex-1 overflow-y-auto">
					{#if settingsTab === 'defaults'}
						<section class="border-b border-white/10 py-3"><div class="mb-2 flex items-center gap-1 text-xs text-gray-400">已选模型 <span title="新建聊天时默认选择">ⓘ</span></div><select class="w-full bg-transparent py-1 text-sm outline-none" onchange={(event) => { const id = event.currentTarget.value; if (id) selectedDefaultModels = toggleSelection(selectedDefaultModels, id); event.currentTarget.value = ''; }}><option value="">选择模型</option>{#each models as model (model.id)}<option value={model.id}>{model.name}</option>{/each}</select>{#if selectedDefaultModels.length}<div class="mt-2 space-y-1">{#each selectedDefaultModels as id (id)}<div class="flex items-center justify-between rounded-lg bg-[#222] px-2 py-1 text-sm">{models.find((model) => model.id === id)?.name ?? id}<button type="button" aria-label={`移除 ${id}`} class="px-2 text-gray-400" onclick={() => selectedDefaultModels = selectedDefaultModels.filter((entry) => entry !== id)}>×</button></div>{/each}</div>{:else}<div class="py-3 text-center text-xs text-gray-500">未选择任何模型</div>{/if}</section>
						<section class="border-b border-white/10 py-3"><div class="mb-2 flex items-center gap-1 text-xs text-gray-400">固定在侧边栏的模型 <span title="固定显示在侧边栏">ⓘ</span></div><select class="w-full bg-transparent py-1 text-sm outline-none" onchange={(event) => { const id = event.currentTarget.value; if (id) pinnedModels = toggleSelection(pinnedModels, id); event.currentTarget.value = ''; }}><option value="">选择模型</option>{#each models as model (model.id)}<option value={model.id}>{model.name}</option>{/each}</select>{#if pinnedModels.length}<div class="mt-2 space-y-1">{#each pinnedModels as id (id)}<div class="flex items-center justify-between rounded-lg bg-[#222] px-2 py-1 text-sm">{models.find((model) => model.id === id)?.name ?? id}<button type="button" aria-label={`移除固定模型 ${id}`} class="px-2 text-gray-400" onclick={() => pinnedModels = pinnedModels.filter((entry) => entry !== id)}>×</button></div>{/each}</div>{:else}<div class="py-3 text-center text-xs text-gray-500">未选择任何模型</div>{/if}</section>
						<section class="border-b border-white/10 py-3"><button class="flex w-full items-center justify-between text-sm" type="button" onclick={() => promptSuggestionsOpen = !promptSuggestionsOpen}>推荐提示词 <span>{promptSuggestionsOpen ? '⌃' : '⌄'}</span></button>{#if promptSuggestionsOpen}<div class="mt-3 space-y-2">{#each promptSuggestions as prompt, index (index)}<div class="flex gap-2"><input class="min-w-0 flex-1 rounded-lg bg-[#262626] px-3 py-2 text-xs" bind:value={prompt.title} placeholder="标题" /><input class="min-w-0 flex-[2] rounded-lg bg-[#262626] px-3 py-2 text-xs" bind:value={prompt.content} placeholder="提示词内容" /><button type="button" aria-label="移除提示词" onclick={() => promptSuggestions = promptSuggestions.filter((_, idx) => idx !== index)}>×</button></div>{/each}<button type="button" class="rounded-lg bg-[#262626] px-3 py-2 text-xs" onclick={() => promptSuggestions = [...promptSuggestions, { title: '', content: '' }]}>＋ 添加提示词</button></div>{/if}</section>
						<section class="border-b border-white/10 py-3"><button class="flex w-full items-center justify-between text-sm" type="button" onclick={() => capabilitiesOpen = !capabilitiesOpen}>模型能力 <span>{capabilitiesOpen ? '⌃' : '⌄'}</span></button>{#if capabilitiesOpen}<div class="mt-3 grid gap-2 sm:grid-cols-2">{#each Object.entries({ vision: '视觉', file_upload: '文件上传', file_context: '文件上下文', web_search: '联网搜索', image_generation: '图像生成', code_interpreter: '代码解释器', citations: '引用', status_updates: '实时状态', builtin_tools: '内置工具', usage: '用量' }) as [key, label] (key)}<label class="flex items-center gap-2 text-xs"><input type="checkbox" bind:checked={modelCapabilities[key]} />{label}</label>{/each}</div>{/if}</section>
						<section class="border-b border-white/10 py-3"><button class="flex w-full items-center justify-between text-sm" type="button" onclick={() => paramsOpen = !paramsOpen}>模型参数 <span>{paramsOpen ? '⌃' : '⌄'}</span></button>{#if paramsOpen}<div class="mt-3 grid gap-3 sm:grid-cols-2">{#each Object.keys(modelParams) as key (key)}<label class="text-xs text-gray-400">{key}<input class="mt-1 w-full rounded-lg bg-[#262626] px-3 py-2 text-sm text-gray-200" bind:value={modelParams[key]} placeholder="默认" /></label>{/each}</div>{/if}</section>
					{:else}
						<section class="py-3"><div class="mb-2 flex items-center justify-between text-xs text-gray-400">重新排序模型<button type="button" class="rounded-lg bg-[#262626] px-2 py-1" onclick={() => orderedModelIds = [...models].sort((a, b) => a.name.localeCompare(b.name)).map((model) => model.id)}>按名称排序</button></div><div class="space-y-1">{#each orderedModelIds as id, index (id)}<div class="flex items-center justify-between rounded-lg bg-[#222] px-3 py-2 text-sm"><span>{models.find((model) => model.id === id)?.name ?? id}</span><div class="flex gap-2"><button type="button" aria-label="上移" disabled={index === 0} onclick={() => { const next = [...orderedModelIds]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; orderedModelIds = next; }}>↑</button><button type="button" aria-label="下移" disabled={index === orderedModelIds.length - 1} onclick={() => { const next = [...orderedModelIds]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; orderedModelIds = next; }}>↓</button></div></div>{/each}</div></section>
					{/if}
				</div>
				<footer class="flex items-center justify-between border-t border-white/10 pt-3"><button type="button" class="text-sm text-gray-400 hover:text-gray-200" onclick={() => { selectedDefaultModels = []; pinnedModels = []; orderedModelIds = models.map((model) => model.id); promptSuggestions = []; modelCapabilities = { vision: true, file_upload: true, file_context: true, web_search: true, image_generation: true, code_interpreter: true, citations: true, status_updates: true, builtin_tools: true, usage: false }; modelParams = { temperature: '', top_p: '', max_tokens: '', seed: '' }; inform('已恢复模型设置默认值'); }}>重置</button><button type="button" class="rounded-full bg-white px-4 py-2 text-sm font-medium text-black" onclick={saveModelSettings}>保存</button></footer>
			</div>
		</section>
	</div>
{/if}

{#if notice}<div class="fixed bottom-5 right-5 z-[10000] rounded-xl bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg dark:bg-white dark:text-gray-900" role="status">{notice}</div>{/if}

