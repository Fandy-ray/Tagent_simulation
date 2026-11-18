<script lang="ts">
	type Props = {
		onShare?: () => void;
		onDownload?: () => void;
		onCopy?: () => void;
		onArchive?: () => void;
		onAddTag?: (tag: string) => void;
		folders?: { id: string; name: string }[];
		onMoveToFolder?: (folderId: string | null) => void;
	};

	let {
		onShare = () => {},
		onDownload = () => {},
		onCopy = () => {},
		onArchive = () => {},
		onAddTag = () => {},
		folders = [],
		onMoveToFolder = () => {}
	}: Props = $props();

	let open = $state(false);
	let tagDraft = $state('');
	let tagEditing = $state(false);
	let moveOpen = $state(false);
	let rootEl = $state<HTMLDivElement | null>(null);
	let menuEl = $state<HTMLDivElement | null>(null);
	let menuStyle = $state('');

	const close = () => {
		open = false;
		tagEditing = false;
		tagDraft = '';
		moveOpen = false;
	};

	const run = (action: () => void) => {
		action();
		close();
	};

	const submitTag = () => {
		const tag = tagDraft.trim();
		if (!tag) return;
		onAddTag(tag);
		close();
	};

	const portal = (node: HTMLElement) => {
		const container = rootEl?.closest('.workspace-palette') ?? document.body;
		container.appendChild(node);
		return {
			destroy() {
				node.remove();
			}
		};
	};

	const updateMenuPosition = () => {
		if (!rootEl) return;
		const rect = rootEl.getBoundingClientRect();
		const width = 220;
		let left = rect.right - width;
		left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
		menuStyle = `position:fixed;left:${left}px;top:${rect.bottom + 4}px;width:${width}px;z-index:100;`;
	};

	const toggle = (event: MouseEvent) => {
		event.preventDefault();
		event.stopPropagation();
		open = !open;
		if (open) {
			updateMenuPosition();
		} else {
			tagEditing = false;
			tagDraft = '';
		}
	};

	$effect(() => {
		if (!open) return;

		updateMenuPosition();

		const onPointerDown = (event: PointerEvent) => {
			const target = event.target as Node;
			if (rootEl?.contains(target) || menuEl?.contains(target)) return;
			close();
		};
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Escape') close();
		};
		const onReposition = () => updateMenuPosition();

		const timer = window.setTimeout(() => {
			window.addEventListener('pointerdown', onPointerDown, true);
			window.addEventListener('keydown', onKeyDown);
			window.addEventListener('resize', onReposition);
			window.addEventListener('scroll', onReposition, true);
		}, 0);

		return () => {
			window.clearTimeout(timer);
			window.removeEventListener('pointerdown', onPointerDown, true);
			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('resize', onReposition);
			window.removeEventListener('scroll', onReposition, true);
		};
	});
</script>

<div class="relative" bind:this={rootEl}>
	<button
		type="button"
		class="hover:bg-gray-850 flex cursor-pointer rounded-xl px-2 py-2 text-gray-400 transition hover:text-white"
		aria-expanded={open}
		aria-haspopup="menu"
		title="更多"
		aria-label="更多"
		onclick={toggle}
	>
		<svg class="size-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
			<circle cx="5" cy="12" r="1.6"></circle>
			<circle cx="12" cy="12" r="1.6"></circle>
			<circle cx="19" cy="12" r="1.6"></circle>
		</svg>
	</button>
</div>

