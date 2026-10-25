<script lang="ts">
	import { fly } from 'svelte/transition';
	import Switch from '$lib/components/common/Switch.svelte';
	import { listSkills, listTools } from '$lib/data/workspaceResources';

	type ToolItem = { id: string; name: string; description?: string };
	type FilterItem = { id: string; name: string; description?: string };

	type Props = {
		webSearchEnabled?: boolean;
		imageGenerationEnabled?: boolean;
		codeInterpreterEnabled?: boolean;
		selectedToolIds?: string[];
		selectedFilterIds?: string[];
		tools?: ToolItem[];
		filters?: FilterItem[];
		onShowValves?: (payload: { type: 'tool' | 'filter'; id: string; name: string }) => void;
		onClose?: () => void;
		children?: import('svelte').Snippet;
	};

	const defaultTools: ToolItem[] = listTools().map((tool) => ({
		id: tool.id,
		name: tool.name,
		description: tool.description
	}));
	const defaultFilters: FilterItem[] = listSkills().map((skill) => ({
		id: skill.id,
		name: skill.name,
		description: skill.description
	}));

	let {
		webSearchEnabled = $bindable(false),
		imageGenerationEnabled = $bindable(false),
		codeInterpreterEnabled = $bindable(false),
		selectedToolIds = $bindable([] as string[]),
		selectedFilterIds = $bindable([] as string[]),
		tools = defaultTools,
		filters = defaultFilters,
		onShowValves = () => {},
		onClose = () => {},
		children
	}: Props = $props();

	let open = $state(false);
	let tab = $state<'main' | 'tools'>('main');
	let rootEl = $state<HTMLDivElement | null>(null);
	let menuEl = $state<HTMLDivElement | null>(null);
	let menuStyle = $state('');

	const sortedFilters = $derived(
		[...filters].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))
	);
	const toolEnabled = (id: string) => selectedToolIds.includes(id);
	const filterEnabled = (id: string) => selectedFilterIds.includes(id);

	const updateMenuPosition = () => {
		if (!rootEl) return;
		const rect = rootEl.getBoundingClientRect();
		const width = 288;
		const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
		menuStyle = `position:fixed;left:${left}px;bottom:${window.innerHeight - rect.top + 8}px;width:${width}px;z-index:120;`;
	};

	const close = () => {
		open = false;
		tab = 'main';
		onClose();
	};

	const toggleTool = (id: string) => {
		selectedToolIds = toolEnabled(id)
			? selectedToolIds.filter((item) => item !== id)
			: [...selectedToolIds, id];
	};

	const toggleFilter = (id: string) => {
		selectedFilterIds = filterEnabled(id)
			? selectedFilterIds.filter((item) => item !== id)
			: [...selectedFilterIds, id];
	};

	const portal = (node: HTMLElement) => {
		document.body.appendChild(node);
		return {
			destroy() {
				node.remove();
			}
		};
	};

	$effect(() => {
		if (!open) return;
		const onPointerDown = (event: PointerEvent) => {
			const target = event.target as Node;
			if (rootEl?.contains(target) || menuEl?.contains(target)) return;
			close();
		};
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Escape') close();
		};
		const timer = window.setTimeout(() => {
			window.addEventListener('pointerdown', onPointerDown, true);
			window.addEventListener('keydown', onKeyDown);
		}, 0);
		return () => {
			window.clearTimeout(timer);
			window.removeEventListener('pointerdown', onPointerDown, true);
			window.removeEventListener('keydown', onKeyDown);
		};
	});
</script>

