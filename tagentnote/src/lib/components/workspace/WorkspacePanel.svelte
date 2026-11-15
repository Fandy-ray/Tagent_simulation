<script lang="ts">
	import { resolve } from '$app/paths';
	import type { Snippet } from 'svelte';

	type Props = {
		title: string;
		count?: number | null;
		searchPlaceholder?: string;
		query?: string;
		primaryAction?: string;
		secondaryAction?: string;
		emptyTitle: string;
		emptyHint: string;
		footerTitle?: string;
		footerDesc?: string;
		footerHref?: string;
		onPrimary?: () => void;
		onSecondary?: () => void;
		children?: Snippet;
	};

	let {
		title,
		count = null,
		searchPlaceholder = '搜索',
		query = $bindable(''),
		primaryAction = '',
		secondaryAction = '',
		emptyTitle,
		emptyHint,
		footerTitle = '',
		footerDesc = '',
		footerHref = '',
		onPrimary = () => {},
		onSecondary = () => {},
		children
	}: Props = $props();
</script>

<!-- eslint-disable svelte/no-navigation-without-resolve -- configured external footer URLs are intentional. -->

<div class="flex h-full min-h-0 flex-col">
	<div class="flex items-center justify-between gap-3 px-0.5 pt-1">
		<div class="flex items-center gap-2 text-xl font-medium text-white">
			<span>{title}</span>
			{#if count !== null}
				<span class="text-lg font-medium text-gray-500">{count}</span>
			{/if}
		</div>

		<div class="flex items-center gap-1.5">
			{#if secondaryAction}
				<button
					type="button"
					class="bg-gray-850 rounded-xl px-3 py-1.5 text-xs font-medium text-gray-200 transition hover:bg-gray-800"
					onclick={onSecondary}
				>
					{secondaryAction}
				</button>
			{/if}
			{#if primaryAction}
				<button
					type="button"
					class="inline-flex items-center gap-1 rounded-xl bg-white px-2 py-1.5 text-xs font-medium text-black transition hover:bg-gray-200"
					onclick={onPrimary}
				>
					<span class="text-sm leading-none">+</span>
					<span class="hidden md:inline">{primaryAction}</span>
				</button>
			{/if}
		</div>
	</div>

	<div class="workspace-surface border-gray-850/30 mt-3 flex-1 overflow-y-auto rounded-3xl border bg-gray-900">
		<div class="flex items-center gap-2 border-b border-white/[0.04] px-3.5 py-2.5">
			<svg
				class="size-3.5 shrink-0 text-gray-500"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				aria-hidden="true"
			>
				<circle cx="11" cy="11" r="7"></circle>
				<path d="m20 20-3.5-3.5"></path>
			</svg>
			<input
				class="w-full bg-transparent text-sm text-gray-100 outline-none placeholder:text-gray-500"
				placeholder={searchPlaceholder}
				bind:value={query}
			/>
		</div>

		{#if children}
			{@render children()}
		{:else}
			<div class="flex flex-col items-center justify-center px-6 py-20 text-center">
				<div class="mb-3 text-3xl">😕</div>
				<div class="mb-1 text-lg font-medium text-white">{emptyTitle}</div>
				<div class="max-w-md text-xs text-gray-500">{emptyHint}</div>
			</div>
		{/if}
	</div>

	{#if footerTitle}
		<div class="mt-10 mb-4">
			<div class="mb-1 text-xl font-medium text-white">由 Open WebUI 社区开发</div>
			<!-- External footer URLs intentionally bypass resolve(); internal paths are resolved above. -->
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
			<a
				class="hover:bg-gray-850 mb-2 flex w-full items-center justify-between rounded-xl px-3.5 py-1.5 transition"
				href={footerHref
					? /^https?:\/\//i.test(footerHref)
						? footerHref
						: resolve(footerHref)
					: '#'}
				target={footerHref ? '_blank' : undefined}
				rel={footerHref ? 'noreferrer' : undefined}
			>
				<div>
					<div class="font-medium text-gray-100">{footerTitle}</div>
					<div class="text-sm text-gray-500">{footerDesc}</div>
				</div>
				<svg
					class="size-4 text-gray-500"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					aria-hidden="true"
				>
					<path d="m9 18 6-6-6-6"></path>
				</svg>
			</a>
		</div>
	{/if}
</div>
