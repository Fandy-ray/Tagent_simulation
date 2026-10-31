<script lang="ts">
	import { onMount } from 'svelte';

	import { listNotebookKnowledge } from '$lib/apis/opennotebook';
	import {
		KIND_LABEL,
		findSource,
		sourceKey,
		type KnowledgeCollection,
		type KnowledgeFile
	} from '$lib/data/knowledge';

	type LoadStatus = 'loading' | 'ready' | 'offline';

	type Props = {
		value?: string;
		selectedKeys?: string[];
		collections?: KnowledgeCollection[];
		placeholder?: string;
		onSubmit?: () => void;
	};

	let {
		value = $bindable(''),
		selectedKeys = $bindable<string[]>([]),
		collections = $bindable<KnowledgeCollection[]>([]),
		placeholder = '输入主题，或选择笔记本与来源',
		onSubmit = () => {}
	}: Props = $props();

	let open = $state(false);
	let loadStatus = $state<LoadStatus>('loading');
	let expanded = $state<Record<string, boolean>>({});

	const query = $derived(value.trim().toLowerCase());

	const matchesSource = (collection: KnowledgeCollection, file: KnowledgeFile) => {
		if (!query) {
			return true;
		}

		return (
			collection.name.toLowerCase().includes(query) ||
			collection.description.toLowerCase().includes(query) ||
			file.title.toLowerCase().includes(query) ||
			KIND_LABEL[file.kind].includes(query)
		);
	};

	const filtered = $derived(
		collections.flatMap((collection) => {
			const files = collection.files.filter((file) => matchesSource(collection, file));
			const notebookMatches =
				!query ||
				collection.name.toLowerCase().includes(query) ||
				collection.description.toLowerCase().includes(query);

			if (!notebookMatches && files.length === 0) {
				return [];
			}

			return [{ collection, files: notebookMatches && !query ? collection.files : files }];
		})
	);

	const selectedSources = $derived(
		selectedKeys
			.map((key) => findSource(key, collections))
			.filter((item): item is NonNullable<typeof item> => item !== null)
	);

	const isSelected = (key: string) => selectedKeys.includes(key);

	const notebookSelection = (collection: KnowledgeCollection, files = collection.files) => {
		// 下载失败的来源点不了，整本勾选时也跳过它们
		const keys = files
			.filter((file) => file.status !== 'failed')
			.map((file) => sourceKey(collection.id, file.id));
		const count = keys.filter((key) => selectedKeys.includes(key)).length;

		return {
			keys,
			count,
			all: keys.length > 0 && count === keys.length,
			some: count > 0 && count < keys.length
		};
	};

	const toggleSource = (collection: KnowledgeCollection, file: KnowledgeFile) => {
		if (file.status === 'failed') {
			return;
		}

		const key = sourceKey(collection.id, file.id);

		selectedKeys = isSelected(key)
			? selectedKeys.filter((item) => item !== key)
			: [...selectedKeys, key];
	};

	const toggleNotebook = (collection: KnowledgeCollection, files: KnowledgeFile[]) => {
		const { keys, all } = notebookSelection(collection, files);

		if (keys.length === 0) {
			return;
		}

		selectedKeys = all
			? selectedKeys.filter((key) => !keys.includes(key))
			: [...new Set([...selectedKeys, ...keys])];
	};

	const removeSource = (key: string) => {
		selectedKeys = selectedKeys.filter((item) => item !== key);
	};

	const toggleExpanded = (collectionId: string) => {
		expanded = {
			...expanded,
			[collectionId]: !expanded[collectionId]
		};
	};

	const keepMenu = (event: MouseEvent) => {
		event.preventDefault();
	};

	const isExpanded = (collectionId: string) => query.length > 0 || expanded[collectionId] !== false;

	const loadNotebooks = async () => {
		const controller = new AbortController();
		const timer = window.setTimeout(() => controller.abort(), 4000);

		loadStatus = 'loading';

		try {
			const next = await listNotebookKnowledge(controller.signal);
			collections = next;
			expanded = Object.fromEntries(next.map((collection) => [collection.id, true]));
			loadStatus = 'ready';
		} catch {
			collections = [];
			loadStatus = 'offline';
		} finally {
			window.clearTimeout(timer);
		}
	};

	onMount(() => {
		void loadNotebooks();
	});
</script>

