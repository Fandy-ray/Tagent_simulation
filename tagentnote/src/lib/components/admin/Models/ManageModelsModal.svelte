<script lang="ts">
	import Modal from '$lib/components/common/Modal.svelte';

	type Props = {
		show?: boolean;
	};
	let { show = $bindable(false) }: Props = $props();

	let notice = $state('');
	const urls = ['http://localhost:11434'];
	let selectedUrlIdx = $state(0);
	let ollamaModels = $state<{ id: string; name: string; size: number }[]>([
		{ id: 'llama3:8b', name: 'llama3:8b', size: 4.7 * 1024 ** 3 },
		{ id: 'mistral:7b', name: 'mistral:7b', size: 4.1 * 1024 ** 3 },
		{ id: 'qwen2.5:7b', name: 'qwen2.5:7b', size: 4.4 * 1024 ** 3 }
	]);

	let modelTag = $state('');
	let modelLoading = $state(false);
	let pullProgress = $state<number | null>(null);

	let deleteModelTag = $state('');
	let showModelDeleteConfirm = $state(false);

	let createModelName = $state('');
	let createModelObject = $state('');
	let createModelLoading = $state(false);

	let showExperimental = $state(false);

	const inform = (message: string) => {
		notice = message;
		setTimeout(() => (notice = ''), 2400);
	};

	const pullModelHandler = () => {
		const tag = modelTag.trim().replace(/^ollama\s+(run|pull)\s+/, '');
		if (!tag) return;
		modelLoading = true;
		pullProgress = 0;
		let progress = 0;
		const timer = setInterval(() => {
			progress = Math.min(100, progress + 12);
			pullProgress = progress;
			if (progress >= 100) {
				clearInterval(timer);
				if (!ollamaModels.find((m) => m.id === tag)) {
					ollamaModels = [...ollamaModels, { id: tag, name: tag, size: 4.5 * 1024 ** 3 }];
				}
				modelLoading = false;
				pullProgress = null;
				modelTag = '';
				inform(`模型 '${tag}' 下载成功（mock）`);
			}
		}, 260);
	};

	const deleteModelHandler = () => {
		const model = ollamaModels.find((m) => m.id === deleteModelTag);
		ollamaModels = ollamaModels.filter((m) => m.id !== deleteModelTag);
		deleteModelTag = '';
		inform(`已删除 ${model?.name ?? ''}（mock）`);
	};

	const createModelHandler = () => {
		let parsed: { size?: number } = {};
		try {
			parsed = JSON.parse(createModelObject);
		} catch (error) {
			inform(`${error}`);
			return;
		}
		createModelLoading = true;
		setTimeout(() => {
			const name = createModelName.trim();
			if (!ollamaModels.find((m) => m.id === name)) {
				ollamaModels = [...ollamaModels, { id: name, name, size: parsed.size ?? 4.5 * 1024 ** 3 }];
			}
			createModelLoading = false;
			createModelName = '';
			createModelObject = '';
			inform('模型已创建（mock）');
		}, 700);
	};
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between px-5 pt-4 pb-1.5 dark:text-gray-100">
			<h1 class="self-center text-lg font-medium">管理模型</h1>
			<button class="self-center" aria-label="关闭" onclick={() => (show = false)}>
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-5"
					><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" /></svg
				>
			</button>
		</div>

		<div class="flex w-full flex-col px-4 pb-4 dark:text-gray-200">
			<div class="flex w-full flex-col">
				<div class="mb-2 text-sm font-medium">Ollama</div>
				<div class="dark:bg-gray-850 mb-4 rounded-lg bg-gray-50">
					<select
						class="w-full bg-transparent px-4 py-2 text-sm outline-none"
						bind:value={selectedUrlIdx}
						aria-label="选择 Ollama 实例"
					>
						{#each urls as url, idx (idx)}<option value={idx}>{url}</option>{/each}
					</select>
				</div>

				<div class="space-y-4">
					<div>
						<div class="mb-2 flex items-center gap-1.5 text-sm font-medium">
							从 Ollama.com 下载模型
						</div>
						<div class="flex w-full">
							<div class="mr-2 flex-1">
								<input
									class="dark:bg-gray-850 w-full rounded-lg bg-gray-50 px-4 py-2 text-sm outline-none placeholder:text-gray-400"
									placeholder="输入模型标签（例如：mistral:7b）"
									bind:value={modelTag}
									disabled={modelLoading}
								/>
							</div>
							<button
								class="dark:bg-gray-850 rounded-lg bg-gray-50 px-2.5 text-gray-800 transition hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-40 dark:text-gray-100 dark:hover:bg-gray-800"
								onclick={pullModelHandler}
								disabled={modelLoading || modelTag.trim() === ''}
								aria-label="下载模型"
							>
								{#if modelLoading}
									<svg
										class="size-4 animate-spin"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										><circle cx="12" cy="12" r="9" opacity="0.25" /><path
											d="M21 12a9 9 0 0 0-9-9"
											stroke-linecap="round"
										/></svg
									>
								{:else}
									<svg class="size-4" viewBox="0 0 16 16" fill="currentColor"
										><path
											d="M8.75 2.75a.75.75 0 0 0-1.5 0v5.69L5.03 6.22a.75.75 0 0 0-1.06 1.06l3.5 3.5a.75.75 0 0 0 1.06 0l3.5-3.5a.75.75 0 0 0-1.06-1.06L8.75 8.44V2.75Z"
										/><path
											d="M3.5 9.75a.75.75 0 0 0-1.5 0v1.5A2.75 2.75 0 0 0 4.75 14h6.5A2.75 2.75 0 0 0 14 11.25v-1.5a.75.75 0 0 0-1.5 0v1.5c0 .69-.56 1.25-1.25 1.25h-6.5c-.69 0-1.25-.56-1.25-1.25v-1.5Z"
										/></svg
									>
								{/if}
							</button>
						</div>
						<div class="mt-2 mb-1 text-xs text-gray-400 dark:text-gray-500">
							访问可下载的模型名称，<a
								class="font-medium text-gray-500 underline dark:text-gray-300"
								href="https://ollama.com/library"
								target="_blank"
								rel="noreferrer">点击此处</a
							>
						</div>

						{#if pullProgress !== null}
							<div class="text-xs">
								<div
									class="rounded-full bg-gray-500 p-0.5 text-center text-xs leading-none font-medium text-gray-100 dark:bg-gray-600"
									style="width: {Math.max(15, pullProgress)}%"
								>
									{pullProgress}%
								</div>
							</div>
						{/if}
					</div>

					<div>
						<div class="mb-2 text-sm font-medium">删除模型</div>
						<div class="flex w-full">
							<div class="dark:bg-gray-850 mr-2 flex-1 rounded-lg bg-gray-50 pr-1.5">
								<select
									class="w-full bg-transparent px-4 py-2 text-sm outline-none dark:text-gray-300"
									bind:value={deleteModelTag}
									aria-label="选择模型"
								>
									<option value="" disabled>选择模型</option>
									{#each ollamaModels as model (model.id)}<option
											value={model.id}
											class="bg-gray-50 dark:bg-gray-700"
											>{model.name} ({(model.size / 1024 ** 3).toFixed(1)} GB)</option
										>{/each}
								</select>
							</div>
							<button
								class="dark:bg-gray-850 rounded-lg bg-gray-50 px-2.5 text-gray-800 transition hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-40 dark:text-gray-100 dark:hover:bg-gray-800"
								onclick={() => (showModelDeleteConfirm = true)}
								disabled={deleteModelTag === ''}
								aria-label="删除模型"
							>
								<svg class="size-4" viewBox="0 0 16 16" fill="currentColor"
									><path
										fill-rule="evenodd"
										d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35l.815-8.15h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5a.75.75 0 0 1 .786-.711Z"
										clip-rule="evenodd"
									/></svg
								>
							</button>
						</div>
					</div>

					<div>
						<div class="mb-2 text-sm font-medium">创建模型</div>
						<div class="flex w-full">
							<div class="mr-2 flex flex-1 flex-col gap-2">
								<input
									class="dark:bg-gray-850 w-full rounded-lg bg-gray-50 px-4 py-2 text-sm outline-none placeholder:text-gray-400"
									placeholder="输入模型标签（例如：my-modelfile）"
									bind:value={createModelName}
									disabled={createModelLoading}
								/>
								<textarea
									class="dark:bg-gray-850 w-full resize-none rounded-lg bg-gray-50 px-4 py-2 text-sm outline-none"
									rows="6"
									placeholder={'e.g. {"model": "my-modelfile", "from": "ollama:7b"})'}
									bind:value={createModelObject}
									disabled={createModelLoading}></textarea>
							</div>
							<div class="flex self-start">
								<button
									class="dark:bg-gray-850 rounded-lg bg-gray-50 px-2.5 py-2.5 text-gray-800 transition hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-40 dark:text-gray-100 dark:hover:bg-gray-800"
									onclick={createModelHandler}
									disabled={createModelLoading ||
										createModelName.trim() === '' ||
										createModelObject.trim() === ''}
									aria-label="创建模型"
								>
									<svg class="size-4" viewBox="0 0 16 16" fill="currentColor"
										><path
											d="M7.25 10.25a.75.75 0 0 0 1.5 0V4.56l2.22 2.22a.75.75 0 1 0 1.06-1.06l-3.5-3.5a.75.75 0 0 0-1.06 0l-3.5 3.5a.75.75 0 0 0 1.06 1.06l2.22-2.22v5.69Z"
										/><path
											d="M3.5 9.75a.75.75 0 0 0-1.5 0v1.5A2.75 2.75 0 0 0 4.75 14h6.5A2.75 2.75 0 0 0 14 11.25v-1.5a.75.75 0 0 0-1.5 0v1.5c0 .69-.56 1.25-1.25 1.25h-6.5c-.69 0-1.25-.56-1.25-1.25v-1.5Z"
										/></svg
									>
								</button>
							</div>
						</div>
					</div>

					<div class="pt-1">
						<div class="flex items-center justify-between text-xs">
							<div class="text-sm font-medium">实验性</div>
							<button
								class="text-xs font-medium text-gray-500"
								type="button"
								onclick={() => (showExperimental = !showExperimental)}
								>{showExperimental ? '隐藏' : '显示'}</button
							>
						</div>
					</div>

					{#if showExperimental}
						<div class="text-xs text-gray-400 dark:text-gray-500">
							上传 GGUF 模型等实验功能为本地 mock 占位。
						</div>
					{/if}
				</div>
			</div>
		</div>
	</div>
</Modal>

{#if showModelDeleteConfirm}
	<div
		class="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 p-4"
		role="presentation"
		onclick={(e) => {
			if (e.target === e.currentTarget) showModelDeleteConfirm = false;
		}}
	>
		<div
			class="w-full max-w-sm rounded-2xl border border-gray-800 bg-gray-900 p-5 text-white shadow-2xl"
			role="dialog"
			aria-modal="true"
			tabindex="-1"
		>
			<div class="text-base font-medium">删除模型</div>
			<p class="mt-2 text-sm text-gray-400">确定要删除模型 {deleteModelTag} 吗？此操作无法撤销。</p>
			<div class="mt-5 flex justify-end gap-2">
				<button
					class="rounded-lg px-3 py-1.5 text-sm text-gray-400 hover:bg-gray-800"
					type="button"
					onclick={() => (showModelDeleteConfirm = false)}>取消</button
				>
				<button
					class="rounded-lg bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-900"
					type="button"
					onclick={() => {
						showModelDeleteConfirm = false;
						deleteModelHandler();
					}}>删除</button
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
