<script lang="ts">
	import { Handle, Position, type NodeProps } from '@xyflow/svelte';

	type OverviewMessage = {
		id: string;
		role: 'user' | 'assistant';
		content: string;
		model?: string;
		favorite?: boolean;
	};

	type NodeData = {
		message: OverviewMessage;
		modelName?: string;
		userName?: string;
	};

	let { data }: NodeProps & { data: NodeData } = $props();

	const preview = $derived(
		data.message.content.trim()
			? data.message.content.length > 80
				? `${data.message.content.slice(0, 80)}…`
				: data.message.content
			: '（空消息）'
	);
</script>

<div
	class="group h-20 w-60 rounded-xl border border-gray-800 bg-black px-4 py-3 shadow-md"
	title={data.message.content}
>
	{#if data.message.role === 'user'}
		<div class="flex w-full">
			<div
				class="flex size-5 shrink-0 -translate-y-px items-center justify-center rounded-full bg-gray-700 text-[9px] font-semibold text-white"
			>
				U
			</div>
			<div class="ml-2 min-w-0 flex-1">
				<div class="line-clamp-1 text-xs font-medium text-white">{data.userName ?? '我'}</div>
				<div class="mt-0.5 line-clamp-2 text-xs text-gray-500">{preview}</div>
			</div>
		</div>
	{:else}
		<div class="flex w-full">
			<div
				class="flex size-5 shrink-0 -translate-y-px items-center justify-center rounded-full bg-white text-[11px] font-black text-black"
			>
				T
			</div>
			<div class="ml-2 min-w-0 flex-1">
				<div class="flex items-center justify-between gap-1">
					<div class="line-clamp-1 text-xs font-medium text-white">
						{data.modelName ?? data.message.model ?? '助手'}
					</div>
					{#if data.message.favorite}
						<svg
							class="size-3 shrink-0 fill-red-500 stroke-red-500"
							viewBox="0 0 24 24"
							aria-hidden="true"
						>
							<path
								stroke-width="2.5"
								d="M12 21s-6.7-4.35-9.33-7.6C.8 11.2 1.1 7.9 3.4 6.2c2-1.5 4.7-.9 6.1 1 .5.8 1.1 1.6 2.5 1.6s2-0.8 2.5-1.6c1.4-1.9 4.1-2.5 6.1-1 2.3 1.7 2.6 5 .73 7.2C18.7 16.65 12 21 12 21z"
							></path>
						</svg>
					{/if}
				</div>
				<div class="mt-0.5 line-clamp-2 text-xs text-gray-500">{preview}</div>
			</div>
		</div>
	{/if}

	<Handle
		type="target"
		position={Position.Top}
		class="!h-2 !w-2 !rounded-full !border-0 !bg-gray-700"
	/>
	<Handle
		type="source"
		position={Position.Bottom}
		class="!h-2 !w-2 !rounded-full !border-0 !bg-gray-700"
	/>
</div>
