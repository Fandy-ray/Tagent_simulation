<script lang="ts">
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import {
		loadMockFunctions,
		saveMockFunctions,
		toFunctionId,
		type FunctionType,
		type MockFunction
	} from '$lib/data/mockFunctions';

	let functions = $state<MockFunction[]>([]);
	let query = $state('');
	let selectedType = $state('');
	let viewOption = $state('');
	let menuFor = $state<string | null>(null);
	let editingFunction = $state<MockFunction | null>(null);
	let editorOpen = $state(false);
	let editorMode = $state<'create' | 'edit'>('create');
	let name = $state('');
	let id = $state('');
	let type = $state<FunctionType>('pipe');
	let description = $state('');
	let content = $state('');
	let version = $state('0.1.0');
	let isActive = $state(true);
	let isGlobal = $state(false);
	let valvesText = $state('{}');
	let fundingUrl = $state('');
	let formError = $state('');
	let deleteTarget = $state<MockFunction | null>(null);
	let valvesTarget = $state<MockFunction | null>(null);
	let valvesDraft = $state('{}');
	let importOpen = $state(false);
	let importUrl = $state('');
	let importError = $state('');
	let importFile = $state<HTMLInputElement | null>(null);
	let notice = $state('');
	let shiftHeld = $state(false);

	const filteredItems = $derived(
		functions
			.filter((func) => selectedType === '' || func.type === selectedType)
			.filter(
				(func) =>
					!query.trim() ||
					`${func.name} ${func.id} ${func.owner} ${func.email} ${func.description}`
						.toLowerCase()
						.includes(query.trim().toLowerCase())
			)
			.filter(
				(func) =>
					viewOption === '' ||
					(viewOption === 'created' ? func.owner === 'TAgent Team' : func.owner !== 'TAgent Team')
			)
			.sort((a, b) => a.type.localeCompare(b.type) || a.name.localeCompare(b.name))
	);

	const toId = toFunctionId;

	function loadFunctions() {
		functions = loadMockFunctions();
	}

	function saveFunctions(next: MockFunction[]) {
		functions = next;
		saveMockFunctions(next);
	}

	function notify(message: string) {
		notice = message;
		setTimeout(() => {
			if (notice === message) notice = '';
		}, 2600);
	}

	function openEditor(func?: MockFunction, clone = false) {
		editorOpen = true;
		editingFunction = func ?? null;
		editorMode = func && !clone ? 'edit' : 'create';
		name = clone && func ? `${func.name} (副本)` : (func?.name ?? '');
		id = clone && func ? `${func.id}-clone` : (func?.id ?? '');
		type = func?.type ?? 'pipe';
		description = func?.description ?? '';
		content = func?.content ?? '';
		version = func?.version ?? '0.1.0';
		isActive = clone ? false : (func?.isActive ?? true);
		isGlobal = clone ? false : (func?.isGlobal ?? false);
		fundingUrl = func?.fundingUrl ?? '';
		valvesText = JSON.stringify(func?.valves ?? {}, null, 2);
		formError = '';
		menuFor = null;
	}

	function saveFunction() {
		const cleanName = name.trim();
		const cleanId = (id || toId(cleanName)).trim();
		if (!cleanName || !cleanId) {
			formError = '请填写函数名称和 ID';
			return;
		}
		if (!/^[a-z0-9][a-z0-9_-]*$/.test(cleanId)) {
			formError = 'ID 仅支持小写字母、数字、短横线和下划线';
			return;
		}
		if (functions.some((func) => func.id === cleanId && func.id !== editingFunction?.id)) {
			formError = '该函数 ID 已存在';
			return;
		}
		let valves: Record<string, string>;
		try {
			const parsed: unknown = JSON.parse(valvesText || '{}');
			if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error();
			valves = Object.fromEntries(
				Object.entries(parsed).map(([key, value]) => [key, String(value)])
			);
		} catch {
			formError = 'Valves 必须是有效的 JSON 对象';
			return;
		}
		const saved: MockFunction = {
			id: cleanId,
			name: cleanName,
			type,
			owner: editingFunction?.owner ?? 'TAgent Team',
			email: editingFunction?.email ?? 'admin@tagent.local',
			description: description.trim(),
			version: version.trim() || '0.1.0',
			isActive,
			isGlobal: ['filter', 'action'].includes(type) && isGlobal,
			fundingUrl: fundingUrl.trim(),
			content,
			valves
		};
		saveFunctions(
			editorMode === 'edit'
				? functions.map((func) => (func.id === editingFunction?.id ? saved : func))
				: [saved, ...functions]
		);
		editingFunction = null;
		editorOpen = false;
		notify(editorMode === 'edit' ? '函数已保存' : '函数已创建');
	}

	function deleteFunction(func: MockFunction) {
		saveFunctions(functions.filter((item) => item.id !== func.id));
		deleteTarget = null;
		menuFor = null;
		notify('函数已删除');
	}

	function exportFunctions(items: MockFunction[], filename: string) {
		const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const anchor = document.createElement('a');
		anchor.href = url;
		anchor.download = filename;
		anchor.click();
		URL.revokeObjectURL(url);
		menuFor = null;
		notify('函数已导出');
	}

	function cloneFunction(func: MockFunction) {
		openEditor(func, true);
	}

	function toggleActive(func: MockFunction) {
		saveFunctions(
			functions.map((item) => (item.id === func.id ? { ...item, isActive: !item.isActive } : item))
		);
	}

	function toggleGlobal(func: MockFunction) {
		if (!['filter', 'action'].includes(func.type)) return;
		saveFunctions(
			functions.map((item) => (item.id === func.id ? { ...item, isGlobal: !item.isGlobal } : item))
		);
	}

	function saveValves() {
		if (!valvesTarget) return;
		try {
			const parsed: unknown = JSON.parse(valvesDraft || '{}');
			if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error();
			saveFunctions(
				functions.map((func) =>
					func.id === valvesTarget?.id
						? {
								...func,
								valves: Object.fromEntries(
									Object.entries(parsed).map(([key, value]) => [key, String(value)])
								)
							}
						: func
				)
			);
			valvesTarget = null;
			notify('Valves 设置已保存');
		} catch {
			notify('Valves 必须是有效的 JSON 对象');
		}
	}

	function importJSON(value: unknown) {
		const incoming = Array.isArray(value) ? value : [value];
		const imported: MockFunction[] = [];
		for (const entry of incoming) {
			if (!entry || typeof entry !== 'object') continue;
			const source =
				'function' in entry && entry.function && typeof entry.function === 'object'
					? (entry.function as Record<string, unknown>)
					: (entry as Record<string, unknown>);
			const meta =
				source.meta && typeof source.meta === 'object'
					? (source.meta as Record<string, unknown>)
					: {};
			const newName = String(source.name ?? 'Imported Function');
			const newId = String(source.id ?? toId(newName));
			if (
				!newId ||
				functions.some((func) => func.id === newId) ||
				imported.some((func) => func.id === newId)
			)
				continue;
			const rawType = String(source.type ?? 'pipe');
			imported.push({
				id: newId,
				name: newName,
				type: (['pipe', 'filter', 'action'].includes(rawType) ? rawType : 'pipe') as FunctionType,
				owner: 'TAgent Team',
				email: 'admin@tagent.local',
				description: String(meta.description ?? source.description ?? ''),
				version: String((meta.manifest as Record<string, unknown> | undefined)?.version ?? '0.1.0'),
				isActive: false,
				isGlobal: false,
				fundingUrl: String(
					(meta.manifest as Record<string, unknown> | undefined)?.funding_url ?? ''
				),
				content: String(source.content ?? ''),
				valves: {}
			});
		}
		if (imported.length) saveFunctions([...imported, ...functions]);
		importOpen = false;
		importError = '';
		importUrl = '';
		notify(
			imported.length ? `已导入 ${imported.length} 个函数` : '没有可导入的函数（ID 可能已存在）'
		);
	}

	async function importFromUrl() {
		const url = importUrl.trim();
		if (!/^https?:\/\//i.test(url)) {
			importError = '请输入有效的 http 或 https 链接';
			return;
		}
		try {
			const response = await fetch(url);
			if (!response.ok) throw new Error('无法读取此链接');
			importJSON(await response.json());
		} catch {
			importError = '链接导入失败，请检查地址或直接导入 JSON 文件';
		}
	}

	function handleFile(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		const reader = new FileReader();
		reader.onload = () => {
			try {
				importJSON(JSON.parse(String(reader.result)));
			} catch {
				importError = 'JSON 文件格式无效';
				importOpen = true;
			}
			input.value = '';
		};
		reader.readAsText(file);
	}

	function supportFunction(func: MockFunction) {
		if (func.fundingUrl) window.open(func.fundingUrl, '_blank', 'noopener,noreferrer');
	}

	$effect(() => {
		loadFunctions();
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Shift') shiftHeld = true;
		};
		const onKeyUp = (event: KeyboardEvent) => {
			if (event.key === 'Shift') shiftHeld = false;
		};
		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);
		window.addEventListener('blur', () => (shiftHeld = false));
		return () => {
			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);
		};
	});

	const PIPE_PLACEHOLDER = 'class Pipe:\n    def pipe(self, body: dict):\n        return body';