<div class="relative" bind:this={rootEl}>
	<button
		type="button"
		id="integration-menu-button"
		class="flex size-8 items-center justify-center rounded-full text-white transition outline-none hover:bg-gray-800"
		title="集成与工具"
		aria-label="集成与工具"
		aria-expanded={open}
		onclick={(event) => {
			event.preventDefault();
			event.stopPropagation();
			open = !open;
			if (open) updateMenuPosition();
			else tab = 'main';
		}}
	>
		{#if children}
			{@render children()}
		{/if}
	</button>
</div>

{#if open}
	<div
		bind:this={menuEl}
		use:portal
		class="bg-gray-850 fixed z-[120] max-h-72 overflow-x-hidden overflow-y-auto rounded-2xl border border-gray-800 px-1 py-1 text-sm text-white shadow-lg"
		style={menuStyle}
		role="menu"
		aria-label="集成与工具"
	>
		{#if tab === 'main'}
			<div in:fly={{ x: -20, duration: 150 }}>
				<button
					type="button"
					class="flex w-full cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-1.5 text-left hover:bg-gray-800/50"
					onclick={() => {
						tab = 'tools';
					}}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.75"
						aria-hidden="true"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.05 1.095-.244 1.568-.575a2.25 2.25 0 0 0 .812-2.177l-.876-3.065a2.25 2.25 0 0 0-1.58-1.58l-3.065-.876a2.25 2.25 0 0 0-2.177.812 4.5 4.5 0 0 1-.575 1.568"
						/>
					</svg>
					<span class="flex w-full items-center justify-between">
						<span class="truncate"
							>工具 <span class="ml-0.5 text-gray-500">{tools.length}</span></span
						>
						<svg
							class="size-4 shrink-0 text-gray-500"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="1.8"
							aria-hidden="true"
							><path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="m8.25 4.5 7.5 7.5-7.5 7.5"
							/></svg
						>
					</span>
				</button>

				{#each sortedFilters as filter (filter.id)}
					<div
						class="group flex w-full items-center justify-between gap-2 rounded-xl px-3 py-1.5 hover:bg-gray-800/50"
					>
						<button
							type="button"
							class="flex min-w-0 flex-1 items-center gap-2 text-left"
							onclick={() => toggleFilter(filter.id)}
							title={filter.description ?? filter.name}
						>
							<svg
								class="size-4 shrink-0"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.75"
								aria-hidden="true"
								><path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z"
								/></svg
							>
							<span class="truncate">{filter.name}</span>
						</button>
						<button
							type="button"
							class="shrink-0 rounded-full p-1 text-gray-400 opacity-0 transition group-hover:opacity-100 hover:text-white focus:opacity-100"
							title="Valves 设置"
							aria-label={`${filter.name} Valves 设置`}
							onclick={(event) => {
								event.preventDefault();
								event.stopPropagation();
								onShowValves({ type: 'filter', id: filter.id, name: filter.name });
							}}
						>
							<svg
								class="size-4"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.6"
								aria-hidden="true"
								><path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M10.5 6h9.75M10.5 6a1.5 1.5 0 1 1-3 0m3 0a1.5 1.5 0 1 0-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-9.75 0h9.75"
								/></svg
							>
						</button>
						<Switch state={filterEnabled(filter.id)} onChange={() => toggleFilter(filter.id)} />
					</div>
				{/each}

				<div
					class="group flex w-full items-center justify-between gap-2 rounded-xl px-3 py-1.5 hover:bg-gray-800/50"
				>
					<button
						type="button"
						class="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left"
						title="联网搜索"
						onclick={() => (webSearchEnabled = !webSearchEnabled)}
					>
						<svg
							class="size-4 shrink-0"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="1.5"
							aria-hidden="true"
							><path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582"
							/></svg
						>
						<span class="truncate">联网搜索</span>
					</button>
					<Switch bind:state={webSearchEnabled} />
				</div>

				<div
					class="group flex w-full items-center justify-between gap-2 rounded-xl px-3 py-1.5 hover:bg-gray-800/50"
				>
					<button
						type="button"
						class="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left"
						title="图像"
						onclick={() => (imageGenerationEnabled = !imageGenerationEnabled)}
					>
						<svg
							class="size-4 shrink-0"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="1.5"
							aria-hidden="true"
							><path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z"
							/></svg
						>
						<span class="truncate">图像</span>
					</button>
					<Switch bind:state={imageGenerationEnabled} />
				</div>

				<div
					class="group flex w-full items-center justify-between gap-2 rounded-xl px-3 py-1.5 hover:bg-gray-800/50"
				>
					<button
						type="button"
						class="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left"
						title="代码解释器"
						onclick={() => (codeInterpreterEnabled = !codeInterpreterEnabled)}
					>
						<svg
							class="size-3.5 shrink-0"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="1.75"
							aria-hidden="true"
							><path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="m6.75 7.5 3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0 0 21 18V6a2.25 2.25 0 0 0-2.25-2.25H5.25A2.25 2.25 0 0 0 3 6v12a2.25 2.25 0 0 0 2.25 2.25Z"
							/></svg
						>
						<span class="truncate">代码解释器</span>
					</button>
					<Switch bind:state={codeInterpreterEnabled} />
				</div>
			</div>
		{:else}
			<div in:fly={{ x: 20, duration: 150 }}>
				<button
					type="button"
					class="flex w-full cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-1.5 text-left hover:bg-gray-800/50"
					onclick={() => (tab = 'main')}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.8"
						aria-hidden="true"
						><path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M15.75 19.5 8.25 12l7.5-7.5"
						/></svg
					>
					<span class="flex w-full items-center justify-between"
						><span>工具 <span class="ml-0.5 text-gray-500">{tools.length}</span></span></span
					>
				</button>

				{#each tools as tool (tool.id)}
					<div
						class="group flex w-full items-center justify-between gap-2 rounded-xl px-3 py-1.5 hover:bg-gray-800/50"
					>
						<button
							type="button"
							class="flex min-w-0 flex-1 items-center gap-2 text-left"
							onclick={() => toggleTool(tool.id)}
							title={tool.description ?? tool.name}
						>
							<svg
								class="size-4 shrink-0"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.75"
								aria-hidden="true"
								><path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.05 1.095-.244 1.568-.575a2.25 2.25 0 0 0 .812-2.177l-.876-3.065a2.25 2.25 0 0 0-1.58-1.58l-3.065-.876a2.25 2.25 0 0 0-2.177.812 4.5 4.5 0 0 1-.575 1.568"
								/></svg
							>
							<span class="min-w-0"
								><span class="block truncate">{tool.name}</span>{#if tool.description}<span
										class="block truncate text-xs text-gray-500">{tool.description}</span
									>{/if}</span
							>
						</button>
						<button
							type="button"
							class="shrink-0 rounded-full p-1 text-gray-400 opacity-0 transition group-hover:opacity-100 hover:text-white focus:opacity-100"
							title="Valves 设置"
							aria-label={`${tool.name} Valves 设置`}
							onclick={(event) => {
								event.preventDefault();
								event.stopPropagation();
								onShowValves({ type: 'tool', id: tool.id, name: tool.name });
							}}
						>
							<svg
								class="size-4"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.6"
								aria-hidden="true"
								><path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M10.5 6h9.75M10.5 6a1.5 1.5 0 1 1-3 0m3 0a1.5 1.5 0 1 0-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-9.75 0h9.75"
								/></svg
							>
						</button>
						<Switch state={toolEnabled(tool.id)} onChange={() => toggleTool(tool.id)} />
					</div>
				{:else}
					<p class="px-3 py-4 text-center text-xs text-gray-500">
						还没有可用工具，可在工作空间中创建。
					</p>
				{/each}
			</div>
		{/if}
	</div>
{/if}
