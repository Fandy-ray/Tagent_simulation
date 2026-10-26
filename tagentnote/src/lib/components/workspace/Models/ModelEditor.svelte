<script lang="ts">
	import { onMount } from 'svelte';

	import { getAgentModels } from '$lib/apis/agent';
	import AdvancedParams from '$lib/components/chat/Settings/Advanced/AdvancedParams.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import { listKnowledge, slugify, type WorkspaceModel } from '$lib/data/workspaceResources';

	import BuiltinTools from './BuiltinTools.svelte';
	import Capabilities from './Capabilities.svelte';
	import DefaultFeatures from './DefaultFeatures.svelte';
	import KnowledgeAttach from './KnowledgeAttach.svelte';
	import PromptSuggestions from './PromptSuggestions.svelte';

	type SuggestionPrompt = { content: string; title: [string, string] };

	type Props = {
		edit?: boolean;
		initial?: WorkspaceModel | null;
		onBack?: () => void;
		onSave?: (model: WorkspaceModel) => void;
	};

	let { edit = false, initial = null, onBack = () => {}, onSave = () => {} }: Props = $props();

	const DEFAULT_AVATAR = '/favicon.svg';

	const DEFAULT_CAPS: Record<string, boolean | undefined> = {
		vision: true,
		file_upload: true,
		file_context: true,
		web_search: true,
		image_generation: true,
		code_interpreter: true,
		citations: true,
		status_updates: true,
		builtin_tools: true,
		usage: false
	};

	const DEFAULT_BUILTIN: Record<string, boolean> = {
		time: true,
		memory: true,
		chats: true,
		notes: true,
		knowledge: true,
		channels: true,
		web_search: true,
		image_generation: true,
		code_interpreter: true
	};

	let saving = $state(false);
	let name = $state('');
	let id = $state('');
	let idTouched = $state(false);
	let baseModelId = $state<string | null>(null);
	let enableDescription = $state(true);
	let description = $state('');
	let system = $state('');
	let tags = $state<string[]>([]);
	let tagDraft = $state('');
	let isActive = $state(true);
	let profileImageUrl = $state(DEFAULT_AVATAR);
	let showAdvanced = $state(false);
	let showPreview = $state(false);
	let showAccessModal = $state(false);
	let params = $state<
		Record<string, unknown> & {
			reasoning_tags: boolean | [string, string] | null;
			custom_params: Record<string, string>;
			use_mmap?: boolean | null;
			use_mlock?: boolean | null;
			format?: string;
		}
	>({ reasoning_tags: null, custom_params: {} });
	let suggestionPrompts = $state<SuggestionPrompt[] | null>(null);
	let knowledgeIds = $state<string[]>([]);
	let knowledgeFiles = $state<{ id: string; name: string; type: 'file'; size?: number }[]>([]);
	let toolIds = $state<string[]>([]);
	let skillIds = $state<string[]>([]);
	let capabilities = $state<Record<string, boolean | undefined>>({ ...DEFAULT_CAPS });
	let builtinTools = $state<Record<string, boolean>>({ ...DEFAULT_BUILTIN });
	let defaultFeatureIds = $state<string[]>([]);
	let ttsVoice = $state('');
	let agentModels = $state<{ id: string; name: string }[]>([]);
	let knowledgeOptions = $state<{ id: string; name: string }[]>([]);
	let fileInput: HTMLInputElement | null = $state(null);
	let createdAt = $state(Date.now());
	let error = $state('');

	const availableFeatures = $derived(
		Object.entries(capabilities)
			.filter(
				([key, value]) =>
					Boolean(value) && ['web_search', 'code_interpreter', 'image_generation'].includes(key)
			)
			.map(([key]) => key)
	);

	const previewInfo = $derived({
		id,
		name,
		baseModelId,
		description: enableDescription ? description : null,
		system,
		tags,
		isActive,
		params: { ...params, system: system.trim() || null },
		meta: {
			profileImageUrl,
			knowledgeIds,
			knowledgeFiles,
			toolIds,
			skillIds,
			capabilities,
			builtinTools: capabilities.builtin_tools ? builtinTools : undefined,
			defaultFeatureIds,
			suggestionPrompts,
			ttsVoice
		}
	});

	const normalizeSuggestions = (raw: unknown): SuggestionPrompt[] | null => {
		if (raw == null) return null;
		if (!Array.isArray(raw)) return null;
		if (raw.length === 0) return [];
		return raw.map((item) => {
			if (typeof item === 'string') {
				return { content: item, title: ['', ''] as [string, string] };
			}
			const obj = item as { content?: string; title?: string | [string, string] };
			let title: [string, string] = ['', ''];
			if (typeof obj.title === 'string') title = [obj.title, ''];
			else if (Array.isArray(obj.title)) title = [obj.title[0] ?? '', obj.title[1] ?? ''];
			return { content: obj.content ?? '', title };
		});
	};

	const applyInitial = (model: WorkspaceModel) => {
		name = model.name || '';
		id = model.id || '';
		idTouched = edit || Boolean(model.id);
		baseModelId = model.baseModelId ?? null;
		description = model.description || '';
		enableDescription = model.description !== null && model.description !== undefined;
		system = model.system || '';
		tags = [...(model.tags || [])];
		isActive = model.isActive !== false;
		profileImageUrl = model.meta?.profileImageUrl || DEFAULT_AVATAR;
		knowledgeIds = [...(model.meta?.knowledgeIds || [])];
		knowledgeFiles = [...(model.meta?.knowledgeFiles || [])];
		toolIds = [...(model.meta?.toolIds || [])];
		skillIds = [...(model.meta?.skillIds || [])];
		capabilities = { ...DEFAULT_CAPS, ...(model.meta?.capabilities || {}) };
		builtinTools = { ...DEFAULT_BUILTIN, ...(model.meta?.builtinTools || {}) };
		defaultFeatureIds = [...(model.meta?.defaultFeatureIds || [])];
		suggestionPrompts = normalizeSuggestions(model.meta?.suggestionPrompts);
		ttsVoice = model.meta?.ttsVoice || '';
		params = {
			reasoning_tags: null,
			custom_params: {},
			...(model.params || {})
		};
		if (typeof params.stop === 'object' && Array.isArray(params.stop)) {
			params = { ...params, stop: params.stop.join(',') };
		}
		createdAt = model.createdAt || Date.now();
	};

	onMount(() => {
		if (initial) applyInitial(initial);
		else {
			const raw = sessionStorage.getItem('model');
			if (raw) {
				try {
					applyInitial(JSON.parse(raw) as WorkspaceModel);
				} catch {
					/* ignore */
				}
				sessionStorage.removeItem('model');
			}
		}

		void getAgentModels()
			.then((res) => {
				agentModels = res.data.map((m) => ({ id: m.id, name: m.name || m.id }));
			})
			.catch(() => {
				agentModels = [];
			});

		knowledgeOptions = listKnowledge().map((k) => ({ id: k.id, name: k.name }));
	});

	$effect(() => {
		if (!edit && !idTouched && name) {
			id = slugify(name);
		}
	});

	const addTag = () => {
		const t = tagDraft.trim();
		if (!t || tags.includes(t)) return;
		tags = [...tags, t];
		tagDraft = '';
	};

	const onAvatarChange = (e: Event) => {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		const reader = new FileReader();
		reader.onload = () => {
			profileImageUrl = String(reader.result || '');
		};
		reader.readAsDataURL(file);
		input.value = '';
	};

	const submit = () => {
		error = '';
		const finalId = (edit ? id : idTouched ? id : slugify(name) || id).trim();
		if (!name.trim()) {
			error = '请填写模型名称';
			return;
		}
		if (!finalId) {
			error = '请填写模型 ID';
			return;
		}
		if (!baseModelId) {
			error = '请选择基础模型';
			return;
		}

		const cleanedParams: Record<string, unknown> = { ...params };
		if (typeof cleanedParams.stop === 'string') {
			const stops = cleanedParams.stop
				.split(',')
				.map((s) => s.trim())
				.filter(Boolean);
			if (stops.length) cleanedParams.stop = stops;
			else delete cleanedParams.stop;
		}
		cleanedParams.system = system.trim() === '' ? null : system;
		for (const key of Object.keys(cleanedParams)) {
			if (
				cleanedParams[key] === '' ||
				cleanedParams[key] === null ||
				cleanedParams[key] === undefined
			) {
				delete cleanedParams[key];
			}
		}

		saving = true;
		onSave({
			id: finalId,
			name: name.trim(),
			baseModelId,
			description: enableDescription ? description.trim() : '',
			system,
			tags,
			isActive,
			params: cleanedParams,
			meta: {
				hidden: initial?.meta?.hidden ?? false,
				profileImageUrl: profileImageUrl || DEFAULT_AVATAR,
				knowledgeIds,
				knowledgeFiles: knowledgeFiles.length ? knowledgeFiles : undefined,
				toolIds,
				skillIds,
				capabilities: Object.fromEntries(
					Object.entries(capabilities).map(([k, v]) => [k, Boolean(v)])
				),
				builtinTools: capabilities.builtin_tools ? builtinTools : undefined,
				defaultFeatureIds: defaultFeatureIds.length ? defaultFeatureIds : undefined,
				suggestionPrompts,
				ttsVoice: ttsVoice.trim() || undefined
			},
			owner: 'you',
			createdAt,
			updatedAt: Date.now()
		});
		saving = false;
	};

	// 占位文字要换行：写在引号里的属性值里 \n 不转义、&#10; 也会被并成空格，所以放在这里
	const SYSTEM_PROMPT_PLACEHOLDER =
		'在此编写模型系统提示词内容\n例如）你是《超级马里奥兄弟》中的马里奥，扮演助手的角色。';
