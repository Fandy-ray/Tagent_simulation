<script lang="ts">
	import type { ComponentProps } from 'svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import { listModels } from '$lib/data/workspaceResources';
	import Capabilities from '$lib/components/workspace/Models/Capabilities.svelte';
	import PromptSuggestions from '$lib/components/workspace/Models/PromptSuggestions.svelte';
	import AdvancedParams from '$lib/components/chat/Settings/Advanced/AdvancedParams.svelte';

	type SuggestionPrompt = { content: string; title: [string, string] };

	type Props = {
		show?: boolean;
		onSaved?: () => void;
	};
	let { show = $bindable(false), onSaved = () => {} }: Props = $props();

	let selectedTab = $state('defaults');
	let loading = $state(false);
	let notice = $state('');

	let defaultModelIds = $state<string[]>([]);
	let defaultPinnedModelIds = $state<string[]>([]);
	let defaultCapabilities = $state<Record<string, boolean | undefined>>({});
	let promptSuggestions = $state<SuggestionPrompt[]>([]);
	// 和 AdvancedParams 组件要的形状一致（reasoning_tags、custom_params 两项必有）
	type DefaultParams = NonNullable<ComponentProps<typeof AdvancedParams>['params']>;
	const emptyParams = (): DefaultParams => ({ reasoning_tags: null, custom_params: {} });
	let defaultParams = $state<DefaultParams>(emptyParams());

	let showPromptSuggestions = $state(false);
	let showDefaultCapabilities = $state(false);
	let showDefaultParams = $state(false);
	let showResetConfirm = $state(false);

	let selectedModelId = $state('');

	const models = $derived(listModels());

	const inform = (message: string) => {
		notice = message;
		setTimeout(() => (notice = ''), 2400);
	};

	$effect(() => {
		if (show) {
			const saved = localStorage.getItem('mock.models.config');
			if (saved) {
				try {
					const parsed = JSON.parse(saved);
					defaultModelIds = parsed.defaultModelIds ?? [];
					defaultPinnedModelIds = parsed.defaultPinnedModelIds ?? [];
					defaultCapabilities = parsed.defaultCapabilities ?? {};
					promptSuggestions = parsed.promptSuggestions ?? [];
					defaultParams = { ...emptyParams(), ...(parsed.defaultParams ?? {}) };
					return;
				} catch {
					/* ignore */
				}
			}
			defaultModelIds = [];
			defaultPinnedModelIds = [];
			defaultCapabilities = {};
			promptSuggestions = [];
			defaultParams = emptyParams();
		}
	});

	const addModel = (list: string[], id: string) =>
		id && !list.includes(id) ? [...list, id] : list;

	const submitHandler = () => {
		loading = true;
		localStorage.setItem(
			'mock.models.config',
			JSON.stringify({
				defaultModelIds,
				defaultPinnedModelIds,
				defaultCapabilities,
				promptSuggestions: promptSuggestions.filter((p) => p.content !== ''),
				defaultParams
			})
		);
		setTimeout(() => {
			loading = false;
			show = false;
			onSaved();
			inform('模型配置已保存（mock）');
		}, 450);
	};

	const resetAll = () => {
		localStorage.removeItem('mock.models.config');
		defaultModelIds = [];
		defaultPinnedModelIds = [];
		defaultCapabilities = {};
		promptSuggestions = [];
		defaultParams = emptyParams();
		showResetConfirm = false;
		onSaved();
		inform('已重置所有模型（mock）');
	};
</script>

