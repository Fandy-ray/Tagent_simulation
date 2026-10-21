<script lang="ts">
	import { goto } from '$app/navigation';
	import { untrack } from 'svelte';
	import CodeEditor from '$lib/components/common/CodeEditor.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import { functionBoilerplate, inferFunctionType, toFunctionId, type FunctionType } from '$lib/data/mockFunctions';

	type Props = {
		id?: string;
		name?: string;
		meta?: { description?: string };
		content?: string;
		edit?: boolean;
		clone?: boolean;
		onSave?: (payload: {
			id: string;
			name: string;
			meta: { description: string };
			content: string;
			type: FunctionType;
		}) => void | Promise<void>;
	};

	let {
		id = '',
		name = '',
		meta = { description: '' },
		content = '',
		edit = false,
		clone = false,
		onSave = () => {}
	}: Props = $props();

	let funcName = $state(untrack(() => name));
	let funcId = $state(untrack(() => id));
	let description = $state(untrack(() => meta.description ?? ''));
	let code = $state(untrack(() => content));
	let showConfirm = $state(false);
	let loading = $state(false);

	// 新建时由名称自动生成 ID；用户手动改过 ID 后不再覆盖
	let autoId = $state(untrack(() => id));
	$effect(() => {
		if (edit || clone) return;
		const generated = toFunctionId(funcName);
		if (!generated) return;
		if (funcId === '' || funcId === autoId) {
			funcId = generated;
			autoId = generated;
		}
	});

	const canSubmit = $derived(Boolean(funcName.trim() && funcId.trim() && description.trim()));
	const inferredType = $derived(inferFunctionType(code));

	const persist = async () => {
		if (loading) return;
		loading = true;
		try {
			await onSave({
				id: toFunctionId(funcId),
				name: funcName.trim(),
				meta: { description: description.trim() },
				content: code,
				type: inferredType
			});
		} finally {
			loading = false;
			showConfirm = false;
		}
	};

	const submit = () => {
		if (!canSubmit) return;
		if (edit) {
			void persist();
			return;
		}
		showConfirm = true;
	};

	const back = () => {
		goto('/admin/functions');
	};
</script>

<div class="flex h-full min-h-0 w-full flex-col">
	<form
		class="flex h-full min-h-0 flex-col"
		onsubmit={(event) => {
			event.preventDefault();
			submit();
		}}
	>
		<header class="mb-2 flex shrink-0 flex-col gap-1">
			<div class="flex w-full items-center gap-1">
				<button
					type="button"
					class="shrink-0 rounded-lg px-1 py-1.5 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-850 dark:hover:text-white"
					onclick={back}
					title="返回函数列表"
					aria-label="返回函数列表"
				>
					<svg class="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
					</svg>
				</button>

				<input
					class="w-full min-w-0 flex-1 bg-transparent text-2xl font-medium outline-none placeholder:text-gray-400 dark:placeholder:text-gray-600"
					type="text"
					placeholder="函数名称"
					aria-label="函数名称"
					bind:value={funcName}
					required
				/>

				<span class="shrink-0 rounded-lg bg-gray-500/20 px-1.5 py-0.5 text-xs font-medium uppercase text-gray-600 dark:text-gray-200">
					函数
				</span>
			</div>

			<div class="flex items-center gap-2 px-1">
				{#if edit}
					<span class="shrink-0 text-sm text-gray-500">{funcId}</span>
				{:else}
					<input
						class="w-full min-w-0 bg-transparent text-sm outline-none placeholder:text-gray-400 disabled:text-gray-500 dark:placeholder:text-gray-600"
						type="text"
						placeholder="函数 ID"
						aria-label="函数 ID"
						bind:value={funcId}
						required
					/>
				{/if}

				<input
					class="w-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400 dark:placeholder:text-gray-600"
					type="text"
					placeholder="函数描述"
					aria-label="函数描述"
					bind:value={description}
					required
				/>
			</div>
		</header>

		<div class="mb-2 min-h-0 flex-1 overflow-hidden">
			<CodeEditor
				value={code}
				lang="python"
				boilerplate={functionBoilerplate}
				onChange={(next) => {
					code = next;
				}}
				onSave={submit}
			/>
		</div>

		<footer class="flex shrink-0 items-center justify-between gap-3 pt-1 pb-3">
			<div class="flex-1 pr-3 text-xs text-gray-500">
				<div class="line-clamp-2">
					<span class="font-semibold dark:text-gray-200">警告：</span>
					函数会执行任意代码。<br />—
					<span class="font-medium dark:text-gray-400">不要安装来自不可信来源的函数。</span>
				</div>
			</div>

			<button
				type="submit"
				class="shrink-0 rounded-full bg-gray-900 px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-gray-700 dark:bg-white dark:text-black dark:hover:bg-gray-200"
				disabled={!canSubmit || loading}
			>
				{loading ? '保存中…' : '保存'}
			</button>
		</footer>
	</form>
</div>

<ConfirmDialog
	bind:show={showConfirm}
	title="创建函数前请确认"
	cancelLabel="取消"
	confirmLabel="我已了解，创建函数"
	onConfirm={() => void persist()}
	onCancel={() => {
		showConfirm = false;
	}}
>
	<div class="text-sm text-gray-400">
		<div class="rounded-lg bg-yellow-500/20 px-4 py-3 text-yellow-700 dark:text-yellow-200">
			<div>请仔细阅读以下警告：</div>
			<ul class="mt-1 list-disc pl-4 text-xs">
				<li>函数允许执行任意代码。</li>
				<li>不要安装你不完全信任来源的函数。</li>
			</ul>
		</div>

		<p class="my-3">
			我确认已阅读并理解上述风险，清楚执行任意代码可能带来的后果，并已验证代码来源可信。
		</p>
	</div>
</ConfirmDialog>
