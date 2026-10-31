<script lang="ts">
	import { onMount } from 'svelte';

	import { resolve } from '$app/paths';
	import {
		adminToken,
		clearAdminToken,
		rememberAdminToken,
		rememberedAdminToken,
		restoreAdminToken
	} from '$lib/apis/admin';
	import {
		ModelAdminError,
		createModelProvider,
		deleteModelProvider,
		listModelProviders,
		probeModel,
		setDefaultModelProvider,
		updateModelProvider,
		type ModelProvider,
		type ModelProviderInput,
		type ProbeResult
	} from '$lib/apis/model-providers';

	type Preset = {
		label: string;
		name: string;
		served_model_id: string;
		base_url: string;
		upstream_model: string;
		auth_mode: 'bearer' | 'none';
	};

	// 常见的几家。都是 OpenAI 兼容接口，别的照厂商文档填就行
	const PRESETS: Preset[] = [
		{
			label: 'DeepSeek',
			name: 'DeepSeek',
			served_model_id: 'deepseek',
			base_url: 'https://api.deepseek.com',
			upstream_model: 'deepseek-chat',
			auth_mode: 'bearer'
		},
		{
			label: '通义千问',
			name: '通义千问',
			served_model_id: 'qwen',
			base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
			upstream_model: 'qwen-plus',
			auth_mode: 'bearer'
		},
		{
			label: '本机模型（LM Studio）',
			name: '本机模型',
			served_model_id: 'local',
			base_url: 'http://127.0.0.1:1234/v1',
			upstream_model: 'local-model',
			auth_mode: 'none'
		}
	];

	// 关闭思考：各家写法不一样，填进「出题、批改时的附加参数」，答疑不受影响
	const THINKING_OFF: { label: string; body: Record<string, unknown> }[] = [
		{ label: 'DeepSeek / 智谱 / 豆包', body: { thinking: { type: 'disabled' } } },
		{ label: '通义千问', body: { enable_thinking: false } }
	];

	type Form = {
		name: string;
		served_model_id: string;
		base_url: string;
		upstream_model: string;
		auth_mode: 'bearer' | 'none';
		api_key: string;
		temperature: string;
		enabled: boolean;
		extra_body: string;
		structured_extra_body: string;
	};

	const blankForm = (): Form => ({
		name: '',
		served_model_id: '',
		base_url: '',
		upstream_model: '',
		auth_mode: 'bearer',
		api_key: '',
		temperature: '0.1',
		enabled: true,
		extra_body: '',
		structured_extra_body: ''
	});

	// 和管理员面板共用一份口令：那边输过、或者这台电脑记住了，这里就不用再填
	let token = $state('');
	let remember = $state(false);
	let connected = $state(false);
	let providers = $state<ModelProvider[]>([]);
	let defaultId = $state('');
	let busy = $state(false);
	let error = $state('');
	let notice = $state('');

	/** null = 没在填表；'' = 新登记；其他 = 正在改的那条 */
	let editing = $state<string | null>(null);
	let form = $state<Form>(blankForm());
	let formError = $state('');
	let confirmDelete = $state('');
	let probes = $state<Record<string, ProbeResult | 'running'>>({});

	const run = async (task: () => Promise<void>) => {
		busy = true;
		error = '';
		notice = '';
		// 点过一次「删除」又去做别的，就不再算确认了
		confirmDelete = '';
		try {
			await task();
		} catch (failure) {
			error = failure instanceof Error ? failure.message : String(failure);
		} finally {
			busy = false;
		}
	};

	const refresh = async () => {
		let registry;
		try {
			registry = await listModelProviders(token);
		} catch (failure) {
			// 后端换过口令：记着的那份作废了，别下次进来还拿它试
			if (failure instanceof ModelAdminError && failure.status === 403) {
				clearAdminToken();
			}
			throw failure;
		}
		providers = registry.providers;
		defaultId = registry.default_model_id;
		connected = true;
		// 改过、停用过之后，之前「试一下」的结果就不作数了
		probes = {};
	};

	const connect = (event: SubmitEvent) => {
		event.preventDefault();
		if (!token.trim()) {
			error = '先填管理口令。';
			return;
		}
		void run(async () => {
			await refresh();
			adminToken.set(token.trim());
			rememberAdminToken(remember ? token : '');
		});
	};

	onMount(() => {
		restoreAdminToken();
		token = $adminToken;
		remember = rememberedAdminToken() !== '';
		if (token) {
			void run(refresh);
		}
	});

	const startCreate = () => {
		editing = '';
		formError = '';
		form = blankForm();
	};

	const startEdit = (provider: ModelProvider) => {
		editing = provider.served_model_id;
		formError = '';
		form = {
			name: provider.name,
			served_model_id: provider.served_model_id,
			base_url: provider.base_url,
			upstream_model: provider.upstream_model,
			auth_mode: provider.auth_mode,
			api_key: '',
			temperature: String(provider.temperature),
			enabled: provider.enabled,
			extra_body: Object.keys(provider.extra_body ?? {}).length
				? JSON.stringify(provider.extra_body, null, 2)
				: '',
			structured_extra_body: Object.keys(provider.structured_extra_body ?? {}).length
				? JSON.stringify(provider.structured_extra_body, null, 2)
				: ''
		};
	};

	const applyPreset = (preset: Preset) => {
		form = { ...form, ...preset };
	};

	const setThinkingOff = (body: Record<string, unknown>) => {
		let current: Record<string, unknown> = {};
		try {
			const parsed = form.structured_extra_body.trim()
				? JSON.parse(form.structured_extra_body)
				: {};
			if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
				current = parsed;
			}
		} catch {
			// 原来写坏了就整段换掉
		}
		// 两种写法只留一种
		delete current.thinking;
		delete current.enable_thinking;
		form.structured_extra_body = JSON.stringify({ ...current, ...body }, null, 2);
	};

	const parseJsonObject = (text: string): unknown => {
		if (!text.trim()) {
			return {};
		}
		const parsed: unknown = JSON.parse(text);
		if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
			throw new TypeError();
		}
		return parsed;
	};

	const readForm = (): ModelProviderInput | string => {
		const temperature = Number(form.temperature);
		if (!Number.isFinite(temperature) || temperature < 0 || temperature > 2) {
			return '温度要在 0 到 2 之间。';
		}
		let extra: unknown;
		let structured: unknown;
		try {
			extra = parseJsonObject(form.extra_body);
			structured = parseJsonObject(form.structured_extra_body);
		} catch {
			return '附加参数要写成一个 JSON 对象，例如 {"thinking": {"type": "disabled"}}。';
		}
		if (editing === '' && form.auth_mode === 'bearer' && !form.api_key.trim()) {
			return '要填 API Key。';
		}
		return {
			name: form.name.trim(),
			served_model_id: form.served_model_id.trim(),
			base_url: form.base_url.trim(),
			upstream_model: form.upstream_model.trim(),
			auth_mode: form.auth_mode,
			api_key: form.api_key,
			temperature,
			enabled: form.enabled,
			extra_body: extra as Record<string, unknown>,
			structured_extra_body: structured as Record<string, unknown>
		};
	};

	const save = (event: SubmitEvent) => {
		event.preventDefault();
		const input = readForm();
		if (typeof input === 'string') {
			formError = input;
			return;
		}
		formError = '';
		void run(async () => {
			const target = editing;
			try {
				if (target) {
					await updateModelProvider(token, target, input);
				} else {
					await createModelProvider(token, input);
				}
			} catch (failure) {
				// 填的不对就留在表单上，别把已经填好的内容清掉
				formError = failure instanceof Error ? failure.message : String(failure);
				return;
			}
			editing = null;
			form = blankForm();
			await refresh();
			notice = `已保存「${input.name}」。答疑、测评页面刷新后就能选到它；可以点「试一下」确认能用。`;
		});
	};

	const toggleEnabled = (provider: ModelProvider) =>
		void run(async () => {
			await updateModelProvider(token, provider.served_model_id, {
				name: provider.name,
				served_model_id: provider.served_model_id,
				base_url: provider.base_url,
				upstream_model: provider.upstream_model,
				auth_mode: provider.auth_mode,
				api_key: '',
				temperature: provider.temperature,
				enabled: !provider.enabled,
				extra_body: provider.extra_body ?? {},
				structured_extra_body: provider.structured_extra_body ?? {}
			});
			await refresh();
		});

	const makeDefault = (provider: ModelProvider) =>
		void run(async () => {
			await setDefaultModelProvider(token, provider.served_model_id);
			await refresh();
			notice = `默认模型改成了「${provider.name}」。`;
		});

	const remove = (provider: ModelProvider) => {
		if (confirmDelete !== provider.served_model_id) {
			confirmDelete = provider.served_model_id;
			return;
		}
		confirmDelete = '';
		void run(async () => {
			await deleteModelProvider(token, provider.served_model_id);
			if (editing === provider.served_model_id) {
				editing = null;
			}
			await refresh();
			notice = `已删除「${provider.name}」。`;
		});
	};

	const probe = async (provider: ModelProvider) => {
		probes = { ...probes, [provider.served_model_id]: 'running' };
		const result = await probeModel(token, provider.served_model_id);
		probes = { ...probes, [provider.served_model_id]: result };
	};

	const extraSummary = (body: Record<string, unknown>) => {
		const text = JSON.stringify(body ?? {});
		return text === '{}' ? '' : text;
	};

	const inputClass =
		'h-10 w-full rounded-lg border border-white/15 bg-white/[0.04] px-3 text-sm text-gray-100 outline-none transition placeholder:text-gray-600 hover:border-white/25 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20';
	const textareaClass =
		'mt-1 w-full rounded-lg border border-white/15 bg-white/[0.04] px-3 py-2 font-mono text-xs text-gray-100 transition outline-none hover:border-white/25 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20';
	const buttonClass =
		'rounded-lg border border-white/15 px-3 py-1.5 text-xs text-gray-200 transition hover:border-white/30 hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50';