<Modal size="lg" bind:show>
	<div>
		<div class="flex justify-between px-5 pt-4 pb-1.5 dark:text-gray-100">
			<h1 class="self-center text-lg font-medium">设置</h1>
			<button class="self-center" aria-label="关闭" onclick={() => (show = false)}>
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-5"
					><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" /></svg
				>
			</button>
		</div>

		<div class="flex w-full flex-col px-4 pb-4 lg:flex-row lg:space-x-4 dark:text-gray-200">
			<form
				class="flex w-full flex-col"
				onsubmit={(e) => {
					e.preventDefault();
					submitHandler();
				}}
			>
				<div class="flex w-full flex-col lg:flex-row lg:space-x-4">
					<div
						class="tabs flex max-w-full scrollbar-none flex-row gap-2.5 overflow-x-auto text-sm font-medium lg:w-40 lg:flex-none lg:flex-col lg:gap-1"
					>
						<button
							class="flex w-fit max-w-fit flex-1 items-center rounded-lg px-0.5 py-1 text-right transition {selectedTab ===
							'defaults'
								? ''
								: 'text-gray-300 hover:text-gray-700 dark:text-gray-600 dark:hover:text-white'}"
							type="button"
							onclick={() => (selectedTab = 'defaults')}
						>
							<svg
								class="mr-2 size-4 self-center"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.6"
								><path
									stroke-linecap="round"
									d="M4 7h10M18 7h2M4 17h2M10 17h10M4 12h4M12 12h8"
								/><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /><circle
									cx="10"
									cy="12"
									r="2"
								/></svg
							>
							<span class="self-center">默认值</span>
						</button>
						<button
							class="flex w-fit max-w-fit flex-1 items-center rounded-lg px-0.5 py-1 text-right transition {selectedTab ===
							'display'
								? ''
								: 'text-gray-300 hover:text-gray-700 dark:text-gray-600 dark:hover:text-white'}"
							type="button"
							onclick={() => (selectedTab = 'display')}
						>
							<svg
								class="mr-2 size-4 self-center"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.6"
								><path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z"
								/><path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
								/></svg
							>
							<span class="self-center">显示</span>
						</button>
					</div>

					<div class="mt-1 flex min-w-0 flex-1 flex-col">
						<div class="scrollbar-hidden h-full max-h-[30rem] overflow-x-hidden overflow-y-auto">
							{#if selectedTab === 'defaults'}
								<div>
									<div class="mb-1 flex justify-between">
										<div class="flex items-center gap-1 text-xs text-gray-500">
											<span>已选模型</span><svg
												class="size-3"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												stroke-width="1.5"
												><path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z"
												/></svg
											>
										</div>
									</div>
									<select
										class="w-full rounded-lg bg-transparent py-1 text-sm text-gray-500 outline-none"
										bind:value={selectedModelId}
										onchange={() => {
											defaultModelIds = addModel(defaultModelIds, selectedModelId);
											selectedModelId = '';
										}}
										aria-label="选择模型"
									>
										<option value="">选择模型</option>
										{#each models as model (model.id)}{#if !defaultModelIds.includes(model.id)}<option
													value={model.id}>{model.name}</option
												>{/if}{/each}
									</select>
									{#if defaultModelIds.length > 0}
										<div class="flex flex-col">
											{#each defaultModelIds as modelId, idx (modelId)}
												<div class="flex w-full items-center justify-between gap-2">
													<div class="flex-1 rounded-lg py-1 text-sm">
														{models.find((m) => m.id === modelId)?.name ?? modelId}
													</div>
													<button
														class="shrink-0 text-gray-500 hover:text-gray-300"
														type="button"
														aria-label="移除"
														onclick={() =>
															(defaultModelIds = defaultModelIds.filter((_, i) => i !== idx))}
														><svg
															class="size-3.5"
															viewBox="0 0 24 24"
															fill="none"
															stroke="currentColor"
															stroke-width="2"><path stroke-linecap="round" d="M5 12h14" /></svg
														></button
													>
												</div>
											{/each}
										</div>
									{:else}
										<div class="py-2 text-center text-xs text-gray-500">未选择任何模型</div>
									{/if}
								</div>

								<hr class="my-2.5 w-full border-gray-50 dark:border-gray-800/10" />

								<div>
									<div class="mb-1 flex justify-between">
										<div class="flex items-center gap-1 text-xs text-gray-500">
											<span>固定在侧边栏的模型</span><svg
												class="size-3"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												stroke-width="1.5"
												><path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z"
												/></svg
											>
										</div>
									</div>
									<select
										class="w-full rounded-lg bg-transparent py-1 text-sm text-gray-500 outline-none"
										bind:value={selectedModelId}
										onchange={() => {
											defaultPinnedModelIds = addModel(defaultPinnedModelIds, selectedModelId);
											selectedModelId = '';
										}}
										aria-label="选择固定模型"
									>
										<option value="">选择模型</option>
										{#each models as model (model.id)}{#if !defaultPinnedModelIds.includes(model.id)}<option
													value={model.id}>{model.name}</option
												>{/if}{/each}
									</select>
									{#if defaultPinnedModelIds.length > 0}
										<div class="flex flex-col">
											{#each defaultPinnedModelIds as modelId, idx (modelId)}
												<div class="flex w-full items-center justify-between gap-2">
													<div class="flex-1 rounded-lg py-1 text-sm">
														{models.find((m) => m.id === modelId)?.name ?? modelId}
													</div>
													<button
														class="shrink-0 text-gray-500 hover:text-gray-300"
														type="button"
														aria-label="移除"
														onclick={() =>
															(defaultPinnedModelIds = defaultPinnedModelIds.filter(
																(_, i) => i !== idx
															))}
														><svg
															class="size-3.5"
															viewBox="0 0 24 24"
															fill="none"
															stroke="currentColor"
															stroke-width="2"><path stroke-linecap="round" d="M5 12h14" /></svg
														></button
													>
												</div>
											{/each}
										</div>
									{:else}
										<div class="py-2 text-center text-xs text-gray-500">未选择任何模型</div>
									{/if}
								</div>

								<hr class="my-2.5 w-full border-gray-50 dark:border-gray-800/10" />

								<div>
									<button
										class="flex w-full items-center justify-between"
										type="button"
										onclick={() => (showPromptSuggestions = !showPromptSuggestions)}
									>
										<div class="text-xs font-medium text-gray-500">推荐提示词</div>
										<svg
											class="size-3 text-gray-500 transition"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="2"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												d={showPromptSuggestions ? 'm18 15-6-6-6 6' : 'm6 9 6 6 6-6'}
											/></svg
										>
									</button>
									{#if showPromptSuggestions}
										<div class="mt-2"><PromptSuggestions bind:promptSuggestions /></div>
									{/if}
								</div>

								<hr class="my-2.5 w-full border-gray-50 dark:border-gray-800/10" />

								<div>
									<button
										class="flex w-full items-center justify-between"
										type="button"
										onclick={() => (showDefaultCapabilities = !showDefaultCapabilities)}
									>
										<div class="text-xs font-medium text-gray-500">模型能力</div>
										<svg
											class="size-3 text-gray-500 transition"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="2"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												d={showDefaultCapabilities ? 'm18 15-6-6-6 6' : 'm6 9 6 6 6-6'}
											/></svg
										>
									</button>
									{#if showDefaultCapabilities}
										<div class="mt-2"><Capabilities bind:capabilities={defaultCapabilities} /></div>
									{/if}
								</div>

								<hr class="my-2.5 w-full border-gray-50 dark:border-gray-800/10" />

								<div>
									<button
										class="flex w-full items-center justify-between"
										type="button"
										onclick={() => (showDefaultParams = !showDefaultParams)}
									>
										<div class="text-xs font-medium text-gray-500">模型参数</div>
										<svg
											class="size-3 text-gray-500 transition"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="2"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												d={showDefaultParams ? 'm18 15-6-6-6 6' : 'm6 9 6 6 6-6'}
											/></svg
										>
									</button>
									{#if showDefaultParams}
										<div class="mt-2">
											<AdvancedParams admin={true} bind:params={defaultParams} />
										</div>
									{/if}
								</div>
							{:else}
								<div class="text-xs text-gray-500">模型顺序与显示方式配置为本地 mock 占位。</div>
							{/if}
						</div>

						<div class="flex items-center justify-between gap-1.5 pt-3 text-sm font-medium">
							<button
								class="text-sm font-normal text-gray-500 transition hover:text-gray-700 hover:underline dark:text-gray-500 dark:hover:text-gray-300"
								type="button"
								onclick={() => (showResetConfirm = true)}>重置</button
							>
							<button
								class="flex items-center gap-2 rounded-full bg-black px-3.5 py-1.5 text-sm font-medium whitespace-nowrap text-white transition hover:bg-gray-900 disabled:cursor-not-allowed dark:bg-white dark:text-black dark:hover:bg-gray-100"
								type="submit"
								disabled={loading}
								>保存{#if loading}<span
										class="size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
									></span>{/if}</button
							>
						</div>
					</div>
				</div>
			</form>
		</div>
	</div>
</Modal>

{#if showResetConfirm}
	<div
		class="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 p-4"
		role="presentation"
		onclick={(e) => {
			if (e.target === e.currentTarget) showResetConfirm = false;
		}}
	>
		<div
			class="w-full max-w-sm rounded-2xl border border-gray-800 bg-gray-900 p-5 text-white shadow-2xl"
			role="dialog"
			aria-modal="true"
			tabindex="-1"
		>
			<div class="text-base font-medium">重置所有模型</div>
			<p class="mt-2 text-sm text-gray-400">这将删除所有模型（包含自定义模型），且无法撤销。</p>
			<div class="mt-5 flex justify-end gap-2">
				<button
					class="rounded-lg px-3 py-1.5 text-sm text-gray-400 hover:bg-gray-800"
					type="button"
					onclick={() => (showResetConfirm = false)}>取消</button
				>
				<button
					class="rounded-lg bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-900"
					type="button"
					onclick={resetAll}>重置</button
				>
			</div>
		</div>
	</div>
{/if}

{#if notice}<div
		class="fixed right-5 bottom-5 z-[10001] rounded-xl bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg dark:bg-white dark:text-gray-900"
		role="status"
	>
		{notice}
	</div>{/if}
