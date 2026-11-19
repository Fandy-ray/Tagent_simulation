<script lang="ts">
	import { untrack, type Component } from 'svelte';

	import { applyTheme, type UserSettings } from '$lib/data/userSettings';
	import { getI18nContext } from '$lib/i18n';

	const i18n = getI18nContext();

	type Props = {
		settings: UserSettings;
		saveSettings: (updated: Partial<UserSettings>) => Promise<void> | void;
		onSave?: () => void;
	};

	let { settings, saveSettings, onSave = () => {} }: Props = $props();

	const buildParams = (source: Record<string, unknown> = {}) => {
		const next = { ...source };
		const stopRaw = next.stop;
		const customParams = { ...(next.custom_params ?? {}) };
		delete next.stop;
		delete next.custom_params;
		return {
			stream_response: null,
			stream_delta_chunk_size: null,
			function_calling: null,
			reasoning_tags: null,
			seed: null,
			temperature: null,
			reasoning_effort: null,
			logit_bias: null,
			frequency_penalty: null,
			presence_penalty: null,
			repeat_penalty: null,
			repeat_last_n: null,
			mirostat: null,
			mirostat_eta: null,
			mirostat_tau: null,
			top_k: null,
			top_p: null,
			min_p: null,
			tfs_z: null,
			num_ctx: null,
			num_batch: null,
			num_keep: null,
			max_tokens: null,
			num_gpu: null,
			...next,
			stop: Array.isArray(stopRaw) ? stopRaw.join(',') : (stopRaw ?? null),
			custom_params: customParams
		};
	};

	let selectedTheme = $state<UserSettings['theme']>(untrack(() => settings.theme));
	let lang = $state(untrack(() => settings.language));
	let notificationEnabled = $state(untrack(() => settings.notificationEnabled));
	let system = $state(untrack(() => settings.system));
	let showAdvanced = $state(false);
	let params = $state<Record<string, unknown>>(untrack(() => buildParams(settings.params ?? {})));
	let advancedLoading = $state(false);

	let AdvancedParamsComp = $state<Component | null>(null);

	const themeChangeHandler = async (theme: UserSettings['theme']) => {
		selectedTheme = theme;
		applyTheme(theme);
		await saveSettings({ theme });
	};

	const toggleNotification = async () => {
		if (!notificationEnabled) {
			const permission = await Notification.requestPermission().catch(() => 'denied');
			if (permission !== 'granted') {
				alert('无法启用回复通知：网站通知权限已被拒绝。请在浏览器设置中允许通知访问。');
				return;
			}
		}
		notificationEnabled = !notificationEnabled;
		await saveSettings({ notificationEnabled });
	};

	const toggleAdvanced = async () => {
		if (showAdvanced) {
			showAdvanced = false;
			return;
		}
		showAdvanced = true;
		if (!AdvancedParamsComp) {
			advancedLoading = true;
			try {
				const mod = await import('$lib/components/chat/Settings/Advanced/AdvancedParams.svelte');
				AdvancedParamsComp = mod.default;
			} finally {
				advancedLoading = false;
			}
		}
		queueMicrotask(() => {
			document.getElementById('settings-advanced-params')?.scrollIntoView({
				block: 'nearest',
				behavior: 'smooth'
			});
		});
	};

	const saveHandler = async () => {
		await saveSettings({
			system: system !== '' ? system : '',
			language: lang,
			params: {
				stream_response: params.stream_response !== null ? params.stream_response : undefined,
				stream_delta_chunk_size:
					params.stream_delta_chunk_size !== null ? params.stream_delta_chunk_size : undefined,
				function_calling: params.function_calling !== null ? params.function_calling : undefined,
				seed: params.seed !== null ? params.seed : undefined,
				stop: params.stop
					? String(params.stop)
							.split(',')
							.filter((e: string) => e)
					: undefined,
				temperature: params.temperature !== null ? params.temperature : undefined,
				reasoning_effort: params.reasoning_effort !== null ? params.reasoning_effort : undefined,
				logit_bias: params.logit_bias !== null ? params.logit_bias : undefined,
				frequency_penalty: params.frequency_penalty !== null ? params.frequency_penalty : undefined,
				presence_penalty: params.presence_penalty !== null ? params.presence_penalty : undefined,
				repeat_penalty: params.repeat_penalty !== null ? params.repeat_penalty : undefined,
				repeat_last_n: params.repeat_last_n !== null ? params.repeat_last_n : undefined,
				mirostat: params.mirostat !== null ? params.mirostat : undefined,
				mirostat_eta: params.mirostat_eta !== null ? params.mirostat_eta : undefined,
				mirostat_tau: params.mirostat_tau !== null ? params.mirostat_tau : undefined,
				top_k: params.top_k !== null ? params.top_k : undefined,
				top_p: params.top_p !== null ? params.top_p : undefined,
				min_p: params.min_p !== null ? params.min_p : undefined,
				tfs_z: params.tfs_z !== null ? params.tfs_z : undefined,
				num_ctx: params.num_ctx !== null ? params.num_ctx : undefined,
				num_batch: params.num_batch !== null ? params.num_batch : undefined,
				num_keep: params.num_keep !== null ? params.num_keep : undefined,
				max_tokens: params.max_tokens !== null ? params.max_tokens : undefined,
				num_gpu: params.num_gpu !== null ? params.num_gpu : undefined,
				think: params.think !== null ? params.think : undefined,
				keep_alive: params.keep_alive !== null ? params.keep_alive : undefined,
				format: params.format !== null ? params.format : undefined,
				custom_params: params.custom_params ?? {}
			}
		});
		onSave();
	};
