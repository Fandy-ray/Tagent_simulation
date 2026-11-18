<script lang="ts">
	import type { Snippet } from 'svelte';

	type Props = {
		title: string;
		subtitle?: string;
		saving?: boolean;
		onBack?: () => void;
		onSave?: () => void;
		saveLabel?: string;
		children?: Snippet;
	};

	let {
		title,
		subtitle = '',
		saving = false,
		onBack = () => {},
		onSave = () => {},
		saveLabel = '保存并创建',
		children
	}: Props = $props();
</script>

<div class="mx-auto w-full max-w-3xl px-1 pb-10">
	<div class="mb-4 flex items-center justify-between gap-3 pt-2">
		<div>
			<button
				type="button"
				class="mb-2 text-xs text-gray-500 transition hover:text-white"
				onclick={onBack}
			>
				← 返回
			</button>
			<h1 class="text-xl font-medium text-white">{title}</h1>
			{#if subtitle}
				<p class="mt-1 text-sm text-gray-500">{subtitle}</p>
			{/if}
		</div>
		<button
			type="button"
			class="rounded-xl bg-white px-3 py-1.5 text-sm font-medium text-black transition hover:bg-gray-200 disabled:opacity-50"
			disabled={saving}
			onclick={onSave}
		>
			{saving ? '保存中…' : saveLabel}
		</button>
	</div>

	<div class="workspace-surface border-gray-850/30 space-y-4 rounded-3xl border bg-gray-900 p-4 md:p-5">
		{#if children}
			{@render children()}
		{/if}
	</div>
</div>