</script>

<svelte:head>
	<title>模型登记 | TAgent 智能教学平台</title>
</svelte:head>

<main class="min-h-screen bg-gray-900 text-gray-100">
	<div class="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
		<header class="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-5">
			<div>
				<h1 class="text-xl font-semibold text-white">模型登记</h1>
				<p class="mt-1 text-sm text-gray-400">
					答疑、出题、批改用的大模型在这里登记。登记一次，答疑、测评、笔记本都能用。
				</p>
			</div>
			<a href={resolve('/agent-select')} class="text-sm text-gray-400 transition hover:text-white"
				>返回</a
			>
		</header>

		<form class="mt-6 rounded-xl border border-white/10 bg-white/[0.03] p-4" onsubmit={connect}>
			<label for="admin-token" class="block text-sm font-medium text-gray-200">管理口令</label>
			<p class="mt-1 text-xs leading-5 text-gray-500">
				在 <code class="text-gray-300">TAgent重写版/.env.runtime</code> 里，<code
					class="text-gray-300">AGENT_ADMIN_TOKEN=</code
				>
				后面那一串（启动脚本会自动生成）。部署在服务器上时，在服务器的部署目录运行
				<code class="text-gray-300">bash TAgent重写版/scripts/show-admin-token.sh</code> 就能看到。
			</p>
			<div class="mt-3 flex gap-2">
				<input
					id="admin-token"
					type="password"
					autocomplete="off"
					class={inputClass}
					placeholder="粘贴管理口令"
					bind:value={token}
				/>
				<button
					type="submit"
					class="shrink-0 rounded-lg bg-cyan-500 px-4 text-sm font-medium text-gray-950 transition hover:bg-cyan-400 disabled:opacity-50"
					disabled={busy}
				>
					{connected ? '刷新' : '连接'}
				</button>
			</div>
			<label class="mt-3 flex items-center gap-2 text-xs text-gray-300">
				<input type="checkbox" bind:checked={remember} />
				在这台电脑上记住（公用电脑别勾；取消勾选后点「{connected ? '刷新' : '连接'}」就清掉了）
			</label>
		</form>

		{#if error}
			<p
				class="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200"
				role="alert"
			>
				{error}
			</p>
		{/if}
		{#if notice}
			<p
				class="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200"
				role="status"
			>
				{notice}
			</p>
		{/if}

		{#if connected}
			<section class="mt-6" aria-labelledby="registered-title">
				<div class="flex items-center justify-between">
					<h2 id="registered-title" class="text-sm font-medium text-gray-200">
						已登记（{providers.length}）
					</h2>
					{#if editing === null}
						<button type="button" class={buttonClass} onclick={() => startCreate()}
							>登记新模型</button
						>
					{/if}
				</div>

				{#if providers.length === 0}
					<p class="mt-3 text-sm text-gray-500">
						还没有登记任何模型，答疑和出题都用不了。点「登记新模型」。
					</p>
				{/if}

				<ul class="mt-3 space-y-3">
					{#each providers as provider (provider.served_model_id)}
						{@const probeState = probes[provider.served_model_id]}
						<li class="rounded-xl border border-white/10 bg-white/[0.03] p-4">
							<div class="flex flex-wrap items-center gap-2">
								<span class="font-medium text-white">{provider.name}</span>
								<span class="text-xs text-gray-500">{provider.served_model_id}</span>
								{#if provider.served_model_id === defaultId}
									<span class="rounded bg-cyan-400/15 px-1.5 py-0.5 text-[11px] text-cyan-200"
										>默认</span
									>
								{/if}
								{#if !provider.enabled}
									<span class="rounded bg-gray-700 px-1.5 py-0.5 text-[11px] text-gray-300"
										>已停用</span
									>
								{/if}
							</div>
							<dl class="mt-2 grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-1 text-xs">
								<dt class="text-gray-500">接口地址</dt>
								<dd class="break-all text-gray-300">{provider.base_url}</dd>
								<dt class="text-gray-500">上游模型</dt>
								<dd class="break-all text-gray-300">{provider.upstream_model}</dd>
								<dt class="text-gray-500">API Key</dt>
								<dd class="text-gray-300">
									{provider.auth_mode === 'none' ? '不需要' : provider.api_key_masked || '未填'}
								</dd>
								<dt class="text-gray-500">温度</dt>
								<dd class="text-gray-300">{provider.temperature}</dd>
								{#if extraSummary(provider.extra_body)}
									<dt class="text-gray-500">附加参数</dt>
									<dd class="font-mono break-all text-gray-300">
										{extraSummary(provider.extra_body)}
									</dd>
								{/if}
								{#if extraSummary(provider.structured_extra_body)}
									<dt class="text-gray-500">出题批改时</dt>
									<dd class="font-mono break-all text-gray-300">
										{extraSummary(provider.structured_extra_body)}
									</dd>
								{/if}
							</dl>

							<div class="mt-3 flex flex-wrap gap-2">
								<button
									type="button"
									class={buttonClass}
									disabled={!provider.enabled || probeState === 'running'}
									onclick={() => void probe(provider)}
								>
									{probeState === 'running' ? '正在试…' : '试一下'}
								</button>
								<button
									type="button"
									class={buttonClass}
									disabled={busy}
									onclick={() => startEdit(provider)}
								>
									修改
								</button>
								{#if provider.enabled && provider.served_model_id !== defaultId}
									<button
										type="button"
										class={buttonClass}
										disabled={busy}
										onclick={() => makeDefault(provider)}
									>
										设为默认
									</button>
								{/if}
								<button
									type="button"
									class={buttonClass}
									disabled={busy}
									onclick={() => toggleEnabled(provider)}
								>
									{provider.enabled ? '停用' : '启用'}
								</button>
								<button
									type="button"
									class="{buttonClass} {confirmDelete === provider.served_model_id
										? 'border-red-400/60 text-red-200'
										: ''}"
									disabled={busy}
									onclick={() => remove(provider)}
								>
									{confirmDelete === provider.served_model_id ? '再点一次确认删除' : '删除'}
								</button>
							</div>

							{#if probeState && probeState !== 'running'}
								<p
									class="mt-3 text-xs leading-5 {probeState.ok
										? 'text-emerald-300'
										: 'text-amber-200'}"
									role="status"
								>
									{probeState.ok
										? `能用：模型回复「${probeState.reply.slice(0, 40)}」，用了 ${probeState.seconds.toFixed(1)} 秒。`
										: probeState.reason}
								</p>
							{/if}
						</li>
					{/each}
				</ul>
			</section>

			{#if editing !== null}
				<form
					class="mt-6 space-y-4 rounded-xl border border-cyan-400/30 bg-white/[0.03] p-4"
					onsubmit={save}
					aria-labelledby="form-title"
				>
					<div class="flex flex-wrap items-center justify-between gap-2">
						<h2 id="form-title" class="text-sm font-medium text-white">
							{editing ? `修改「${form.name || editing}」` : '登记新模型'}
						</h2>
						{#if !editing}
							<div class="flex flex-wrap gap-1.5">
								{#each PRESETS as preset (preset.label)}
									<button type="button" class={buttonClass} onclick={() => applyPreset(preset)}>
										{preset.label}
									</button>
								{/each}
							</div>
						{/if}
					</div>

					<div class="grid gap-4 sm:grid-cols-2">
						<label class="block text-xs text-gray-400">
							名称（页面上显示的）
							<input
								class="{inputClass} mt-1"
								bind:value={form.name}
								placeholder="DeepSeek"
								required
							/>
						</label>
						<label class="block text-xs text-gray-400">
							模型 ID（英文，登记后不能改）
							<input
								class="{inputClass} mt-1 disabled:opacity-60"
								bind:value={form.served_model_id}
								placeholder="deepseek"
								disabled={Boolean(editing)}
								required
							/>
						</label>
						<label class="block text-xs text-gray-400 sm:col-span-2">
							接口地址（OpenAI 兼容的 base URL）
							<input
								class="{inputClass} mt-1"
								bind:value={form.base_url}
								placeholder="https://api.deepseek.com"
								required
							/>
						</label>
						<label class="block text-xs text-gray-400">
							上游模型名
							<input
								class="{inputClass} mt-1"
								bind:value={form.upstream_model}
								placeholder="deepseek-chat"
								required
							/>
						</label>
						<label class="block text-xs text-gray-400">
							温度（0~2，出题批改建议 0.1）
							<input class="{inputClass} mt-1" bind:value={form.temperature} inputmode="decimal" />
						</label>
						<label class="block text-xs text-gray-400">
							鉴权
							<select class="{inputClass} mt-1" bind:value={form.auth_mode}>
								<option value="bearer">要 API Key</option>
								<option value="none">不要（本机模型）</option>
							</select>
						</label>
						{#if form.auth_mode === 'bearer'}
							<label class="block text-xs text-gray-400">
								API Key{editing ? '（留空 = 不换）' : ''}
								<input
									class="{inputClass} mt-1"
									type="password"
									autocomplete="off"
									bind:value={form.api_key}
									placeholder={editing ? '不换就留空' : 'sk-…'}
								/>
							</label>
						{/if}
					</div>

					<div>
						<div class="flex flex-wrap items-center justify-between gap-2">
							<label for="extra-body" class="text-xs text-gray-400">附加参数（JSON，可不填）</label>
							<button type="button" class={buttonClass} onclick={() => (form.extra_body = '')}
								>清空</button
							>
						</div>
						<textarea
							id="extra-body"
							rows="3"
							class={textareaClass}
							bind:value={form.extra_body}
							placeholder={'{"top_k": 5}'}></textarea>
						<p class="mt-1 text-xs leading-5 text-gray-500">
							每次请求都原样带给模型，答疑也带。各家写法不同，以厂商文档为准。
						</p>
					</div>

					<div>
						<div class="flex flex-wrap items-center justify-between gap-2">
							<label for="structured-extra-body" class="text-xs text-gray-400"
								>出题、批改时的附加参数（JSON，可不填）</label
							>
							<div class="flex flex-wrap gap-1.5">
								{#each THINKING_OFF as option (option.label)}
									<button
										type="button"
										class={buttonClass}
										onclick={() => setThinkingOff(option.body)}
									>
										关闭思考：{option.label}
									</button>
								{/each}
								<button
									type="button"
									class={buttonClass}
									onclick={() => (form.structured_extra_body = '')}>清空</button
								>
							</div>
						</div>
						<textarea
							id="structured-extra-body"
							rows="3"
							class={textareaClass}
							bind:value={form.structured_extra_body}
							placeholder={'{"thinking": {"type": "disabled"}}'}></textarea>
						<p class="mt-1 text-xs leading-5 text-gray-500">
							只有出题、闪卡、批改带，答疑不带。会先思考的模型建议在这里关思考：出题批改只要一段
							JSON，思考只是白等，第一张闪卡和整卷都会慢很多；答疑还能留着思考。「试一下」也会带上它。
						</p>
					</div>

					<label class="flex items-center gap-2 text-xs text-gray-300">
						<input type="checkbox" bind:checked={form.enabled} />
						启用（停用后页面上选不到它）
					</label>

					{#if formError}
						<p
							class="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200"
							role="alert"
						>
							{formError}
						</p>
					{/if}

					<div class="flex justify-end gap-2">
						<button
							type="button"
							class={buttonClass}
							onclick={() => {
								editing = null;
								formError = '';
							}}
						>
							取消
						</button>
						<button
							type="submit"
							class="rounded-lg bg-cyan-500 px-4 py-1.5 text-sm font-medium text-gray-950 transition hover:bg-cyan-400 disabled:opacity-50"
							disabled={busy}
						>
							保存
						</button>
					</div>
				</form>
			{/if}
		{/if}
	</div>
</main>
