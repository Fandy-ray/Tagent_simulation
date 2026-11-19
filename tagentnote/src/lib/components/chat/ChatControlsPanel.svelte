<script lang="ts">
	import Controls from '$lib/components/chat/Controls/Controls.svelte';
	import type { MockMessage } from '$lib/components/chat/MockMessages.svelte';
	import { getI18nContext } from '$lib/i18n';

	const i18n = getI18nContext();

	type Props = {
		open?: boolean;
		params?: Record<string, unknown>;
		messages?: MockMessage[];
		modelName?: string;
		onClose?: () => void;
		onChange?: (params: Record<string, unknown>) => void;
		onSelectMessage?: (messageId: string) => void;
	};

	let {
		open = false,
		params = $bindable({}),
		messages = [],
		modelName = '',
		onClose = () => {},
		onChange = () => {},
		onSelectMessage = () => {}
	}: Props = $props();

	let activeTab = $state<'controls' | 'overview'>('controls');
	const hasMessages = $derived(messages.length > 0);

	$effect(() => {
		if (!hasMessages && activeTab === 'overview') {
			activeTab = 'controls';
		}
	});
</script>

{#if open}
	<aside
		class="bg-gray-850 shadow-[ -8px_0_24px_rgba(0,0,0,0.35)] relative z-30 flex h-full w-[min(100%,420px)] shrink-0 flex-col border-l border-white/5"
		id="controls-container"
		aria-label={$i18n.t('Chat Advanced Settings')}
	>
		<div class="bg-gray-850 flex h-full min-h-0 flex-col">
			<div class="flex shrink-0 items-center justify-between gap-2 px-2 pt-2 pb-2">
				<div class="flex min-w-0 flex-1 gap-1 overflow-x-auto">
					<button
						type="button"
						class={`rounded-lg px-2.5 py-1 text-sm whitespace-nowrap transition ${
							activeTab === 'controls'
								? 'bg-gray-800 font-medium text-white'
								: 'text-gray-400 hover:text-gray-300'
						}`}
						aria-pressed={activeTab === 'controls'}
						onclick={() => {
							activeTab = 'controls';
						}}
					>
						对话高级设置
					</button>
					{#if hasMessages}
						<button
							type="button"
							class={`rounded-lg px-2.5 py-1 text-sm whitespace-nowrap transition ${
								activeTab === 'overview'
									? 'bg-gray-800 font-medium text-white'
									: 'text-gray-400 hover:text-gray-300'
							}`}
							aria-pressed={activeTab === 'overview'}
							onclick={() => {
								activeTab = 'overview';
							}}
						>
							概述
						</button>
					{/if}
				</div>
				<button
					type="button"
					class="shrink-0 rounded-lg p-1 text-gray-400 transition hover:bg-gray-800 hover:text-gray-300"
					onclick={onClose}
					aria-label="关闭"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						class="size-4"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<div
				class={`bg-gray-850 min-h-0 flex-1 ${
					activeTab === 'controls' ? 'overflow-y-auto px-3 pt-1 pb-4' : 'overflow-hidden'
				}`}
			>
				{#if activeTab === 'overview'}
					<!-- 流程图（@xyflow）很少打开，点到「概览」才加载，别压在答疑页首屏里 -->
					{#await import('$lib/components/chat/Overview/Overview.svelte') then { default: Overview }}
						<Overview
							{messages}
							{modelName}
							currentMessageId={messages.at(-1)?.id ?? null}
							onNodeClick={onSelectMessage}
						/>
					{/await}
				{:else}
					<Controls embed={true} bind:params {onClose} {onChange} />
				{/if}
			</div>
		</div>
	</aside>
{/if}