<div class="relative w-full max-w-md text-left">
	<div
		class="rounded-2xl border border-white/[0.08] bg-white/[0.035] transition focus-within:border-white/20 hover:border-white/[0.12]"
	>
		{#if selectedSources.length > 0}
			<div class="flex flex-wrap gap-1 px-2 pt-2">
				{#each selectedSources as item (sourceKey(item.collection.id, item.file.id))}
					<button
						type="button"
						class="inline-flex max-w-full items-center gap-1 rounded-md bg-white/[0.08] px-2 py-0.5 text-[11px] text-gray-200 transition hover:bg-white/[0.14]"
						onclick={() => removeSource(sourceKey(item.collection.id, item.file.id))}
					>
						<span class="truncate">
							{item.collection.name} · {item.file.title}
						</span>
						<span class="text-gray-500" aria-hidden="true">×</span>
					</button>
				{/each}
			</div>
		{/if}

		<div class="relative">
			<input
				class="w-full bg-transparent px-3 py-2 pr-9 text-sm text-gray-100 outline-none placeholder:text-gray-500"
				{placeholder}
				maxlength="100"
				role="combobox"
				aria-expanded={open}
				aria-autocomplete="list"
				aria-controls="knowledge-combobox-list"
				aria-haspopup="tree"
				bind:value
				onfocus={() => {
					open = true;
				}}
				oninput={() => {
					open = true;
				}}
				onkeydown={(event) => {
					if (event.key === 'Enter') {
						// 中文输入法按回车是在确认候选词，不是提交。少了这句，
						// 打「排队论」的过程中就会莫名其妙开始出题。
						if (event.isComposing) {
							return;
						}

						open = false;
						onSubmit();
					}

					if (event.key === 'Escape') {
						open = false;
					}
				}}
				onblur={() => {
					window.setTimeout(() => {
						open = false;
					}, 150);
				}}
			/>

			<svg
				class="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-gray-500"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				aria-hidden="true"
			>
				<path d="m6 9 6 6 6-6"></path>
			</svg>
		</div>
	</div>

	{#if open}
		<div
			id="knowledge-combobox-list"
			class="bg-gray-850 absolute inset-x-0 top-[calc(100%+6px)] z-20 max-h-72 overflow-y-auto rounded-xl border border-white/10 py-1 shadow-lg"
			tabindex="-1"
			role="tree"
			onmousedown={keepMenu}
		>
			{#if loadStatus === 'loading'}
				<div class="px-3 py-2 text-sm text-gray-500">正在读取笔记本…</div>
			{:else if loadStatus === 'offline'}
				<div class="px-3 py-2 text-sm text-gray-500">
					无法连接 OpenNoteBook，请先启动笔记本服务后再选来源。
				</div>
			{:else if collections.length === 0}
				<div class="px-3 py-2 text-sm text-gray-500">
					笔记本里还没有内容。请先在笔记本模块创建笔记本并添加来源。
				</div>
			{:else}
				{#each filtered as group (group.collection.id)}
					{@const notebook = notebookSelection(group.collection, group.files)}
					{@const opened = isExpanded(group.collection.id)}

					<div role="group" aria-label={group.collection.name}>
						<div class="flex items-center gap-1 px-1.5 py-0.5">
							<button
								type="button"
								class="flex size-7 shrink-0 items-center justify-center rounded-md text-gray-300 transition hover:bg-white/[0.08]"
								role="checkbox"
								aria-checked={notebook.all ? 'true' : notebook.some ? 'mixed' : 'false'}
								aria-label={`选择笔记本 ${group.collection.name}`}
								onclick={() => toggleNotebook(group.collection, group.files)}
							>
								<span
									class={`flex size-4 items-center justify-center rounded-sm border text-[10px] leading-none ${
										notebook.all || notebook.some
											? 'border-white bg-white text-black'
											: 'border-white/30'
									}`}
								>
									{notebook.all ? '✓' : notebook.some ? '–' : ''}
								</span>
							</button>

							<button
								type="button"
								class="flex min-w-0 flex-1 items-center justify-between rounded-md px-1.5 py-1.5 text-left transition hover:bg-white/[0.06]"
								aria-expanded={opened}
								onclick={() => toggleExpanded(group.collection.id)}
							>
								<span class="min-w-0">
									<span class="block truncate text-sm text-gray-100">
										{group.collection.name}
									</span>
									<span class="block text-[11px] text-gray-500">
										笔记本 · {group.collection.files.length} 个来源
									</span>
								</span>

								<svg
									class={`size-3.5 shrink-0 text-gray-500 transition ${opened ? 'rotate-180' : ''}`}
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									aria-hidden="true"
								>
									<path d="m6 9 6 6 6-6"></path>
								</svg>
							</button>
						</div>

						{#if opened}
							{#if group.files.length === 0}
								<div class="px-3 py-1.5 pl-9 text-[11px] text-gray-500">该笔记本暂无来源</div>
							{:else}
								{#each group.files as file (file.id)}
									{@const key = sourceKey(group.collection.id, file.id)}
									{@const checked = isSelected(key)}

									<button
										type="button"
										class="flex w-full items-center gap-2 py-1.5 pr-3 pl-9 text-left transition hover:bg-white/[0.06]"
										role="treeitem"
										aria-selected={checked}
										disabled={file.status === 'failed'}
										title={file.status === 'failed'
											? '该来源下载失败，无法作为本次材料；请在 OpenNoteBook 中重试'
											: undefined}
										onclick={() => toggleSource(group.collection, file)}
									>
										<span
											class={`flex size-4 shrink-0 items-center justify-center rounded-sm border text-[10px] leading-none ${
												checked ? 'border-white bg-white text-black' : 'border-white/30'
											}`}
										>
											{checked ? '✓' : ''}
										</span>

										<span class="min-w-0 flex-1">
											<span class="block truncate text-sm text-gray-200">
												{file.title}
											</span>
											<span
												class={`text-[11px] ${file.status === 'failed' ? 'text-red-400' : 'text-gray-500'}`}
											>
												{file.status === 'failed' ? '下载失败' : KIND_LABEL[file.kind]}
											</span>
										</span>
									</button>
								{/each}
							{/if}
						{/if}
					</div>
				{/each}

				{#if filtered.length === 0}
					<div class="px-3 py-2 text-sm text-gray-500">
						没有匹配的笔记本或来源，将按输入主题出题
					</div>
				{/if}
			{/if}
		</div>
	{/if}
</div>
