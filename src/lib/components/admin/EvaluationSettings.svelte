<script lang="ts">
	import { listModels, type WorkspaceModel } from '$lib/data/workspaceResources';

	type ArenaModel = {
		id: string;
		name: string;
		meta: {
			profile_image_url: string;
			description: string;
			model_ids: string[] | null;
			filter_mode: 'include' | 'exclude';
			access_grants: { role: 'user' | 'admin' | 'group'; id: string; name: string }[];
		};
	};
	type EvaluationConfig = { enabled: boolean; models: ArenaModel[] };
	const STORAGE_KEY = 'admin-evaluation-arena-mock';
	const availableModels = $state<WorkspaceModel[]>(listModels());
	const defaultImage = '/favicon.svg';
	const defaultConfig: EvaluationConfig = { enabled: true, models: [] };

	let config = $state<EvaluationConfig>(defaultConfig);
	let showEditor = $state(false);
	let editingId = $state<string | null>(null);
	let confirmDelete = $state<string | null>(null);
	let notice = $state('');
	let name = $state('');
	let id = $state('');
	let description = $state('');
	let profileImageUrl = $state(defaultImage);
	let selectedModelId = $state('');
	let modelIds = $state<string[]>([]);
	let filterMode = $state<'include' | 'exclude'>('include');
	let accessGrants = $state<ArenaModel['meta']['access_grants']>([]);
	let accessScope = $state<'everyone' | 'selected'>('everyone');
	let saving = $state(false);
	let fileInput: HTMLInputElement | null = $state(null);

	function inform(message: string) {
		notice = message;
		setTimeout(() => notice = '', 2300);
	}

	function persist() {
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
		} catch {
			inform('无法保存到浏览器本地存储');
		}
	}

	function resetEditor() {
		editingId = null;
		name = '';
		id = '';
		description = '';
		profileImageUrl = defaultImage;
		selectedModelId = '';
		modelIds = [];
		filterMode = 'include';
		accessGrants = [];
		accessScope = 'everyone';
	}

	function openAdd() {
		resetEditor();
		showEditor = true;
	}

	function openEdit(model: ArenaModel) {
		editingId = model.id;
		name = model.name;
		id = model.id;
		description = model.meta.description;
		profileImageUrl = model.meta.profile_image_url || defaultImage;
		modelIds = [...(model.meta.model_ids ?? [])];
		filterMode = model.meta.filter_mode ?? 'include';
		accessGrants = [...(model.meta.access_grants ?? [])];
		accessScope = accessGrants.length ? 'selected' : 'everyone';
		showEditor = true;
	}

	function normalizeId(value: string) {
		return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').replace(/-+/g, '-');
	}

	function addSelectedModel() {
		if (selectedModelId && !modelIds.includes(selectedModelId)) modelIds = [...modelIds, selectedModelId];
		selectedModelId = '';
	}

	function saveArenaModel(event: SubmitEvent) {
		event.preventDefault();
		const cleanName = name.trim();
		const cleanId = (editingId ? id : normalizeId(name)).trim();
		if (!cleanName || !cleanId) {
			inform('请填写模型名称');
			return;
		}
		if (config.models.some((item) => item.id === cleanId && item.id !== editingId)) {
			inform('此 ID 已被使用，请修改名称');
			return;
		}
		saving = true;
		const entry: ArenaModel = {
			id: cleanId,
			name: cleanName,
			meta: {
				profile_image_url: profileImageUrl,
				description: description.trim(),
				model_ids: modelIds.length ? [...modelIds] : null,
				filter_mode: modelIds.length ? filterMode : 'include',
				access_grants: accessScope === 'selected' ? [...accessGrants] : []
			}
		};
		config.models = editingId ? config.models.map((item) => item.id === editingId ? entry : item) : [...config.models, entry];
		persist();
		saving = false;
		showEditor = false;
		resetEditor();
		inform(editingId ? '评价模型已更新（本地 mock）' : '评价模型已添加（本地 mock）');
	}

	function deleteArenaModel(idToDelete: string) {
		config.models = config.models.filter((model) => model.id !== idToDelete);
		persist();
		confirmDelete = null;
		showEditor = false;
		resetEditor();
		inform('评价模型已删除（本地 mock）');
	}

	function importImage(event: Event) {
		const file = (event.currentTarget as HTMLInputElement).files?.[0];
		if (!file) return;
		if (!file.type.startsWith('image/')) {
			inform('请选择图片文件');
			return;
		}
		const reader = new FileReader();
		reader.onload = () => profileImageUrl = String(reader.result || defaultImage);
		reader.readAsDataURL(file);
	}

	$effect(() => {
		try {
			const stored = localStorage.getItem(STORAGE_KEY);
			if (stored) {
				const parsed = JSON.parse(stored) as EvaluationConfig;
				if (Array.isArray(parsed.models)) config = parsed;
			} else {
				config = structuredClone(defaultConfig);
				persist();
			}
		} catch {
			inform('读取本地评价配置失败');
		}
	});
</script>

