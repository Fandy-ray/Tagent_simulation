<script lang="ts">
	type AuthMode = 'bearer' | 'none';
	type Provider = {
		name: string;
		served_model_id: string;
		base_url: string;
		upstream_model: string;
		auth_mode: AuthMode;
		api_key: string;
		temperature: number;
		enabled: boolean;
	};
	type ProviderForm = Provider;
	type StoredRegistry = { default_model_id: string; providers: Provider[] };

	const STORAGE_KEY = 'admin-agent-model-providers-mock';
	const initialRegistry: StoredRegistry = {
		default_model_id: 'openai-compatible:gpt-4o-mini',
		providers: [
			{
				name: 'OpenAI Compatible',
				served_model_id: 'openai-compatible:gpt-4o-mini',
				base_url: 'https://api.openai.com/v1',
				upstream_model: 'gpt-4o-mini',
				auth_mode: 'bearer',
				api_key: '',
				temperature: 0.1,
				enabled: true
			}
		]
	};

	let registry = $state<StoredRegistry>(initialRegistry);
	let editingId = $state<string | null>(null);
	let editingHasKey = $state(false);
	let form = $state<ProviderForm>(emptyForm());
	let notice = $state('');
	let loadError = $state('');
	let search = $state('');
	let filter = $state<'all' | 'enabled' | 'disabled'>('all');
	let saving = $state(false);
	let confirmDelete = $state<string | null>(null);

	let filteredProviders = $derived(registry.providers.filter((provider) => {
		const query = search.trim().toLowerCase();
		const matchesQuery = !query || [provider.name, provider.served_model_id, provider.upstream_model].some((value) => value.toLowerCase().includes(query));
		const matchesFilter = filter === 'all' || (filter === 'enabled' ? provider.enabled : !provider.enabled);
		return matchesQuery && matchesFilter;
	}));

	function emptyForm(): ProviderForm {
		return { name: '', served_model_id: '', base_url: '', upstream_model: '', auth_mode: 'bearer', api_key: '', temperature: 0.1, enabled: true };
	}

	function persist() {
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(registry));
		} catch {
			loadError = '无法保存到浏览器本地存储';
		}
	}

	function inform(message: string) {
		notice = message;
		setTimeout(() => notice = '', 2400);
	}

	function resetForm() {
		editingId = null;
		editingHasKey = false;
		form = emptyForm();
	}

	function editProvider(provider: Provider) {
		editingId = provider.served_model_id;
		editingHasKey = Boolean(provider.api_key);
		form = { ...provider, api_key: '' };
	}

	function validate() {
		if (!form.name.trim()) return '请填写显示名称';
		if (!/^[A-Za-z0-9._:-]{1,128}$/.test(form.served_model_id.trim())) return '模型 ID 仅支持字母、数字、点、下划线、冒号和连字符';
		try {
			const url = new URL(form.base_url.trim());
			if (!['http:', 'https:'].includes(url.protocol)) throw new Error();
		} catch {
			return '请输入有效的 HTTP 或 HTTPS 服务地址';
		}
		if (!form.upstream_model.trim()) return '请填写上游模型名称';
		if (form.auth_mode === 'bearer' && !form.api_key.trim() && (!editingId || !editingHasKey)) return 'Bearer 认证需要填写 API Key';
		if (!Number.isFinite(Number(form.temperature)) || Number(form.temperature) < 0 || Number(form.temperature) > 2) return 'Temperature 必须在 0 到 2 之间';
		if (!editingId && registry.providers.some((provider) => provider.served_model_id === form.served_model_id.trim())) return '该模型 ID 已存在';
		return '';
	}

	function saveProvider() {
		const error = validate();
		if (error) {
			inform(error);
			return;
		}
		saving = true;
		const provider: Provider = {
			...form,
			name: form.name.trim(),
			served_model_id: form.served_model_id.trim(),
			base_url: form.base_url.trim().replace(/\/$/, ''),
			upstream_model: form.upstream_model.trim(),
			temperature: Number(form.temperature),
			api_key: form.auth_mode === 'none' ? '' : (form.api_key || registry.providers.find((item) => item.served_model_id === editingId)?.api_key || '')
		};
		if (editingId) {
			registry.providers = registry.providers.map((item) => item.served_model_id === editingId ? provider : item);
			if (registry.default_model_id === editingId) registry.default_model_id = provider.served_model_id;
		} else {
			registry.providers = [...registry.providers, provider];
			if (!registry.default_model_id && provider.enabled) registry.default_model_id = provider.served_model_id;
		}
		persist();
		resetForm();
		saving = false;
		inform('智能体模型提供商已保存（本地 mock）');
	}

	function toggleProvider(provider: Provider) {
		registry.providers = registry.providers.map((item) => item.served_model_id === provider.served_model_id ? { ...item, enabled: !item.enabled } : item);
		if (!provider.enabled) registry.default_model_id = provider.served_model_id;
		else if (registry.default_model_id === provider.served_model_id) registry.default_model_id = registry.providers.find((item) => item.enabled && item.served_model_id !== provider.served_model_id)?.served_model_id ?? '';
		persist();
	}

	function setDefault(provider: Provider) {
		if (!provider.enabled) return;
		registry.default_model_id = provider.served_model_id;
		persist();
		inform('默认智能体模型已更新（本地 mock）');
	}

	function deleteProvider(id: string) {
		registry.providers = registry.providers.filter((provider) => provider.served_model_id !== id);
		if (registry.default_model_id === id) registry.default_model_id = registry.providers.find((provider) => provider.enabled)?.served_model_id ?? '';
		if (editingId === id) resetForm();
		confirmDelete = null;
		persist();
		inform('智能体模型提供商已删除（本地 mock）');
	}

	$effect(() => {
		try {
			const stored = localStorage.getItem(STORAGE_KEY);
			if (stored) {
				const parsed = JSON.parse(stored) as StoredRegistry;
				if (Array.isArray(parsed.providers)) registry = parsed;
			} else {
				registry = structuredClone(initialRegistry);
				persist();
			}
		} catch {
			loadError = '读取本地智能体模型配置失败';
		}
	});
