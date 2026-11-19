<script lang="ts">
	import { resolve } from '$app/paths';

	import { KIND_LABEL, type Citation } from '$lib/data/knowledge';

	type Props = {
		citations?: Citation[];
		label?: string;
	};

	let { citations = [], label = '引用' }: Props = $props();

	const displayTitle = (citation: Citation) => {
		const title = citation.title.trim();
		// 论文：标签已经写了「论文」，前面不再挂「参考文献」，直接是题目 · 期刊出处
		const notebook = citation.kind === 'paper' ? '' : citation.collectionName.trim();
		const same = title && notebook && title === notebook;
		const head = same ? notebook : [notebook, title].filter(Boolean).join(' · ');
		return citation.locator ? `${head} · ${citation.locator}` : head;
	};

	// 论文链到期刊官网，新窗口打开；教材没有可以打开的页面
	const isExternal = (citation: Citation) => /^https?:\/\//i.test(citation.href);
</script>

<!-- eslint-disable svelte/no-navigation-without-resolve -- external citation URLs are intentionally preserved. -->

{#if citations.length > 0}
	<div class="qa-citations mt-3 space-y-1.5">
		<div class="text-[11px] font-medium tracking-wide text-gray-500">
			{label}
		</div>
		<div class="flex flex-col gap-1">
			{#each citations as citation (citation.id)}
				{#if citation.href}
					<!-- External journal URLs intentionally bypass resolve(); internal citation paths are resolved above. -->
					<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
					<a
						href={isExternal(citation) ? citation.href : resolve(citation.href)}
						target={isExternal(citation) ? '_blank' : undefined}
						rel={isExternal(citation) ? 'noopener noreferrer' : undefined}
						title={citation.snippet}
						class="group inline-flex max-w-full items-center gap-2 rounded-lg px-1 py-0.5 text-sm text-sky-300 transition hover:bg-white/[0.04] hover:text-sky-200"
					>
						<span class="shrink-0 text-[10px] text-gray-500">
							{KIND_LABEL[citation.kind]}
						</span>
						<span class="min-w-0 truncate underline decoration-sky-500/40 underline-offset-2">
							{displayTitle(citation)}
						</span>
					</a>
				{:else}
					<span
						title={citation.snippet}
						class="inline-flex max-w-full items-center gap-2 px-1 py-0.5 text-sm text-gray-300"
					>
						<span class="shrink-0 text-[10px] text-gray-500">
							{KIND_LABEL[citation.kind]}
						</span>
						<span class="min-w-0 truncate">{displayTitle(citation)}</span>
					</span>
				{/if}
			{/each}
		</div>
	</div>
{/if}
