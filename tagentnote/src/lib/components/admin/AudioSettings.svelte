<script lang="ts">
	import { onMount } from 'svelte';
	import { audioSettingsKey } from '$lib/data/adminAudio';

	type Field = {
		id: string;
		label: string;
		type?: 'url' | 'number' | 'password' | 'checkbox' | 'textarea';
		placeholder?: string;
	};
	const apiKey: Field = { id: 'apiKey', label: 'API Key', type: 'password' };
	const baseUrl: Field = { id: 'baseUrl', label: 'API 地址', type: 'url' };
	const model: Field = { id: 'model', label: '模型' };
	const region: Field = { id: 'region', label: '区域' };
	const voice: Field = { id: 'voice', label: '语音名称或 ID' };
	const sttEngines: Record<string, { label: string; fields: Field[] }> = {
		local: { label: 'Whisper（本地）', fields: [{ ...model, placeholder: 'base' }] },
		web: { label: '浏览器 Web API', fields: [] },
		openai: { label: 'OpenAI', fields: [baseUrl, apiKey, { ...model, placeholder: 'whisper-1' }] },
		deepgram: { label: 'Deepgram', fields: [apiKey, model] },
		azure: {
			label: 'Azure AI Speech',
			fields: [
				apiKey,
				region,
				baseUrl,
				{ id: 'locales', label: '识别语言' },
				{ id: 'speakers', label: '最大说话人数', type: 'number' }
			]
		},
		mistral: {
			label: 'Mistral AI',
			fields: [
				baseUrl,
				apiKey,
				model,
				{ id: 'chatCompletions', label: '使用 Chat Completions 接口', type: 'checkbox' }
			]
		}
	};
	const ttsEngines: Record<string, { label: string; fields: Field[] }> = {
		web: { label: '浏览器 Web API', fields: [] },
		transformers: { label: 'Transformers（本地）', fields: [model, voice] },
		openai: {
			label: 'OpenAI',
			fields: [
				baseUrl,
				apiKey,
				{ ...model, placeholder: 'tts-1' },
				voice,
				{ id: 'params', label: '额外请求参数（JSON）', type: 'textarea' }
			]
		},
		elevenlabs: { label: 'ElevenLabs', fields: [apiKey, model, voice] },
		azure: {
			label: 'Azure AI Speech',
			fields: [apiKey, region, baseUrl, voice, { id: 'format', label: '音频输出格式' }]
		}
	};

	const inputClass =
		'w-full rounded-lg border border-[var(--qa-line)] bg-[var(--qa-raised)] px-3 py-2 text-sm text-[color:var(--qa-text)]';
	let sttEngine = $state('web');
	let ttsEngine = $state('web');
	let contentTypes = $state('');
	let splitOn = $state('punctuation');
	let browserVoice = $state('');
	let settings = $state<Record<string, string | number | boolean>>({});
	let secrets = $state<Record<string, string>>({});
	let voices = $state<SpeechSynthesisVoice[]>([]);
	let notice = $state('');

	onMount(() => {
		const loadVoices = () => {
			voices = window.speechSynthesis?.getVoices() ?? [];
		};
		loadVoices();
		window.speechSynthesis?.addEventListener('voiceschanged', loadVoices);
		try {
			const saved = JSON.parse(localStorage.getItem(audioSettingsKey) ?? '{}');
			sttEngine = Object.hasOwn(sttEngines, saved.sttEngine) ? saved.sttEngine : 'web';
			ttsEngine = Object.hasOwn(ttsEngines, saved.ttsEngine) ? saved.ttsEngine : 'web';
			contentTypes = saved.contentTypes ?? '';
			splitOn = saved.splitOn ?? 'punctuation';
			browserVoice = saved.browserVoice ?? '';
			settings = saved.settings ?? {};
		} catch {
			notice = '无法读取本地音频配置。';
		}
		return () => window.speechSynthesis?.removeEventListener('voiceschanged', loadVoices);
	});

	function save(event: SubmitEvent) {
		event.preventDefault();
		try {
			localStorage.setItem(
				audioSettingsKey,
				JSON.stringify({ sttEngine, ttsEngine, contentTypes, splitOn, browserVoice, settings })
			);
			notice = '音频配置已保存。API Key 仅保留在当前页面。';
		} catch {
			notice = '无法保存配置，请检查浏览器存储设置。';
		}
	}