<div class="flex min-h-full flex-col text-sm">
	<section class="mb-4">
		<div class="mb-2 mt-0.5 text-base font-medium">常规</div>
		<hr class="my-2 border-gray-100/30 dark:border-gray-850/30" />
		<div class="mb-2.5 flex w-full items-center justify-between gap-3">
			<div><div class="text-xs font-medium">对战模型</div><p class="mt-1 text-xs text-gray-500">启用模型对战后，可在评估页面比较不同模型的回答。</p></div>
			<button type="button" role="switch" aria-checked={config.enabled} aria-label="启用模型对战" class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition {config.enabled ? 'bg-emerald-600' : 'bg-gray-300 dark:bg-gray-700'}" onclick={() => { config.enabled = !config.enabled; persist(); }}><span class="absolute size-4 rounded-full bg-white shadow transition-all {config.enabled ? 'left-[18px]' : 'left-0.5'}"></span></button>
		</div>
	</section>

	{#if config.enabled}
		<section>
			<div class="mb-2.5 mt-0.5 flex items-center justify-between"><h2 class="text-base font-medium">管理</h2><button type="button" class="flex size-8 items-center justify-center rounded-lg text-gray-600 transition hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/10" aria-label="添加对战模型" title="添加对战模型" onclick={openAdd}><span class="text-xl leading-none">＋</span></button></div>
			<hr class="my-2 border-gray-100/30 dark:border-gray-850/30" />
			<div class="flex flex-col gap-2">
				{#if config.models.length}
					{#each config.models as model (model.id)}
						<div class="flex items-center justify-between gap-3 py-1">
							<div class="flex min-w-0 flex-1 items-center gap-2.5"><img src={model.meta.profile_image_url || defaultImage} alt="" class="size-8 shrink-0 rounded-full object-cover" /><div class="min-w-0 flex-1"><div class="truncate font-medium">{model.name}</div><div class="truncate text-xs text-gray-500">{model.meta.description || model.id}</div></div></div>
							<button type="button" class="rounded-xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:hover:bg-white/5 dark:hover:text-white" aria-label={`编辑 ${model.name}`} title="设置" onclick={() => openEdit(model)}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="size-4"><path stroke-linecap="round" stroke-linejoin="round" d="M10.5 6h9m-9 6h9m-9 6h9M4.5 6h.01M4.5 12h.01M4.5 18h.01"/><path stroke-linecap="round" stroke-linejoin="round" d="m3.5 6 1 1 2-2m-3 7 1 1 2-2m-3 7 1 1 2-2"/></svg></button>
						</div>
					{/each}
				{:else}
					<div class="py-4 text-center text-xs text-gray-500">使用默认对战模型（包含全部可用模型）。点击加号添加自定义模型。</div>
				{/if}
			</div>
		</section>
	{/if}
</div>

{#if showEditor}
	<div class="fixed inset-0 z-[9999] flex items-center justify-center overflow-y-auto bg-black/60 p-3" role="presentation" onclick={(event) => { if (event.target === event.currentTarget) showEditor = false; }}>
		<div class="my-auto w-full max-w-lg rounded-[1.75rem] border border-white/10 bg-gray-950/95 text-gray-100 shadow-2xl backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="arena-model-title" tabindex="-1">
			<header class="flex items-center justify-between px-5 pb-2 pt-4"><h2 id="arena-model-title" class="text-lg font-medium">{editingId ? '编辑对战模型' : '添加对战模型'}</h2><button type="button" class="rounded-lg p-1 text-gray-300 hover:bg-white/10" aria-label="关闭" onclick={() => showEditor = false}><span class="text-xl">×</span></button></header>
			<form class="flex flex-col px-5 pb-4" onsubmit={saveArenaModel}>
				<div class="flex justify-center pb-4"><input bind:this={fileInput} class="hidden" type="file" accept="image/*" onchange={importImage} /><button class="relative size-16 shrink-0 overflow-hidden rounded-full" type="button" aria-label="上传头像" onclick={() => fileInput?.click()}><img src={profileImageUrl} class="size-16 rounded-full object-cover" alt="模型头像" /><span class="absolute inset-0 flex items-center justify-center bg-black/50 text-white opacity-0 transition hover:opacity-100">✎</span></button></div>
				<div class="grid grid-cols-2 gap-3"><label class="field-wrap"><span>名称</span><input bind:value={name} placeholder="模型名称" required oninput={() => { if (!editingId) id = normalizeId(name); }} /></label><label class="field-wrap"><span>ID</span><input bind:value={id} placeholder="自动生成" required disabled={!!editingId} /></label></div>
				<label class="field-wrap mt-3"><span>描述</span><input bind:value={description} placeholder="输入描述" /></label>
				<hr class="my-3 border-gray-700/60" />
				<section><div class="mb-2 text-xs font-medium text-gray-400">访问权限</div><div class="flex flex-wrap gap-3 text-xs"><label class="flex items-center gap-2"><input type="radio" bind:group={accessScope} value="everyone" />所有用户</label><label class="flex items-center gap-2"><input type="radio" bind:group={accessScope} value="selected" />指定用户或用户组</label></div>{#if accessScope === 'selected'}<div class="mt-3 grid grid-cols-2 gap-2"><label class="flex items-center gap-2 text-xs"><input type="checkbox" checked={accessGrants.some((grant) => grant.role === 'user' && grant.id === 'admin')} onchange={(event) => accessGrants = event.currentTarget.checked ? [...accessGrants.filter((grant) => grant.id !== 'admin'), { role: 'user', id: 'admin', name: '管理员' }] : accessGrants.filter((grant) => grant.id !== 'admin')} />管理员</label><label class="flex items-center gap-2 text-xs"><input type="checkbox" checked={accessGrants.some((grant) => grant.role === 'user' && grant.id === 'all-users')} onchange={(event) => accessGrants = event.currentTarget.checked ? [...accessGrants.filter((grant) => grant.id !== 'all-users'), { role: 'user', id: 'all-users', name: '所有登录用户' }] : accessGrants.filter((grant) => grant.id !== 'all-users')} />所有登录用户</label></div><p class="mt-2 text-[11px] text-gray-500">权限设置仅保存在本地 mock 配置中。</p>{/if}</section>
				<hr class="my-3 border-gray-700/60" />
				<section><div class="mb-1 flex items-center justify-between"><span class="text-xs text-gray-400">模型范围</span><button type="button" class="text-xs text-gray-400 hover:text-white" onclick={() => filterMode = filterMode === 'include' ? 'exclude' : 'include'}>{filterMode === 'include' ? '包含' : '排除'}</button></div>{#if modelIds.length}<div class="space-y-1">{#each modelIds as modelId (modelId)}<div class="flex items-center justify-between rounded-lg px-1 py-1 text-sm"><span>{availableModels.find((item) => item.id === modelId)?.name ?? modelId}</span><button type="button" class="px-2 text-gray-400 hover:text-white" aria-label={`移除 ${modelId}`} onclick={() => modelIds = modelIds.filter((item) => item !== modelId)}>−</button></div>{/each}</div>{:else}<p class="py-2 text-center text-xs text-gray-500">留空表示包含所有模型，也可以指定模型范围</p>{/if}<div class="mt-2 flex items-center gap-2"><select class="min-w-0 flex-1 rounded-lg bg-gray-850 px-3 py-2 text-sm outline-none" bind:value={selectedModelId}><option value="">选择模型</option>{#each availableModels as model (model.id)}<option value={model.id}>{model.name}</option>{/each}</select><button type="button" class="rounded-lg p-2 text-gray-300 hover:bg-white/10 disabled:opacity-40" aria-label="添加所选模型" disabled={!selectedModelId || modelIds.includes(selectedModelId)} onclick={addSelectedModel}>＋</button></div></section>
				<div class="flex justify-end gap-2 pt-4">{#if editingId}<button type="button" class="mr-auto rounded-full px-3.5 py-1.5 text-sm text-red-400 hover:bg-red-500/10" onclick={() => confirmDelete = editingId}>删除</button>{/if}<button type="button" class="rounded-full px-3.5 py-1.5 text-sm text-gray-300 hover:bg-white/10" onclick={() => showEditor = false}>取消</button><button type="submit" class="rounded-full bg-white px-4 py-1.5 text-sm font-medium text-gray-900 disabled:opacity-50" disabled={saving}>{saving ? '保存中…' : '保存'}</button></div>
			</form>
		</div>
	</div>
{/if}

{#if confirmDelete}
	<div class="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 p-4" role="presentation" onclick={(event) => { if (event.target === event.currentTarget) confirmDelete = null; }}><div class="w-full max-w-sm rounded-2xl border border-white/10 bg-gray-950 p-5 text-gray-100 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="arena-delete-title" tabindex="-1"><h3 id="arena-delete-title" class="font-medium">删除对战模型？</h3><p class="mt-2 text-sm text-gray-400">该模型会从本地评价配置中移除。</p><div class="mt-5 flex justify-end gap-2"><button type="button" class="rounded-lg px-3 py-1.5 text-sm hover:bg-white/10" onclick={() => confirmDelete = null}>取消</button><button type="button" class="rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white" onclick={() => deleteArenaModel(confirmDelete!)}>删除</button></div></div></div>
{/if}
{#if notice}<div class="fixed bottom-5 right-5 z-[10001] max-w-sm rounded-xl bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg dark:bg-white dark:text-gray-900" role="status">{notice}</div>{/if}

<style>
	.field-wrap { display: flex; min-width: 0; flex-direction: column; gap: 0.25rem; }
	.field-wrap span { font-size: 0.75rem; color: rgb(156 163 175); }
	.field-wrap input { width: 100%; min-width: 0; border: 0; border-bottom: 1px solid rgb(75 85 99); background: transparent; padding: 0.35rem 0; font-size: 0.875rem; outline: none; }
	.field-wrap input:focus { border-color: rgb(156 163 175); }
</style>
