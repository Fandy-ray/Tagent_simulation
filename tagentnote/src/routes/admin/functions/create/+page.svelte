<script lang="ts">
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import FunctionEditor from '$lib/components/admin/Functions/FunctionEditor.svelte';
	import { loadMockFunctions, saveMockFunctions, type FunctionType } from '$lib/data/mockFunctions';

	let mounted = $state(false);
	let notice = $state('');

	onMount(() => {
		mounted = true;
	});

	const saveHandler = (payload: {
		id: string;
		name: string;
		meta: { description: string };
		content: string;
		type: FunctionType;
	}) => {
		const existing = loadMockFunctions();
		if (existing.some((item) => item.id === payload.id)) {
			notice = `函数 ID「${payload.id}」已存在，请换一个名称或 ID`;
			return;
		}

		saveMockFunctions([
			{
				id: payload.id,
				name: payload.name,
				type: payload.type,
				owner: 'TAgent Team',
				email: 'admin@tagent.local',
				description: payload.meta.description,
				version: '0.1.0',
				isActive: false,
				isGlobal: false,
				fundingUrl: '',
				content: payload.content,
				valves: {}
			},
			...existing
		]);

		void goto(resolve('/admin/functions'));
	};
</script>

<svelte:head><title>新函数 | 管理员面板</title></svelte:head>

{#if mounted}
	<div class="flex h-[calc(100dvh-6.5rem)] min-h-0 flex-col overflow-hidden px-3 pb-4 sm:px-4">
		{#if notice}
			<p
				class="mb-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-200"
				role="alert"
			>
				{notice}
			</p>
		{/if}

		<FunctionEditor onSave={saveHandler} />
	</div>
{/if}