</script>

<div class="flex h-full min-h-0 flex-col justify-between text-sm" id="tab-general">
	<div class="min-h-0 flex-1 overflow-y-auto pr-1">
		<div>
			<div class="mb-1 text-sm font-medium">{$i18n.t('WebUI Settings')}</div>

			<div class="flex w-full justify-between">
				<div class="self-center text-xs font-medium">{$i18n.t('Theme')}</div>
				<div class="relative flex items-center">
					<select
						class="w-fit rounded-sm bg-transparent px-2 py-2 pr-8 text-right text-xs outline-none"
						bind:value={selectedTheme}
						onchange={() => themeChangeHandler(selectedTheme)}
					>
						<option value="dark" class="bg-gray-800">深空</option>
						<option value="light" class="bg-gray-800">空间站</option>
					</select>
				</div>
			</div>

			<div>
				<div class="flex w-full justify-between py-0.5">
					<div class="self-center text-xs font-medium">{$i18n.t('Desktop Notification')}</div>
					<button
						class="flex rounded-sm px-3 py-1 text-xs transition"
						onclick={toggleNotification}
						type="button"
						role="switch"
						aria-checked={notificationEnabled}
					>
						{#if notificationEnabled}
							<span class="ml-2 self-center">{$i18n.t('Enabled')}</span>
						{:else}
							<span class="ml-2 self-center">{$i18n.t('Disabled')}</span>
						{/if}
					</button>
				</div>
			</div>
		</div>

		<hr class="border-gray-850/30 my-3" />

		<div>
			<div class="my-2.5 text-sm font-medium">{$i18n.t('System Prompt')}</div>
			<textarea
				bind:value={system}
				class="w-full resize-y bg-transparent text-sm text-gray-300 outline-none"
				rows="4"
				placeholder={$i18n.t('System Prompt Placeholder')}></textarea>
		</div>

		<div class="mt-2 space-y-3 pr-1.5">
			<div class="flex items-center justify-between text-sm">
				<div class="font-medium">{$i18n.t('Advanced Parameters Title')}</div>
				<button
					class="text-xs font-medium text-gray-500 hover:text-gray-300"
					type="button"
					aria-expanded={showAdvanced}
					onclick={toggleAdvanced}
				>
					{showAdvanced ? $i18n.t('Hide') : $i18n.t('Show')}
				</button>
			</div>

			{#if showAdvanced}
				<div id="settings-advanced-params" class="pb-4 text-gray-200">
					{#if advancedLoading || !AdvancedParamsComp}
						<p class="py-3 text-xs text-gray-500">{$i18n.t('Loading Advanced Params')}</p>
					{:else}
						<AdvancedParamsComp admin={true} custom={true} bind:params />
					{/if}
				</div>
			{/if}
		</div>
	</div>

	<div class="flex shrink-0 justify-end pt-3 text-sm font-medium">
		<button
			class="rounded-full bg-white px-3.5 py-1.5 text-sm font-medium text-black transition hover:bg-gray-100"
			onclick={saveHandler}
			type="button"
		>
			{$i18n.t('Save')}
		</button>
	</div>
</div>
