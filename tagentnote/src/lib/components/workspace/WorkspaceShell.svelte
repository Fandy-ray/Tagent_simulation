<script lang="ts">
	import { resolve } from '$app/paths';
	import type { Snippet } from 'svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import ViewSelector from './common/ViewSelector.svelte';

	type Props = {
		title: string;
		count?: number | null;
		query?: string;
		searchPlaceholder?: string;
		viewOption?: string;
		showViewSelector?: boolean;
		primaryHref?: string;
		primaryLabel?: string;
		onPrimary?: () => void;
		importLabel?: string;
		exportLabel?: string;
		onImport?: () => void;
		onExport?: () => void;
		filters?: Snippet;
		toolbarEnd?: Snippet;
		children?: Snippet;
		footer?: Snippet;
		emptyTitle?: string;
		emptyHint?: string;
		showEmpty?: boolean;
	};

	let {
		title,
		count = null,
		query = $bindable(''),
		searchPlaceholder = '搜索',
		viewOption = $bindable(''),
		showViewSelector = true,
		primaryHref = '',
		primaryLabel = '',
		onPrimary = () => {},
		importLabel = '',
		exportLabel = '',
		onImport = () => {},
		onExport = () => {},
		filters,
		toolbarEnd,
		children,
		footer,
		emptyTitle = '未找到内容',
		emptyHint = '请尝试调整您的搜索词或过滤器以找到您需要的内容。',
		showEmpty = false
	}: Props = $props();
</script>

<div class="flex h-full min-h-0 flex-col">
	<div class="mt-1.5 mb-3 flex flex-col gap-1 px-1">
		<div class="flex items-center justify-between">
			<div class="flex shrink-0 items-center gap-2 px-0.5 text-xl font-medium">
				<div>{title}</div>
				{#if count !== null}
					<div class="text-lg font-medium text-gray-500">{count}</div>
				{/if}
			</div>
			<div class="flex w-full items-center justify-end gap-1.5">
				{#if importLabel}
					<button
						type="button"
						class="bg-gray-850 flex min-h-9 items-center rounded-lg px-3 text-sm leading-none font-medium whitespace-nowrap text-gray-200 transition hover:bg-gray-800"
						onclick={onImport}
					>
						{importLabel}
					</button>
				{/if}
				{#if exportLabel}
					<button
						type="button"
						class="bg-gray-850 flex items-center rounded-lg px-2 py-1 text-xs leading-none font-medium text-gray-200 transition hover:bg-gray-800"
						onclick={onExport}
					>
						{exportLabel}
					</button>
				{/if}
				{#if primaryLabel}
					{#if primaryHref}
						<a
							class="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-white px-3 text-sm leading-none font-medium whitespace-nowrap text-black transition hover:bg-gray-200"
							href={resolve(primaryHref)}
						>
							<Plus className="size-3" />
							<span>{primaryLabel}</span>
						</a>
					{:else}
						<button
							type="button"
							class="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-white px-3 text-sm leading-none font-medium whitespace-nowrap text-black transition hover:bg-gray-200"
							onclick={onPrimary}
						>
							<Plus className="size-3" />
							<span>{primaryLabel}</span>
						</button>
					{/if}
				{/if}
			</div>
		</div>
	</div>

	<div class="workspace-surface border-gray-850/30 rounded-3xl border bg-gray-900 py-2">
		<div class="flex w-full items-center space-x-2 px-3.5 py-0.5 pb-2">
			<div class="flex flex-1 items-center">
				<div class="mr-3 ml-1 self-center">
					<Search className="size-3.5" />
				</div>
				<input
					class="w-full rounded-r-xl bg-transparent py-1 text-sm text-gray-100 outline-none placeholder:text-gray-500"
					placeholder={searchPlaceholder}
					bind:value={query}
					aria-label={searchPlaceholder}
				/>
				{#if query}
					<div class="translate-y-[0.5px] self-center bg-transparent pl-1.5">
						<button
							type="button"
							class="rounded-full p-0.5 transition hover:bg-gray-800"
							aria-label="清除搜索"
							onclick={() => {
								query = '';
							}}
						>
							<XMark className="size-3" strokeWidth="2" />
						</button>
					</div>
				{/if}
			</div>
		</div>

		{#if showViewSelector || filters || toolbarEnd}
			<div class="relative z-20 flex w-full items-center gap-2 bg-transparent px-3">
				<div
					class="flex min-w-0 flex-1 scrollbar-none gap-0.5 overflow-x-auto rounded-full bg-transparent px-0.5 text-center text-sm whitespace-nowrap"
				>
					{#if showViewSelector}
						<ViewSelector
							bind:value={viewOption}
							onChange={(v) => {
								viewOption = v;
								if (typeof localStorage !== 'undefined') {
									localStorage.workspaceViewOption = v;
								}
							}}
						/>
					{/if}
					{#if filters}
						{@render filters()}
					{/if}
				</div>
				{#if toolbarEnd}
					<div class="relative z-30 shrink-0">{@render toolbarEnd()}</div>
				{/if}
			</div>
		{/if}

		{#if showEmpty}
			<div class="flex flex-col items-center justify-center px-6 py-16 text-center">
				<div class="mb-3 text-3xl">😕</div>
				<div class="mb-1 text-lg font-medium text-white">{emptyTitle}</div>
				<div class="max-w-md text-xs text-gray-500">{emptyHint}</div>
			</div>
		{:else if children}
			{@render children()}
		{/if}
	</div>

	{#if footer}
		{@render footer()}
	{/if}
</div>