</script>

<svelte:head><title>函数 | 管理员面板</title></svelte:head>

<section class="space-y-3 px-3 pb-8 text-gray-900 sm:px-4 dark:text-gray-100">
	<header class="flex flex-wrap items-center justify-between gap-2 py-1">
		<h1 class="flex items-center gap-2 px-0.5 text-lg font-medium">
			函数 <span class="text-sm text-gray-500">{filteredItems.length}</span>
		</h1>
		<div class="flex items-center gap-1.5">
			<input
				bind:this={importFile}
				type="file"
				accept=".json,application/json"
				class="hidden"
				onchange={handleFile}
			/>
			<button
				class="dark:bg-gray-850 rounded-xl bg-gray-50 px-3 py-1.5 text-xs font-medium transition hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800"
				onclick={() => importFile?.click()}>导入 JSON</button
			>
			{#if functions.length}<button
					class="dark:bg-gray-850 rounded-xl bg-gray-50 px-3 py-1.5 text-xs font-medium transition hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800"
					onclick={() => exportFunctions(functions, `functions-export-${Date.now()}.json`)}
					>导出全部</button
				>{/if}
			<div class="relative">
				<button
					class="flex items-center gap-1 rounded-xl bg-gray-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-gray-700 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
					onclick={() => (menuFor = menuFor === '__add' ? null : '__add')}
					aria-expanded={menuFor === '__add'}
					><span class="text-base leading-none">+</span> 新建函数</button
				>
				{#if menuFor === '__add'}<div
						class="dark:bg-gray-850 absolute top-9 right-0 z-20 w-44 rounded-xl border border-gray-200 bg-white p-1 shadow-lg dark:border-gray-800"
					>
						<button
							class="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
							onclick={() => {
								menuFor = null;
								void goto(resolve('/admin/functions/create'));
							}}>新函数</button
						><button
							class="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
							onclick={() => {
								importOpen = true;
								menuFor = null;
							}}>从链接导入</button
						>
					</div>{/if}
			</div>
		</div>
	</header>

	<div
		class="rounded-2xl border border-gray-200 bg-white py-2 dark:border-gray-800 dark:bg-gray-900"
	>
		<div class="flex items-center gap-2 px-3.5 pb-2">
			<svg viewBox="0 0 20 20" fill="currentColor" class="size-4 shrink-0 text-gray-500"
				><path
					fill-rule="evenodd"
					d="M9 3.5a5.5 5.5 0 1 0 3.445 9.788l3.328 3.328a.75.75 0 1 0 1.06-1.06l-3.328-3.329A5.5 5.5 0 0 0 9 3.5ZM5 9a4 4 0 1 1 8 0 4 4 0 0 1-8 0Z"
					clip-rule="evenodd"
				/></svg
			>
			<input
				class="w-full bg-transparent py-1 text-sm outline-none placeholder:text-gray-500"
				bind:value={query}
				placeholder="搜索函数"
				aria-label="搜索函数"
			/>
			{#if query}<button
					class="rounded-full p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
					onclick={() => (query = '')}
					aria-label="清除搜索">×</button
				>{/if}
		</div>
		<div class="flex gap-1 overflow-x-auto px-3 text-xs">
			<div class="dark:bg-gray-850/70 flex shrink-0 gap-1 rounded-full bg-gray-100/70 p-0.5">
				{#each [{ key: '', label: '全部' }, { key: 'created', label: '我创建的' }, { key: 'shared', label: '共享给我' }] as option (option.key)}<button
						class="rounded-full px-3 py-1 transition {viewOption === option.key
							? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white'
							: 'text-gray-500 hover:text-gray-800 dark:hover:text-gray-200'}"
						onclick={() => (viewOption = option.key)}>{option.label}</button
					>{/each}
			</div>
			<div class="dark:bg-gray-850/70 flex shrink-0 gap-1 rounded-full bg-gray-100/70 p-0.5">
				{#each [{ key: '', label: '全部类型' }, { key: 'pipe', label: 'Pipe' }, { key: 'filter', label: 'Filter' }, { key: 'action', label: 'Action' }] as option (option.key)}<button
						class="rounded-full px-3 py-1 transition {selectedType === option.key
							? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-white'
							: 'text-gray-500 hover:text-gray-800 dark:hover:text-gray-200'}"
						onclick={() => (selectedType = option.key)}>{option.label}</button
					>{/each}
			</div>
		</div>

		{#if filteredItems.length}
			<div class="my-2 grid gap-1 px-3 lg:grid-cols-2 lg:gap-2">
				{#each filteredItems as func (func.id)}
					<article
						class="flex w-full items-center gap-3 rounded-xl px-2 py-2 transition hover:bg-gray-50 dark:hover:bg-white/5"
					>
						<button
							class="min-w-0 flex-1 cursor-pointer text-left"
							onclick={() => openEditor(func)}
						>
							<div class="flex min-w-0 items-center gap-1.5">
								<span
									class="shrink-0 rounded-sm bg-gray-500/15 px-1 text-[10px] font-semibold text-gray-600 uppercase dark:text-gray-200"
									>{func.type}</span
								>
								<span class="truncate text-sm font-medium">{func.name}</span>
								{#if func.version}<span class="shrink-0 text-xs font-medium text-gray-500"
										>v{func.version}</span
									>{/if}
							</div>
							<div class="flex min-w-0 gap-2 px-1">
								<span class="shrink-0 text-xs text-gray-500" title={func.email}
									>由 {func.owner}</span
								><span class="truncate text-xs text-gray-500">{func.description}</span>
							</div>
						</button>
						<div class="flex shrink-0 items-center gap-0.5">
							{#if shiftHeld}<button
									class="rounded-lg p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40"
									onclick={() => (deleteTarget = func)}
									aria-label="删除函数"
									title="删除函数"
									><svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
										><path
											fill-rule="evenodd"
											d="M8.5 2a1.5 1.5 0 0 0-1.42 1H5a.75.75 0 0 0 0 1.5h10a.75.75 0 0 0 0-1.5h-2.08A1.5 1.5 0 0 0 11.5 2h-3ZM6 6h8l-.56 9.04A2 2 0 0 1 11.45 17h-2.9a2 2 0 0 1-1.99-1.96L6 6Zm2.25 2a.75.75 0 0 0-1.5 0v5a.75.75 0 0 0 1.5 0V8Zm4.5 0a.75.75 0 0 0-1.5 0v5a.75.75 0 0 0 1.5 0V8Z"
											clip-rule="evenodd"
										/></svg
									></button
								>
							{:else}
								{#if func.fundingUrl}<button
										class="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
										onclick={() => supportFunction(func)}
										aria-label="支持此函数"
										title="支持"
										><svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
											><path
												d="M9.65 2.55a.75.75 0 0 1 .7 0c2.07 1.04 3.9 2.7 5.01 4.86 1.12 2.17 1.44 4.75.49 7.28-.47 1.25-1.37 2.2-2.52 2.76-1.13.56-2.42.7-3.75.51-2.62-.37-5.42-2.1-7.32-4.68a.75.75 0 0 1 .6-1.19c2.05-.03 3.57-.58 4.55-1.56.97-.97 1.54-2.5 1.56-4.56a.75.75 0 0 1 .68-.72Z"
											/></svg
										></button
									>{/if}
								<button
									class="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
									onclick={() => {
										valvesTarget = func;
										valvesDraft = JSON.stringify(func.valves, null, 2);
									}}
									aria-label="Valves 设置"
									title="Valves"
									><svg
										viewBox="0 0 20 20"
										fill="none"
										stroke="currentColor"
										stroke-width="1.5"
										class="size-4"
										><path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M11.5 3.5a4 4 0 0 0-4.8 4.8L3 12a2 2 0 1 0 2.8 2.8l3.7-3.7a4 4 0 0 0 4.8-4.8l-2.1 2.1-2.8-2.8 2.1-2.1Z"
										/></svg
									></button
								>
								<div class="relative">
									<button
										class="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
										onclick={() => (menuFor = menuFor === func.id ? null : func.id)}
										aria-label="更多函数操作"
										aria-expanded={menuFor === func.id}>···</button
									>{#if menuFor === func.id}<div
											class="dark:bg-gray-850 absolute top-9 right-0 z-20 w-44 rounded-xl border border-gray-200 bg-white p-1 shadow-lg dark:border-gray-800"
										>
											<button
												class="w-full rounded-lg px-3 py-1.5 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
												onclick={() => openEditor(func)}>编辑</button
											><button
												class="w-full rounded-lg px-3 py-1.5 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
												onclick={() => cloneFunction(func)}>克隆</button
											><button
												class="w-full rounded-lg px-3 py-1.5 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
												onclick={() => exportFunctions([func], `function-${func.id}-export.json`)}
												>导出</button
											><button
												class="w-full rounded-lg px-3 py-1.5 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
												onclick={() => {
													navigator.clipboard?.writeText(func.id);
													menuFor = null;
													notify('函数 ID 已复制');
												}}>复制 ID</button
											>{#if ['filter', 'action'].includes(func.type)}<div
													class="my-1 border-t border-gray-100 dark:border-gray-800"
												></div>
												<label class="flex items-center justify-between px-3 py-2 text-sm"
													><span>全局启用</span><input
														type="checkbox"
														checked={func.isGlobal}
														onchange={() => toggleGlobal(func)}
													/></label
												>{/if}
											<div class="my-1 border-t border-gray-100 dark:border-gray-800"></div>
											<button
												class="w-full rounded-lg px-3 py-1.5 text-left text-sm text-red-600 hover:bg-gray-50 dark:hover:bg-gray-800"
												onclick={() => {
													deleteTarget = func;
													menuFor = null;
												}}>删除</button
											>
										</div>{/if}
								</div>
							{/if}
							<button
								class="relative h-[1.125rem] w-8 shrink-0 rounded-full px-1 outline outline-1 outline-gray-700 transition {func.isActive
									? 'bg-emerald-700'
									: 'bg-transparent'}"
								role="switch"
								aria-label={`启用 ${func.name}`}
								aria-checked={func.isActive}
								onclick={() => toggleActive(func)}
								><span
									class="block size-3 rounded-full bg-white transition-transform {func.isActive
										? 'translate-x-3'
										: ''}"
								></span></button
							>
						</div>
					</article>
				{/each}
			</div>
		{:else}
			<div class="flex min-h-56 flex-col items-center justify-center px-4 py-10 text-center">
				<span class="mb-3 text-3xl text-gray-400">∅</span>
				<h2 class="text-base font-medium">没有找到函数</h2>
				<p class="mt-1 text-xs text-gray-500">调整搜索词或筛选条件试试。</p>
			</div>
		{/if}
	</div>
	<p class="text-right text-[10px] text-gray-400">函数列表、启用状态和配置均为本地 mock 数据。</p>
	{#if notice}<div
			class="fixed right-5 bottom-5 z-[70] rounded-xl bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg dark:bg-white dark:text-gray-900"
			role="status"
		>
			{notice}
		</div>{/if}
</section>

{#if editorOpen}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget) editingFunction = null;
			editorOpen = false;
		}}
	>
		<div
			class="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white text-gray-900 shadow-2xl dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100"
			role="dialog"
			aria-modal="true"
			aria-labelledby="function-editor-title"
			tabindex="-1"
		>
			<header
				class="flex items-center justify-between border-b border-gray-100 px-5 py-4 dark:border-gray-800"
			>
				<div>
					<h2 id="function-editor-title" class="text-lg font-semibold">
						{editorMode === 'edit' ? '编辑函数' : '新建函数'}
					</h2>
					<p class="mt-0.5 text-xs text-gray-500">编辑描述、源代码和函数配置。</p>
				</div>
				<button
					class="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
					onclick={() => {
						editingFunction = null;
						editorOpen = false;
					}}
					aria-label="关闭编辑器">×</button
				>
			</header>
			<div class="flex-1 space-y-3 overflow-y-auto p-5">
				<div class="grid gap-3 sm:grid-cols-2">
					<label class="space-y-1"
						><span class="text-xs font-medium">函数名称</span><input
							class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-gray-700"
							bind:value={name}
							oninput={() => {
								if (editorMode === 'create') id = toId(name);
							}}
							placeholder="例如：Research Assistant"
						/></label
					><label class="space-y-1"
						><span class="text-xs font-medium">函数 ID</span><input
							class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-gray-700"
							bind:value={id}
							placeholder="research-assistant"
						/></label
					><label class="space-y-1"
						><span class="text-xs font-medium">类型</span><select
							class="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none dark:border-gray-700 dark:bg-gray-900"
							bind:value={type}
							><option value="pipe">Pipe</option><option value="filter">Filter</option><option
								value="action">Action</option
							></select
						></label
					><label class="space-y-1"
						><span class="text-xs font-medium">版本</span><input
							class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-gray-700"
							bind:value={version}
							placeholder="0.1.0"
						/></label
					>
				</div>
				<label class="block space-y-1"
					><span class="text-xs font-medium">描述</span><textarea
						class="min-h-16 w-full resize-y rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-gray-700"
						bind:value={description}
						placeholder="简要说明函数用途"></textarea></label
				>
				<label class="block space-y-1"
					><span class="text-xs font-medium">Python 源代码</span><textarea
						class="min-h-64 w-full resize-y rounded-lg border border-gray-200 bg-[#111827] px-3 py-2 font-mono text-xs text-gray-100 outline-none focus:border-blue-500"
						bind:value={content}
						spellcheck="false"
						placeholder={PIPE_PLACEHOLDER}></textarea></label
				>
				<label class="block space-y-1"
					><span class="text-xs font-medium">Valves JSON 配置</span><textarea
						class="min-h-24 w-full resize-y rounded-lg border border-gray-200 bg-transparent px-3 py-2 font-mono text-xs outline-none focus:border-blue-500 dark:border-gray-700"
						bind:value={valvesText}
						spellcheck="false"></textarea></label
				>
				<label class="block space-y-1"
					><span class="text-xs font-medium">Funding URL（可选）</span><input
						class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-gray-700"
						bind:value={fundingUrl}
						placeholder="https://"
					/></label
				>
				<div class="flex flex-wrap gap-5">
					<label class="flex items-center gap-2 text-sm"
						><input type="checkbox" bind:checked={isActive} />启用函数</label
					>{#if ['filter', 'action'].includes(type)}<label class="flex items-center gap-2 text-sm"
							><input type="checkbox" bind:checked={isGlobal} />全局启用</label
						>{/if}
				</div>
				{#if formError}<p class="text-sm text-red-600" role="alert">{formError}</p>{/if}
			</div>
			<footer
				class="flex justify-end gap-2 border-t border-gray-100 px-5 py-3 dark:border-gray-800"
			>
				<button
					class="rounded-lg px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
					onclick={() => {
						editingFunction = null;
						editorOpen = false;
					}}>取消</button
				><button
					class="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white dark:bg-white dark:text-gray-900"
					onclick={saveFunction}>保存函数</button
				>
			</footer>
		</div>
	</div>
{/if}

{#if deleteTarget}
	<div
		class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget) deleteTarget = null;
		}}
	>
		<div
			class="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-5 shadow-2xl dark:border-gray-700 dark:bg-gray-900"
			role="dialog"
			aria-modal="true"
			aria-labelledby="delete-function-title"
			tabindex="-1"
		>
			<h2 id="delete-function-title" class="text-lg font-semibold">删除函数？</h2>
			<p class="mt-2 text-sm text-gray-500">
				确定删除 <span class="font-medium text-gray-900 dark:text-white">{deleteTarget.name}</span
				>？此操作无法撤销。
			</p>
			<div class="mt-5 flex justify-end gap-2">
				<button
					class="rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800"
					onclick={() => (deleteTarget = null)}>取消</button
				><button
					class="rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700"
					onclick={() => deleteFunction(deleteTarget!)}>删除</button
				>
			</div>
		</div>
	</div>
{/if}

{#if valvesTarget}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget) valvesTarget = null;
		}}
	>
		<div
			class="w-full max-w-lg rounded-2xl border border-gray-200 bg-white p-5 shadow-2xl dark:border-gray-700 dark:bg-gray-900"
			role="dialog"
			aria-modal="true"
			aria-labelledby="valves-title"
			tabindex="-1"
		>
			<h2 id="valves-title" class="text-lg font-semibold">Valves 设置</h2>
			<p class="mt-1 text-xs text-gray-500">{valvesTarget.name} · 配置以 JSON mock 保存</p>
			<textarea
				class="mt-4 min-h-48 w-full rounded-lg border border-gray-200 bg-[#111827] p-3 font-mono text-xs text-gray-100 outline-none focus:border-blue-500"
				bind:value={valvesDraft}
				spellcheck="false"></textarea>
			<div class="mt-4 flex justify-end gap-2">
				<button
					class="rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800"
					onclick={() => (valvesTarget = null)}>取消</button
				><button
					class="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white dark:bg-white dark:text-gray-900"
					onclick={saveValves}>保存配置</button
				>
			</div>
		</div>
	</div>
{/if}

{#if importOpen}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget) importOpen = false;
		}}
	>
		<div
			class="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-5 shadow-2xl dark:border-gray-700 dark:bg-gray-900"
			role="dialog"
			aria-modal="true"
			aria-labelledby="import-function-title"
			tabindex="-1"
		>
			<h2 id="import-function-title" class="text-lg font-semibold">从链接导入函数</h2>
			<p class="mt-1 text-xs text-gray-500">输入可直接返回函数 JSON 的链接。</p>
			<input
				class="mt-4 w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-blue-500 dark:border-gray-700"
				bind:value={importUrl}
				placeholder="https://example.com/function.json"
			/>
			<div
				class="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
			>
				<p class="font-medium">安全提示</p>
				<p class="mt-1">
					函数可能执行任意代码。仅导入可信来源的内容；导入的 mock 函数默认处于禁用状态。
				</p>
			</div>
			{#if importError}<p class="mt-2 text-xs text-red-600" role="alert">{importError}</p>{/if}
			<div class="mt-5 flex justify-end gap-2">
				<button
					class="rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800"
					onclick={() => {
						importOpen = false;
						importError = '';
					}}>取消</button
				><button
					class="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white dark:bg-white dark:text-gray-900"
					onclick={importFromUrl}>导入</button
				>
			</div>
		</div>
	</div>
{/if}
