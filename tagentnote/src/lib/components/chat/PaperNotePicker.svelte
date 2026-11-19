<script lang="ts">
	import type { KnowledgeCollection } from '$lib/data/knowledge';
	import type { PaperNoteReference } from '$lib/data/paperWorkflow';

	type Props = {
		collections?: KnowledgeCollection[];
		selected?: PaperNoteReference[];
		onChange?: (notes: PaperNoteReference[]) => void;
	};

	let {
		collections = [],
		selected = $bindable<PaperNoteReference[]>([]),
		onChange = () => {}
	}: Props = $props();

	let open = $state(false);
	let query = $state('');
	let rootEl = $state<HTMLDivElement | null>(null);
	let openUp = $state(false);

	const noteGroups = $derived(
		collections
			.map((collection) => ({
				collection,
				notes: collection.files.filter(
					(file) =>
						file.kind === 'note' &&
						(!query.trim() || file.title.toLowerCase().includes(query.trim().toLowerCase()))
				)
			}))
			.filter((group) => group.notes.length > 0)
	);

	const noteKey = (notebookId: string, noteId: string) => `${notebookId}||${noteId}`;
	const isSelected = (key: string) => selected.some((note) => note.key === key);

	const toggleNote = (
		collection: KnowledgeCollection,
		note: KnowledgeCollection['files'][number]
	) => {
		const key = noteKey(collection.id, note.id);
		if (isSelected(key)) {
			selected = selected.filter((item) => item.key !== key);
		} else {
			selected = [
				...selected,
				{
					key,
					notebookId: collection.id,
					notebookName: collection.name,
					noteId: note.id,
					title: note.title
				}
			];
		}
		onChange(selected);
	};

	const removeNote = (key: string) => {
		selected = selected.filter((item) => item.key !== key);
		onChange(selected);
	};

	const toggleOpen = () => {
		if (!open) {
			const rect = rootEl?.getBoundingClientRect();
			openUp = Boolean(rect && rect.bottom + 240 > window.innerHeight);
		}
		open = !open;
	};
</script>

<div class="relative mt-2" bind:this={rootEl}>
	<div class="flex flex-wrap items-center gap-1.5">
		{#each selected as note (note.key)}
			<button
				type="button"
				class="inline-flex max-w-full items-center gap-1 rounded-md border border-[color:var(--qa-active,var(--m3-primary))]/15 bg-[var(--qa-active,var(--m3-primary))]/[0.08] px-2 py-1 text-[11px] text-[color:var(--qa-active,var(--m3-primary))] hover:bg-[var(--qa-active,var(--m3-primary))]/[0.14]"
				title={`${note.notebookName} · ${note.title}`}
				onclick={() => removeNote(note.key)}
			>
				<span class="max-w-56 truncate">笔记 · {note.title}</span>
				<span class="text-[color:var(--qa-active,var(--m3-primary))]/60" aria-hidden="true">×</span>
			</button>
		{/each}

		<button
			type="button"
			class="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11px] text-gray-400 transition hover:border-[color:var(--qa-active,var(--m3-primary))]/30 hover:bg-white/[0.06] hover:text-[color:var(--qa-active,var(--m3-primary))]"
			aria-expanded={open}
			onclick={toggleOpen}
		>
			<span aria-hidden="true">↗</span>
			{selected.length > 0 ? '继续选择笔记' : '从笔记本选择笔记'}
		</button>
	</div>

	{#if open}
		<div
			class={`bg-gray-850 absolute left-0 z-40 w-full max-w-lg min-w-64 rounded-xl border border-white/10 p-2 shadow-2xl ${openUp ? 'bottom-[calc(100%+6px)]' : 'top-[calc(100%+6px)]'}`}
		>
			<div class="mb-2 flex items-center gap-2">
				<input
					class="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/20 px-2.5 py-1.5 text-xs text-gray-100 outline-none placeholder:text-gray-600 focus:border-[color:var(--qa-active,var(--m3-primary))]/50"
					placeholder="搜索笔记"
					bind:value={query}
				/>
				<button
					type="button"
					class="shrink-0 rounded-lg px-2 py-1.5 text-xs text-gray-400 hover:bg-white/10 hover:text-white"
					onclick={() => (open = false)}
				>
					完成
				</button>
			</div>

			<div class="max-h-52 overflow-y-auto">
				{#if collections.length === 0}
					<div class="px-2 py-3 text-xs text-gray-500">暂无可用笔记本</div>
				{:else if noteGroups.length === 0}
					<div class="px-2 py-3 text-xs text-gray-500">没有匹配的笔记，请先在笔记本中创建笔记</div>
				{:else}
					{#each noteGroups as group (group.collection.id)}
						<div class="mb-2 last:mb-0">
							<div
								class="px-2 py-1 text-[11px] font-medium text-[color:var(--qa-active,var(--m3-primary))]/80"
							>
								{group.collection.name}
							</div>
							{#each group.notes as note (note.id)}
								{@const key = noteKey(group.collection.id, note.id)}
								<button
									type="button"
									class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-gray-200 hover:bg-white/[0.08]"
									onclick={() => toggleNote(group.collection, note)}
								>
									<span
										class={`flex size-4 shrink-0 items-center justify-center rounded border text-[10px] ${isSelected(key) ? 'border-[color:var(--qa-active,var(--m3-primary))] bg-[var(--qa-active,var(--m3-primary))] text-[color:var(--qa-on-active,var(--m3-on-primary))]' : 'border-white/25 text-transparent'}`}
									>
										✓
									</span>
									<span class="min-w-0 truncate">{note.title}</span>
								</button>
							{/each}
						</div>
					{/each}
				{/if}
			</div>
		</div>
	{/if}
</div>