{#if open}
	<div
		bind:this={menuEl}
		use:portal
		class="workspace-menu-popup bg-gray-850 rounded-2xl border border-gray-800 px-1 py-1 text-white shadow-lg shadow-black/40"
		style={menuStyle}
		tabindex="-1"
		role="menu"
		onclick={(event) => event.stopPropagation()}
		onkeydown={(event) => {
			// Esc 要传到 window 上的监听去关菜单；焦点在菜单里时拦掉它，菜单就关不掉了
			if (event.key !== 'Escape') event.stopPropagation();
		}}
	>
		<button
			type="button"
			class="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-1.5 text-sm text-gray-100 transition hover:bg-gray-800"
			role="menuitem"
			onclick={() => run(onShare)}
		>
			<svg
				class="size-4 shrink-0"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="1.5"
				aria-hidden="true"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M9 8.25H7.5a2.25 2.25 0 0 0-2.25 2.25v9a2.25 2.25 0 0 0 2.25 2.25h9a2.25 2.25 0 0 0 2.25-2.25v-9A2.25 2.25 0 0 0 16.5 8.25H15m0-3-3-3m0 0-3 3m3-3V15"
				></path>
			</svg>
			分享
		</button>

		<button
			type="button"
			class="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-1.5 text-sm text-gray-100 transition hover:bg-gray-800"
			role="menuitem"
			onclick={() => run(onDownload)}
		>
			<svg
				class="size-4 shrink-0"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="1.5"
				aria-hidden="true"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M7.5 12 12 16.5m0 0L16.5 12M12 16.5V3"
				></path>
			</svg>
			下载
		</button>

		<button
			type="button"
			class="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-1.5 text-sm text-gray-100 transition hover:bg-gray-800"
			role="menuitem"
			onclick={() => run(onCopy)}
		>
			<svg
				class="size-4 shrink-0"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="1.5"
				aria-hidden="true"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184"
				></path>
			</svg>
			复制
		</button>

		<hr class="my-1 border-gray-800/80" />

		<button
			type="button"
			class="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-1.5 text-sm text-gray-100 transition hover:bg-gray-800"
			role="menuitem"
			onclick={() => run(onArchive)}
		>
			<svg
				class="size-4 shrink-0"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="1.5"
				aria-hidden="true"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="m20.25 7.5-.625 10.632a2.25 2.25 0 0 1-2.247 2.118H6.622a2.25 2.25 0 0 1-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125Z"
				></path>
			</svg>
			归档
		</button>

		<hr class="my-1 border-gray-800/80" />

		{#if folders.length > 0}
			{#if moveOpen}
				<div class="max-h-40 overflow-y-auto px-1 py-0.5">
					<button
						type="button"
						class="flex w-full rounded-xl px-3 py-1.5 text-left text-xs text-gray-400 hover:bg-gray-800 hover:text-white"
						onclick={() => run(() => onMoveToFolder(null))}
					>
						移出分组
					</button>
					{#each folders as folder (folder.id)}
						<button
							type="button"
							class="flex w-full truncate rounded-xl px-3 py-1.5 text-left text-xs text-gray-100 hover:bg-gray-800"
							onclick={() => run(() => onMoveToFolder(folder.id))}
						>
							{folder.name}
						</button>
					{/each}
				</div>
			{:else}
				<button
					type="button"
					class="flex w-full cursor-pointer items-center rounded-xl px-3 py-1.5 text-left text-sm text-gray-100 transition hover:bg-gray-800"
					role="menuitem"
					onclick={() => {
						moveOpen = true;
					}}
				>
					移至分组...
				</button>
			{/if}
			<hr class="my-1 border-gray-800/80" />
		{/if}

		{#if tagEditing}
			<form
				class="flex items-center gap-1 px-2 py-1"
				onsubmit={(event) => {
					event.preventDefault();
					submitTag();
				}}
			>
				<input
					class="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-sm text-gray-100 outline-none placeholder:text-gray-500 focus:border-white/20"
					placeholder="添加标签..."
					bind:value={tagDraft}
				/>
				<button
					type="submit"
					class="rounded-lg px-2 py-1 text-xs text-gray-300 transition hover:bg-gray-800 hover:text-white"
				>
					添加
				</button>
			</form>
		{:else}
			<button
				type="button"
				class="flex w-full cursor-pointer items-center rounded-xl px-3 py-1.5 text-left text-sm text-gray-100 transition hover:bg-gray-800"
				role="menuitem"
				onclick={() => {
					tagEditing = true;
				}}
			>
				添加标签...
			</button>
		{/if}
	</div>
{/if}