</script>

{#snippet providerFields(fields: Field[], scope: string)}
	{#each fields as field (field.id)}
		{@const id = scope + ':' + field.id}
		<label class="grid gap-1">
			<span>{field.label}</span>
			{#if field.type === 'password'}
				<input class={inputClass} type="password" autocomplete="off" bind:value={secrets[id]} />
			{:else if field.type === 'checkbox'}
				<input class="size-4" type="checkbox" bind:checked={settings[id] as boolean} />
			{:else if field.type === 'textarea'}
				<textarea class={inputClass} rows="3" bind:value={settings[id] as string}></textarea>
			{:else}
				<input
					class={inputClass}
					type={field.type ?? 'text'}
					placeholder={field.placeholder}
					bind:value={settings[id]}
				/>
			{/if}
		</label>
	{/each}
{/snippet}

<form class="space-y-5 pb-5 text-sm" onsubmit={save}>
	<header class="pt-2">
		<h2 class="text-base font-semibold">音频</h2>
		<p class="mt-1 text-xs text-gray-400">
			配置保存在当前浏览器。答疑页目前使用浏览器语音输入和朗读，其他引擎尚未接入。
		</p>
	</header>
	<section class="space-y-4 rounded-xl border border-[var(--qa-line)] bg-[var(--qa-panel)] p-4">
		<h3 class="font-medium">语音转文字（STT）</h3>
		<label class="grid gap-1"
			>支持的音频内容类型<input
				class={inputClass}
				placeholder="例如 audio/wav, audio/mpeg"
				bind:value={contentTypes}
			/></label
		>
		<label class="grid gap-1">
			<span>语音识别引擎</span>
			<select class={inputClass} bind:value={sttEngine}>
				{#each Object.entries(sttEngines) as [id, engine] (id)}
					<option value={id}>{engine.label}</option>
				{/each}
			</select>
		</label>
		{@render providerFields(sttEngines[sttEngine].fields, 'stt:' + sttEngine)}
	</section>
	<section class="space-y-4 rounded-xl border border-[var(--qa-line)] bg-[var(--qa-panel)] p-4">
		<h3 class="font-medium">文字转语音（TTS）</h3>
		<label class="grid gap-1">
			<span>语音合成引擎</span>
			<select class={inputClass} bind:value={ttsEngine}>
				{#each Object.entries(ttsEngines) as [id, engine] (id)}
					<option value={id}>{engine.label}</option>
				{/each}
			</select>
		</label>
		{#if ttsEngine === 'web'}
			<label class="grid gap-1">
				<span>浏览器朗读声音</span>
				<select class={inputClass} bind:value={browserVoice}>
					<option value="">使用浏览器默认声音</option>
					{#each voices as option (option.voiceURI)}
						<option value={option.voiceURI}>{option.name}（{option.lang}）</option>
					{/each}
				</select>
			</label>
		{:else}
			{@render providerFields(ttsEngines[ttsEngine].fields, 'tts:' + ttsEngine)}
		{/if}
		<label class="grid gap-1">
			<span>朗读文本切分</span>
			<select class={inputClass} bind:value={splitOn}>
				<option value="punctuation">按标点切分</option>
				<option value="paragraphs">按段落切分</option>
				<option value="none">不切分</option>
			</select>
		</label>
	</section>
	<div class="flex flex-wrap items-center justify-end gap-3">
		<p role="status" class="text-xs text-gray-400">{notice}</p>
		<button
			type="submit"
			class="rounded-lg bg-[var(--qa-active)] px-4 py-2 font-medium text-[color:var(--qa-on-active)]"
			>保存</button
		>
	</div>
</form>
