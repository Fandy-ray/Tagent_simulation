<script lang="ts">
	import { getI18nContext } from '$lib/i18n';
	const i18n = getI18nContext();

	import Modal from '$lib/components/common/Modal.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import Minus from '$lib/components/icons/Minus.svelte';
	import SensitiveInput from '$lib/components/common/SensitiveInput.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Tags from '$lib/components/common/Tags.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';

	const showToast = (message: string, type: 'success' | 'error' = 'success') => {
		const toast = document.createElement('div');
		toast.className = `fixed bottom-4 right-4 px-4 py-2 rounded-lg text-white text-sm z-[100] ${type === 'success' ? 'bg-green-600' : 'bg-red-600'}`;
		toast.textContent = message;
		document.body.appendChild(toast);
		setTimeout(() => toast.remove(), 3000);
	};

	type Props = {
		show?: boolean;
		edit?: boolean;
		direct?: boolean;
		ollama?: boolean;
		connection?: any;
		onSubmit?: (connection: any) => void;
		onDelete?: () => void;
	};

	let {
		show = $bindable(false),
		edit = false,
		direct = false,
		ollama = false,
		connection = null,
		onSubmit = () => {},
		onDelete = () => {}
	}: Props = $props();

	let url = $state('');
	let key = $state('');
	let auth_type = $state('bearer');
	let connectionType = $state('external');
	let azure = $state(false);
	let apiVersion = $state('');
	let prefixId = $state('');
	let enable = $state(true);
	let headers = $state('');
	let apiType = $state('');
	let tags: any[] = $state([]);
	let modelId = $state('');
	let modelIds: any[] = $state([]);
	let loading = $state(false);
	let showDeleteConfirmDialog = $state(false);

	$effect(() => {
		if (show && !connection) {
			connectionType = ollama ? 'local' : 'external';
		}
	});

	$effect(() => {
		azure = (url.includes('azure.') || url.includes('cognitive.microsoft.com')) && !direct && !ollama
			? true
			: false;
	});

	const verifyOpenAIHandler = async () => {
		url = url.replace(/\/$/, '');

		if (headers) {
			try {
				const _headers = JSON.parse(headers);
				if (typeof _headers !== 'object' || Array.isArray(_headers)) {
					throw new Error('Headers must be a valid JSON object');
				}
				headers = JSON.stringify(_headers, null, 2);
			} catch {
				showToast($i18n.t('Headers must be a valid JSON object'), 'error');
				return;
			}
		}

		showToast($i18n.t('Server connection verified'), 'success');
	};

	const addModelHandler = () => {
		if (modelId) {
			modelIds = [...modelIds, modelId];
			modelId = '';
		}
	};

	const submitHandler = async () => {
		loading = true;

		if (!url) {
			loading = false;
			showToast($i18n.t('URL is required'), 'error');
			return;
		}

		if (azure) {
			if (!apiVersion) {
				loading = false;
				showToast($i18n.t('API Version is required'), 'error');
				return;
			}

			if (!key && auth_type !== 'azure_ad' && auth_type !== 'microsoft_entra_id') {
				loading = false;
				showToast($i18n.t('Key is required'), 'error');
				return;
			}

			if (modelIds.length === 0) {
				loading = false;
				showToast($i18n.t('Deployment names are required for Azure OpenAI'), 'error');
				return;
			}
		}

		if (headers) {
			try {
				const _headers = JSON.parse(headers);
				if (typeof _headers !== 'object' || Array.isArray(_headers)) {
					throw new Error('Headers must be a valid JSON object');
				}
				headers = JSON.stringify(_headers, null, 2);
			} catch {
				showToast($i18n.t('Headers must be a valid JSON object'), 'error');
				return;
			}
		}

		url = url.replace(/\/$/, '');

		const newConnection = {
			url,
			key,
			config: {
				enable,
				tags,
				prefix_id: prefixId,
				model_ids: modelIds,
				connection_type: connectionType,
				auth_type,
				headers: headers ? JSON.parse(headers) : undefined,
				...(apiType ? { api_type: apiType } : {}),
				...(azure ? { azure: true, api_version: apiVersion } : {})
			}
		};

		await onSubmit(newConnection);

		loading = false;
		show = false;

		url = '';
		key = '';
		auth_type = 'bearer';
		apiType = '';
		prefixId = '';
		tags = [];
		modelIds = [];
	};

	const init = () => {
		if (connection) {
			url = connection.url ?? '';
			key = connection.key ?? '';

			auth_type = connection.config?.auth_type ?? 'bearer';
			headers = connection.config?.headers
				? JSON.stringify(connection.config.headers, null, 2)
				: '';

			enable = connection.config?.enable ?? true;
			tags = connection.config?.tags ?? [];
			prefixId = connection.config?.prefix_id ?? '';
			modelIds = connection.config?.model_ids ?? [];

			connectionType = connection.config?.connection_type ?? (ollama ? 'local' : 'external');
			azure = connection.config?.azure ?? false;
			apiVersion = connection.config?.api_version ?? '';
			apiType = connection.config?.api_type ?? '';
		}
	};

	$effect(() => {
		if (show) {
			init();
		}
	});
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between px-5 pt-4 pb-1.5 dark:text-gray-100">
			<h1 class="self-center text-lg font-medium">
				{#if edit}
					{$i18n.t('Edit Connection')}
				{:else}
					{$i18n.t('Add Connection')}
				{/if}
			</h1>
			<button
				class="self-center"
				aria-label={$i18n.t('Close')}
				onclick={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex w-full flex-col px-4 pb-4 dark:text-gray-200">
			<div class="flex w-full flex-col">
				<form
					class="flex w-full flex-col"
					onsubmit={(e) => {
						e.preventDefault();
						submitHandler();
					}}
				>
					<div class="px-1">
						{#if !direct}
							<div class="flex gap-2">
								<div class="flex w-full items-center justify-between">
									<div class="text-xs text-gray-500">
										{$i18n.t('Connection Type')}
									</div>

									<div>
										<button
											onclick={() => {
												connectionType = connectionType === 'local' ? 'external' : 'local';
											}}
											type="button"
											class="text-xs text-gray-700 dark:text-gray-300"
										>
											{#if connectionType === 'local'}
												{$i18n.t('Local')}
											{:else}
												{$i18n.t('External')}
											{/if}
										</button>
									</div>
								</div>
							</div>
						{/if}

						<div class="mt-1.5 flex gap-2">
							<div class="flex w-full flex-col">
								<label for="url-input" class="mb-0.5 text-xs text-gray-500">
									{$i18n.t('URL')}
								</label>

								<div class="flex-1">
									<input
										id="url-input"
										class="w-full bg-transparent text-sm text-gray-300 outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-700"
										type="text"
										bind:value={url}
										placeholder={$i18n.t('API Base URL')}
										autocomplete="off"
										list={ollama ? undefined : 'suggestions'}
										required
									/>

									<datalist id="suggestions">
										<option value="https://api.openai.com/v1"></option>
										<option value="https://api.anthropic.com/v1"></option>
										<option
											value="https://generativelanguage.googleapis.com/v1beta/openai"
										></option>
										<option value="https://api.mistral.ai/v1"></option>
										<option value="https://api.groq.com/openai/v1"></option>
										<option value="https://openrouter.ai/api/v1"></option>
										<option value="https://api.x.ai/v1"></option>
									</datalist>
								</div>
							</div>

							<Tooltip content={$i18n.t('Verify Connection')} className="self-end -mb-1">
								<button
									class="self-center rounded-lg bg-transparent p-1 transition hover:bg-gray-100 dark:hover:bg-gray-850"
									onclick={() => {
										verifyOpenAIHandler();
									}}
									type="button"
									aria-label={$i18n.t('Verify Connection')}
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
										class="size-4"
										aria-hidden="true"
									>
										<path
											fill-rule="evenodd"
											d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H3.989a.75.75 0 00-.75.75v4.242a.75.75 0 001.5 0v-2.43l.31.31a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm1.23-3.723a.75.75 0 00.219-.53V2.929a.75.75 0 00-1.5 0V5.36l-.31-.31A7 7 0 003.239 8.188a.75.75 0 101.448.389A5.5 5.5 0 0113.89 6.11l.311.31h-2.432a.75.75 0 000 1.5h4.243a.75.75 0 00.53-.219z"
											clip-rule="evenodd"
										/>
									</svg>
								</button>
							</Tooltip>

							<div class="flex shrink-0 flex-col self-end">
								<label class="sr-only" for="toggle-connection">
									{$i18n.t('Toggle whether current connection is active.')}
								</label>
								<Tooltip content={enable ? $i18n.t('Enabled') : $i18n.t('Disabled')}>
									<Switch id="toggle-connection" bind:state={enable} />
								</Tooltip>
							</div>
						</div>

						<div class="mt-2 flex gap-2">
							<div class="flex w-full flex-col">
								<label for="select-bearer-or-session" class="text-xs text-gray-500">
									{$i18n.t('Auth')}
								</label>

								<div class="flex gap-2">
									<div class="flex-shrink-0 self-start">
										<select
											id="select-bearer-or-session"
											class="w-full bg-transparent pr-5 text-sm outline-hidden"
											bind:value={auth_type}
										>
											<option value="none">{$i18n.t('None')}</option>
											<option value="bearer">{$i18n.t('Bearer')}</option>
											{#if !direct && !ollama}
												<option value="session">{$i18n.t('Session')}</option>
												<option value="system_oauth">{$i18n.t('OAuth')}</option>
												{#if azure}
													<option value="microsoft_entra_id">{$i18n.t('Entra ID')}</option>
												{/if}
											{/if}
										</select>
									</div>

									<div class="flex flex-1 items-center">
										{#if auth_type === 'bearer'}
											<SensitiveInput
												bind:value={key}
												placeholder={$i18n.t('API Key')}
												required={false}
											/>
										{:else if auth_type === 'none'}
											<div class="self-center text-xs text-gray-500">
												{$i18n.t('No authentication')}
											</div>
										{:else if auth_type === 'session'}
											<div class="self-center text-xs text-gray-500">
												{$i18n.t(
													'Forwards system user session credentials to authenticate'
												)}
											</div>
										{:else if auth_type === 'system_oauth'}
											<div class="self-center text-xs text-gray-500">
												{$i18n.t(
													'Forwards system user OAuth access token to authenticate'
												)}
											</div>
										{:else if auth_type === 'microsoft_entra_id'}
											<div class="self-center text-xs text-gray-500">
												{$i18n.t('Uses DefaultAzureCredential to authenticate')}
											</div>
										{/if}
									</div>
								</div>
							</div>
						</div>

						{#if !direct && !ollama}
							<div class="mt-2 flex gap-2">
								<div class="flex w-full flex-col">
									<label for="headers-input" class="mb-0.5 text-xs text-gray-500">
										{$i18n.t('Headers')}
									</label>

									<div class="flex-1">
										<Tooltip
											content={$i18n.t(
												'Enter additional headers in JSON format (e.g. {"X-Custom-Header": "value"}'
											)}
										>
											<Textarea
												className="w-full text-sm outline-hidden"
												bind:value={headers}
												placeholder={$i18n.t('Enter additional headers in JSON format')}
											/>
										</Tooltip>
									</div>
								</div>
							</div>
						{/if}

						<div class="mt-2 flex gap-2">
							<div class="flex w-full flex-col">
								<label for="prefix-id-input" class="mb-0.5 text-xs text-gray-500">
									{$i18n.t('Prefix ID')}
								</label>

								<div class="flex-1">
									<Tooltip
										content={$i18n.t(
											'Prefix ID is used to avoid conflicts with other connections by adding a prefix to the model IDs - leave empty to disable'
										)}
									>
										<input
											class="w-full bg-transparent text-sm text-gray-300 outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-700"
											type="text"
											id="prefix-id-input"
											bind:value={prefixId}
											placeholder={$i18n.t('Prefix ID')}
											autocomplete="off"
										/>
									</Tooltip>
								</div>
							</div>
						</div>

						{#if !direct && !ollama}
							<div class="mt-2 flex w-full flex-row items-center justify-between">
								<label for="provider-type" class="mb-0.5 text-xs text-gray-500">
									{$i18n.t('Provider Type')}
								</label>

								<div>
									<button
										onclick={() => {
											azure = !azure;
										}}
										type="button"
										id="provider-type"
										class="text-xs text-gray-700 dark:text-gray-300"
									>
										{azure ? $i18n.t('Azure OpenAI') : $i18n.t('OpenAI')}
									</button>
								</div>
							</div>
						{/if}

						{#if !ollama && !direct}
							<div class="mt-1 flex w-full items-center justify-between">
								<div class="mb-0.5 text-xs text-gray-500">{$i18n.t('API Type')}</div>
								<button type="button" class="text-xs text-gray-700 dark:text-gray-300" onclick={() => apiType = apiType === 'responses' ? '' : 'responses'}>{apiType === 'responses' ? 'Responses' : 'Chat Completions'}</button>
							</div>
						{/if}

						{#if azure}
							<div class="mt-2 flex gap-2">
								<div class="flex w-full flex-col">
									<label for="api-version-input" class="mb-0.5 text-xs text-gray-500">
										{$i18n.t('API Version')}
									</label>

									<div class="flex-1">
										<input
											id="api-version-input"
											class="w-full bg-transparent text-sm text-gray-300 outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-700"
											type="text"
											bind:value={apiVersion}
											placeholder={$i18n.t('API Version')}
											autocomplete="off"
											required
										/>
									</div>
								</div>
							</div>
						{/if}

						<div class="mt-2 flex w-full flex-col">
							<div class="mb-1 flex justify-between">
								<div class="mb-0.5 text-xs text-gray-500">
									{$i18n.t('Model IDs')}
								</div>
							</div>

							{#if modelIds.length > 0}
								<ul class="flex flex-col">
									{#each modelIds as _, modelIdx}
										{@const m = modelIds[modelIdx]}
										<li class="flex w-full items-center justify-between gap-2">
											<div class="flex-1 rounded-lg py-1 text-sm">
												{m}
											</div>
											<div class="shrink-0">
												<button
													aria-label={$i18n.t('Remove {{MODELID}} from list.', {
														MODELID: m
													})}
													type="button"
													onclick={() => {
														modelIds = modelIds.filter((_, idx) => idx !== modelIdx);
													}}
												>
													<Minus className="size-3.5" strokeWidth="2" />
												</button>
											</div>
										</li>
									{/each}
								</ul>
							{:else}
								<div class="px-10 py-2 text-center text-xs text-gray-500">
									{#if ollama}
										{$i18n.t('Leave empty to include all models from "{{url}}/api/tags" endpoint', { url })}
									{:else if azure}
										{$i18n.t('Deployment names are required for Azure OpenAI')}
									{:else}
										{$i18n.t(
											'Leave empty to include all models from "{{url}}/models" endpoint',
											{ url }
										)}
									{/if}
								</div>
							{/if}
						</div>

						<div class="flex items-center">
							<label class="sr-only" for="add-model-id-input">
								{$i18n.t('Add a model ID')}
							</label>
							<input
								class={`w-full rounded-lg bg-transparent py-1 text-sm ${modelId ? '' : 'text-gray-500'} outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-700`}
								bind:value={modelId}
								id="add-model-id-input"
								placeholder={$i18n.t('Add a model ID')}
							/>

							<div>
								<button
									type="button"
									aria-label={$i18n.t('Add')}
									onclick={() => {
										addModelHandler();
									}}
								>
									<Plus className="size-3.5" strokeWidth="2" />
								</button>
							</div>
						</div>
					</div>

					<div class="mt-2 flex gap-2">
						<div class="flex w-full flex-col">
							<div class="mb-0.5 text-xs text-gray-500">
								{$i18n.t('Tags')}
							</div>

							<div class="mt-0.5 flex-1">
								<Tags
									bind:tags
									onAdd={(e) => {
										tags = [...tags, { name: e.detail }];
									}}
									onDelete={(e) => {
										tags = tags.filter((tag) => tag.name !== e.detail);
									}}
								/>
							</div>
						</div>
					</div>

					<div class="flex items-center justify-between pt-3 text-sm font-medium">
						<div>
							{#if edit}
								<button
									class="px-1 py-1.5 text-sm font-medium text-gray-500 transition hover:text-gray-700 hover:underline dark:text-gray-400 dark:hover:text-gray-200"
									type="button"
									onclick={() => {
										showDeleteConfirmDialog = true;
									}}
								>
									{$i18n.t('Delete')}
								</button>
							{/if}
						</div>

						<button
							class={`flex items-center gap-2 whitespace-nowrap rounded-full bg-black px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-gray-900 dark:bg-white dark:text-black dark:hover:bg-gray-100 ${loading ? 'cursor-not-allowed' : ''}`}
							type="submit"
							disabled={loading}
						>
							{$i18n.t('Save')}

							{#if loading}
								<span class="shrink-0">
									<Spinner />
								</span>
							{/if}
						</button>
					</div>
				</form>
			</div>
		</div>
	</div>
</Modal>

<ConfirmDialog
	bind:show={showDeleteConfirmDialog}
	message={$i18n.t(
		'Are you sure you want to delete this connection? This action cannot be undone.'
	)}
	confirmLabel={$i18n.t('Delete')}
	onConfirm={() => {
		onDelete();
		show = false;
	}}
/>