</script>

<div class="flex min-h-full flex-col">
	<header class="flex items-center justify-between gap-3 border-b border-gray-100 pb-3 dark:border-gray-800">
		<div class="min-w-0">
			<h2 class="text-base font-medium text-gray-900 dark:text-gray-100">智能体模型</h2>
			<p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">OpenAI 兼容服务提供商</p>
		</div>
		<button type="button" class="flex size-8 items-center justify-center rounded-lg bg-gray-900 text-white hover:bg-gray-800 dark:bg-white dark:text-gray-900" onclick={resetForm} aria-label="添加模型提供商" title="添加模型提供商"><span class="text-xl leading-none">＋</span></button>
	</header>

	{#if loadError}<div class="mt-3 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-200" role="alert">{loadError}</div>{/if}

	<div class="grid min-h-0 flex-1 grid-cols-1 gap-5 pt-4 xl:grid-cols-[minmax(0,1fr)_340px]">
		<section class="min-w-0" aria-label="模型提供商">
			<div class="mb-3 flex flex-col gap-2 sm:flex-row">
				<input class="min-w-0 flex-1 rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none placeholder:text-gray-400 focus:border-gray-400 dark:border-gray-700" bind:value={search} placeholder="搜索名称或模型 ID" aria-label="搜索智能体模型" />
				<select class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none dark:border-gray-700 dark:bg-gray-900" bind:value={filter} aria-label="按状态筛选"><option value="all">全部状态</option><option value="enabled">已启用</option><option value="disabled">已停用</option></select>
			</div>
			{#if filteredProviders.length === 0}
				<div class="border-y border-gray-100 py-10 text-center text-sm text-gray-500 dark:border-gray-800 dark:text-gray-400">{registry.providers.length ? '没有符合条件的模型提供商' : '暂无模型提供商，点击右上角添加'}</div>
			{:else}
				<div class="hidden overflow-x-auto md:block">
					<table class="w-full table-fixed text-left text-sm">
						<thead class="border-b border-gray-100 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400"><tr><th class="w-[22%] px-2 py-2 font-medium">名称</th><th class="w-[24%] px-2 py-2 font-medium">模型 ID</th><th class="w-[20%] px-2 py-2 font-medium">上游模型</th><th class="w-[12%] px-2 py-2 font-medium">状态</th><th class="w-[22%] px-2 py-2 text-right font-medium">操作</th></tr></thead>
						<tbody class="divide-y divide-gray-100 dark:divide-gray-800">
							{#each filteredProviders as provider (provider.served_model_id)}
								<tr class="align-middle">
									<td class="px-2 py-3"><div class="truncate font-medium text-gray-900 dark:text-gray-100">{provider.name}</div><div class="mt-0.5 truncate text-xs text-gray-500">{provider.auth_mode === 'bearer' ? (provider.api_key ? '••••••••' : '未配置 API Key') : '无需认证'}</div></td>
									<td class="truncate px-2 py-3 font-mono text-xs" title={provider.served_model_id}>{provider.served_model_id}{#if registry.default_model_id === provider.served_model_id}<span class="ml-1 font-sans text-emerald-600 dark:text-emerald-400">默认</span>{/if}</td>
									<td class="truncate px-2 py-3 font-mono text-xs" title={provider.upstream_model}>{provider.upstream_model}</td>
									<td class="px-2 py-3"><button type="button" role="switch" aria-label={`切换 ${provider.name} 状态`} aria-checked={provider.enabled} class="relative inline-flex h-5 w-9 items-center rounded-full transition {provider.enabled ? 'bg-emerald-600' : 'bg-gray-300 dark:bg-gray-700'}" onclick={() => toggleProvider(provider)}><span class="absolute size-4 rounded-full bg-white shadow transition-all {provider.enabled ? 'left-[18px]' : 'left-0.5'}"></span></button></td>
									<td class="px-2 py-3"><div class="flex justify-end gap-1">{#if provider.enabled && registry.default_model_id !== provider.served_model_id}<button class="icon-button" type="button" onclick={() => setDefault(provider)} aria-label="设为默认" title="设为默认">☆</button>{/if}<button class="icon-button" type="button" onclick={() => editProvider(provider)} aria-label="编辑" title="编辑">✎</button><button class="icon-button text-red-600 dark:text-red-400" type="button" onclick={() => confirmDelete = provider.served_model_id} aria-label="删除" title="删除">×</button></div></td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				<div class="divide-y divide-gray-100 border-y border-gray-100 dark:divide-gray-800 dark:border-gray-800 md:hidden">
					{#each filteredProviders as provider (provider.served_model_id)}
						<div class="py-3"><div class="flex items-start justify-between gap-3"><div class="min-w-0"><div class="truncate font-medium">{provider.name}{#if registry.default_model_id === provider.served_model_id}<span class="ml-1 text-emerald-600">默认</span>{/if}</div><div class="truncate font-mono text-xs text-gray-500">{provider.served_model_id}</div></div><button type="button" role="switch" aria-label={`切换 ${provider.name} 状态`} aria-checked={provider.enabled} class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition {provider.enabled ? 'bg-emerald-600' : 'bg-gray-300 dark:bg-gray-700'}" onclick={() => toggleProvider(provider)}><span class="absolute size-4 rounded-full bg-white shadow {provider.enabled ? 'left-[18px]' : 'left-0.5'}"></span></button></div><div class="mt-3 flex items-center justify-between gap-2 text-xs text-gray-500"><span class="truncate">{provider.upstream_model}</span><div class="flex gap-1"><button class="icon-button" type="button" onclick={() => editProvider(provider)} aria-label="编辑">✎</button><button class="icon-button text-red-600" type="button" onclick={() => confirmDelete = provider.served_model_id} aria-label="删除">×</button></div></div></div>
					{/each}
				</div>
			{/if}
		</section>

		<form class="space-y-3 border-t border-gray-100 pt-4 dark:border-gray-800 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0" onsubmit={(event) => { event.preventDefault(); saveProvider(); }} novalidate>
			<h3 class="text-sm font-medium text-gray-900 dark:text-gray-100">{editingId ? '编辑模型提供商' : '添加模型提供商'}</h3>
			<div><label class="field-label" for="agent-provider-name">名称</label><input id="agent-provider-name" class="field-input" bind:value={form.name} placeholder="例如：OpenAI 兼容服务" /></div>
			<div><label class="field-label" for="agent-provider-id">模型 ID</label><input id="agent-provider-id" class="field-input font-mono" bind:value={form.served_model_id} disabled={!!editingId} placeholder="例如：my-provider:gpt-4o-mini" /></div>
			<div><label class="field-label" for="agent-provider-url">Base URL</label><input id="agent-provider-url" class="field-input font-mono" bind:value={form.base_url} placeholder="https://api.openai.com/v1" /></div>
			<div><label class="field-label" for="agent-provider-model">上游模型</label><input id="agent-provider-model" class="field-input font-mono" bind:value={form.upstream_model} placeholder="gpt-4o-mini" /></div>
			<div class="grid grid-cols-2 gap-3"><div><label class="field-label" for="agent-provider-auth">认证方式</label><select id="agent-provider-auth" class="field-input" bind:value={form.auth_mode}><option value="bearer">Bearer</option><option value="none">无需认证</option></select></div><div><label class="field-label" for="agent-provider-temperature">Temperature</label><input id="agent-provider-temperature" class="field-input" type="number" min="0" max="2" step="0.1" bind:value={form.temperature} /></div></div>
			{#if form.auth_mode === 'bearer'}<div><label class="field-label" for="agent-provider-key">API Key</label><input id="agent-provider-key" class="field-input font-mono" type="password" bind:value={form.api_key} placeholder={editingId && editingHasKey ? '留空以保留当前密钥' : '输入 API Key（mock）'} autocomplete="new-password" /></div>{/if}
			<div class="flex items-center justify-between py-1"><span class="text-sm text-gray-700 dark:text-gray-200">启用提供商</span><button type="button" role="switch" aria-label="启用提供商" aria-checked={form.enabled} class="relative inline-flex h-5 w-9 items-center rounded-full transition {form.enabled ? 'bg-emerald-600' : 'bg-gray-300 dark:bg-gray-700'}" onclick={() => form.enabled = !form.enabled}><span class="absolute size-4 rounded-full bg-white shadow {form.enabled ? 'left-[18px]' : 'left-0.5'}"></span></button></div>
			<div class="flex justify-end gap-2 pt-2"><button class="rounded-lg border border-gray-200 px-3 py-1.5 text-sm hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800" type="button" onclick={resetForm}>取消</button><button class="rounded-lg bg-gray-900 px-3 py-1.5 text-sm text-white hover:bg-gray-800 dark:bg-white dark:text-gray-900" type="submit" disabled={saving}>{saving ? '保存中…' : '保存'}</button></div>
		</form>
	</div>
</div>

{#if confirmDelete}
	<div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4" role="presentation" onclick={(event) => { if (event.target === event.currentTarget) confirmDelete = null; }}><div class="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-5 shadow-2xl dark:border-gray-700 dark:bg-gray-900" role="dialog" aria-modal="true" aria-labelledby="agent-delete-title" tabindex="-1"><h3 id="agent-delete-title" class="font-medium">删除模型提供商？</h3><p class="mt-2 text-sm text-gray-500">此操作会从本地 mock 配置中移除该提供商。</p><div class="mt-5 flex justify-end gap-2"><button class="rounded-lg border border-gray-200 px-3 py-1.5 text-sm dark:border-gray-700" type="button" onclick={() => confirmDelete = null}>取消</button><button class="rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white" type="button" onclick={() => deleteProvider(confirmDelete!)}>删除</button></div></div></div>
{/if}
{#if notice}<div class="fixed bottom-5 right-5 z-[110] max-w-sm rounded-xl bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg dark:bg-white dark:text-gray-900" role="status">{notice}</div>{/if}

<style>
	:global(.icon-button) { display: inline-flex; height: 2rem; width: 2rem; align-items: center; justify-content: center; border-radius: 0.5rem; color: rgb(107 114 128); }
	:global(.icon-button:hover) { background: rgb(243 244 246); color: rgb(17 24 39); }
	:global(.dark .icon-button:hover) { background: rgb(31 41 55); color: rgb(243 244 246); }
	.field-label { display: block; margin-bottom: 0.25rem; font-size: 0.75rem; color: rgb(75 85 99); }
	:global(.dark) .field-label { color: rgb(209 213 219); }
	.field-input { width: 100%; border: 1px solid rgb(229 231 235); border-radius: 0.5rem; background: transparent; padding: 0.5rem 0.75rem; font-size: 0.875rem; outline: none; }
	:global(.dark) .field-input { border-color: rgb(55 65 81); }
	.field-input:focus { border-color: rgb(107 114 128); }
</style>