</script>

<div class="mx-auto w-full max-w-4xl px-1 pb-12">
	<button
		type="button"
		class="mb-3 flex items-center gap-1 space-x-1 text-sm font-medium text-gray-300 hover:text-white"
		onclick={onBack}
	>
		<svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
			<path
				fill-rule="evenodd"
				d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z"
				clip-rule="evenodd"
			/>
		</svg>
		<span>返回</span>
	</button>

	<input
		bind:this={fileInput}
		type="file"
		accept="image/*"
		class="hidden"
		onchange={onAvatarChange}
	/>

	<form
		class="flex w-full flex-col gap-3 md:flex-row md:gap-6"
		onsubmit={(e) => {
			e.preventDefault();
			submit();
		}}
	>
		<div class="w-full px-1">
			<div class="flex w-full flex-row gap-4 md:gap-6">
				<div class="my-2 flex shrink-0 justify-center self-start">
					<div class="self-center">
						<button
							class="group relative flex shrink-0 items-center rounded-2xl shadow-xl {profileImageUrl !==
							DEFAULT_AVATAR
								? 'bg-transparent'
								: 'bg-white'}"
							type="button"
							aria-label="上传头像"
							onclick={() => fileInput?.click()}
						>
							{#if profileImageUrl && profileImageUrl !== DEFAULT_AVATAR}
								<img
									src={profileImageUrl}
									alt="model profile"
									class="size-20 shrink-0 rounded-xl object-cover md:size-48"
								/>
							{:else}
								<div
									class="flex size-20 shrink-0 items-center justify-center rounded-xl bg-white text-3xl font-black text-black md:size-48 md:text-6xl"
								>
									T
								</div>
							{/if}

							<div class="absolute right-0 bottom-0 z-10">
								<div class="m-1.5">
									<div
										class="rounded-full border-2 border-black bg-gray-800 p-1 text-white shadow-xl transition group-hover:bg-gray-600"
									>
										<svg viewBox="0 0 16 16" fill="currentColor" class="size-5" aria-hidden="true">
											<path
												fill-rule="evenodd"
												d="M2 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4Zm10.5 5.707a.5.5 0 0 0-.146-.353l-1-1a.5.5 0 0 0-.708 0L9.354 9.646a.5.5 0 0 1-.708 0L6.354 7.354a.5.5 0 0 0-.708 0l-2 2a.5.5 0 0 0-.146.353V12a.5.5 0 0 0 .5.5h8a.5.5 0 0 0 .5-.5V9.707ZM12 5a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"
												clip-rule="evenodd"
											/>
										</svg>
									</div>
								</div>
							</div>

							<div
								class="absolute inset-0 rounded-lg bg-black opacity-0 transition group-hover:opacity-20"
							></div>
						</button>

						<div class="mt-1 flex w-full justify-center">
							<button
								class="rounded-lg px-2 py-1 text-xs text-gray-500"
								type="button"
								onclick={() => {
									profileImageUrl = DEFAULT_AVATAR;
								}}
							>
								重置图片
							</button>
						</div>
					</div>
				</div>

				<div class="flex w-full flex-1 flex-col">
					<div class="my-2 flex items-start justify-between gap-3">
						<div class="flex w-full min-w-0 flex-col">
							<input
								class="w-full bg-transparent text-3xl font-medium text-white outline-none placeholder:text-gray-500"
								placeholder="模型名称"
								bind:value={name}
								required
								oninput={() => {
									if (!edit && !idTouched) id = slugify(name);
								}}
							/>
							<input
								class="mt-0.5 w-full bg-transparent text-xs text-gray-400 outline-none placeholder:text-gray-600"
								placeholder="模型 ID"
								bind:value={id}
								disabled={edit}
								required
								oninput={() => {
									idTouched = true;
								}}
							/>
						</div>

						<button
							class="bg-gray-850 flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-white transition hover:bg-gray-800"
							type="button"
							onclick={() => {
								showAccessModal = true;
							}}
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2.5"
								class="size-3.5 shrink-0"
								aria-hidden="true"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"
								/>
							</svg>
							<div class="shrink-0 text-sm font-medium">访问</div>
						</button>
					</div>

					<div class="mb-1">
						<div class="mb-1 text-xs font-medium text-gray-500">基础模型 (来自)</div>
						<div class="relative">
							<select
								class="w-full appearance-none bg-transparent py-0.5 pr-6 text-sm text-white outline-none"
								bind:value={baseModelId}
								required
							>
								<option value={null} class="bg-gray-900 text-gray-300">选择一个基础模型</option>
								{#each agentModels as m (m.id)}
									<option value={m.id} class="bg-gray-900 text-white">{m.name}</option>
								{/each}
							</select>
							<svg
								class="pointer-events-none absolute top-1/2 right-0 size-3.5 -translate-y-1/2 text-gray-400"
								viewBox="0 0 20 20"
								fill="currentColor"
								aria-hidden="true"
							>
								<path
									fill-rule="evenodd"
									d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
									clip-rule="evenodd"
								/>
							</svg>
						</div>
					</div>

					<div class="mb-1">
						<div class="mb-1 flex w-full items-center justify-between">
							<div class="self-center text-xs font-medium text-gray-500">描述</div>
							<button
								class="flex rounded-sm p-1 text-xs text-gray-300 transition"
								type="button"
								onclick={() => {
									enableDescription = !enableDescription;
								}}
							>
								<span class="ml-2 self-center">{enableDescription ? '自定义' : '默认'}</span>
							</button>
						</div>
						{#if enableDescription}
							<Textarea
								className="w-full resize-none overflow-y-hidden bg-transparent text-sm text-white outline-none placeholder:text-gray-500"
								placeholder="添加有关该模型能力的简短描述"
								bind:value={description}
							/>
						{/if}
					</div>

					<div class="mb-1 w-full max-w-full">
						<div class="flex flex-wrap gap-1.5">
							<!-- key 带序号：导入的 JSON 里同一个标签可能写了两次，只用标签当 key 会重复，整个编辑页报错 -->
							{#each tags as tag, tagIdx (`${tagIdx}:${tag}`)}
								<button
									type="button"
									class="bg-gray-850 rounded-full px-2 py-0.5 text-xs text-gray-300 hover:bg-gray-800"
									onclick={() => {
										tags = tags.filter((t) => t !== tag);
									}}
								>
									{tag} ×
								</button>
							{/each}
						</div>
						<input
							class="mt-1 w-full bg-transparent text-sm outline-none placeholder:text-gray-500"
							placeholder="添加标签..."
							bind:value={tagDraft}
							onkeydown={(e) => {
								if (e.key === 'Enter') {
									e.preventDefault();
									addTag();
								}
							}}
						/>
					</div>
				</div>
			</div>

			<div class="my-2">
				<div class="flex w-full justify-between">
					<div class="self-center text-xs font-medium text-gray-500">模型参数</div>
				</div>

				<div class="mt-2">
					<div class="my-1">
						<div class="mb-2 text-xs font-medium">系统提示词</div>
						<Textarea
							className="w-full resize-none overflow-y-hidden bg-transparent text-sm outline-none"
							placeholder={SYSTEM_PROMPT_PLACEHOLDER}
							rows={4}
							bind:value={system}
						/>
					</div>

					<div class="flex w-full justify-between">
						<div class="self-center text-xs font-medium">高级参数</div>
						<button
							class="flex rounded-sm p-1 px-3 text-xs transition"
							type="button"
							onclick={() => {
								showAdvanced = !showAdvanced;
							}}
						>
							<span class="ml-2 self-center">{showAdvanced ? '隐藏' : '显示'}</span>
						</button>
					</div>

					{#if showAdvanced}
						<div class="my-2">
							<AdvancedParams admin={true} custom={true} bind:params />
						</div>
					{/if}
				</div>
			</div>

			<hr class="border-gray-850/30 my-2" />

			<div class="my-2">
				<div class="flex w-full items-center justify-between">
					<div class="self-center text-xs font-medium text-gray-500">提示词</div>
					<button
						class="flex rounded-sm p-1 text-xs transition"
						type="button"
						onclick={() => {
							if (suggestionPrompts === null) {
								suggestionPrompts = [{ content: '', title: ['', ''] }];
							} else {
								suggestionPrompts = null;
							}
						}}
					>
						<span class="ml-2 self-center">{suggestionPrompts === null ? '默认' : '自定义'}</span>
					</button>
				</div>

				{#if suggestionPrompts !== null}
					<div class="mt-2">
						<PromptSuggestions bind:promptSuggestions={suggestionPrompts} />
					</div>
				{/if}
			</div>

			<div class="my-4">
				<KnowledgeAttach options={knowledgeOptions} bind:knowledgeIds bind:knowledgeFiles />
			</div>

			<hr class="border-gray-850/30 my-4" />

			<div class="my-4">
				<Capabilities bind:capabilities />
			</div>

			{#if availableFeatures.length > 0}
				<div class="my-4">
					<DefaultFeatures {availableFeatures} bind:featureIds={defaultFeatureIds} />
				</div>
			{/if}

			{#if capabilities.builtin_tools}
				<div class="my-4">
					<BuiltinTools bind:builtinTools />
				</div>
			{/if}

			<div class="my-4">
				<div class="mb-1 flex w-full justify-between">
					<div class="self-center text-xs font-medium text-gray-500">文本转语音音色</div>
				</div>
				<input
					class="w-full bg-transparent text-sm outline-none placeholder:text-gray-600"
					type="text"
					bind:value={ttsVoice}
					placeholder="例如: alloy, echo, shimmer"
				/>
			</div>

			<hr class="border-gray-850/30 my-4" />

			{#if error}
				<p class="mb-2 text-sm text-red-400">{error}</p>
			{/if}

			<div class="my-2 flex justify-end">
				<button
					class="flex w-full justify-center rounded-lg bg-white px-3 py-2 text-sm text-black transition hover:bg-gray-100 disabled:cursor-not-allowed"
					type="submit"
					disabled={saving}
				>
					<div class="self-center font-medium">
						{edit ? '保存并更新' : '保存并创建'}
					</div>
				</button>
			</div>

			<div class="my-2 pb-20 text-gray-700">
				<div class="mb-2 flex w-full justify-between">
					<div class="self-center text-sm font-medium text-gray-400">JSON 预览</div>
					<button
						class="flex rounded-sm p-1 px-3 text-xs transition"
						type="button"
						onclick={() => {
							showPreview = !showPreview;
						}}
					>
						<span class="ml-2 self-center">{showPreview ? '隐藏' : '显示'}</span>
					</button>
				</div>

				{#if showPreview}
					<textarea
						class="w-full resize-none bg-transparent text-sm text-gray-400 outline-none"
						rows="10"
						value={JSON.stringify(previewInfo, null, 2)}
						disabled
						readonly></textarea>
				{/if}
			</div>
		</div>
	</form>
</div>

{#if showAccessModal}
	<Modal bind:show={showAccessModal} size="sm">
		<div class="px-5 py-4">
			<div class="mb-2 text-lg font-medium">访问</div>
			<p class="text-sm text-gray-400">本地演示：访问控制暂存于本机</p>
			<div class="mt-4 flex justify-end">
				<button
					type="button"
					class="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-black hover:bg-gray-200"
					onclick={() => {
						showAccessModal = false;
					}}
				>
					关闭
				</button>
			</div>
		</div>
	</Modal>
{/if}
