<script lang="ts">
	import { page } from '$app/state';
	import { asset } from '$app/paths';
	const remoteSensingPdf = 'https://pubs.usgs.gov/circ/1525/cir1525.pdf';
</script>

<svelte:head><title>问小轨 · 空天资料库</title></svelte:head>

{#if page.url.searchParams.get('document') === 'usgs-1525'}
	<main
		class="space-theme flex h-dvh flex-col bg-[var(--m3-background)] text-[color:var(--m3-on-surface)]"
	>
		<header class="flex flex-wrap items-center justify-between gap-3 p-4">
			<h1>用遥感监测矿区与生态恢复</h1>
			<a href={remoteSensingPdf} target="_blank" rel="noopener noreferrer">打开 USGS 原始 PDF ↗</a>
		</header>
		<iframe
			class="min-h-0 w-full flex-1"
			src={asset('/resources/usgs-circular-1525.pdf')}
			title="USGS 遥感监测技术报告"
		></iframe>
	</main>
{/if}
