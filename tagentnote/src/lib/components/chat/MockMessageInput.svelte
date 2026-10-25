<script lang="ts">
	import PlusAlt from '$lib/components/icons/PlusAlt.svelte';
	import ComponentIcon from '$lib/components/icons/Component.svelte';
	import VoiceIcon from '$lib/components/icons/Voice.svelte';
	import { countCharacters, ESSAY_MAX_CHARS, ESSAY_MIN_CHARS } from '$lib/data/essay';
	import { listPrompts, listSkills, listTools } from '$lib/data/workspaceResources';
	import InputMenu, { type InputAttachment } from './MessageInput/InputMenu.svelte';
	import IntegrationsMenu from './MessageInput/IntegrationsMenu.svelte';
	import VoiceRecording from './MessageInput/VoiceRecording.svelte';
	import CallOverlay from './MessageInput/CallOverlay.svelte';
	import { getI18nContext } from '$lib/i18n';

	const i18n = getI18nContext();

	type Props = {
		prompt?: string;
		placeholder?: string;
		disabled?: boolean;
		generating?: boolean;
		ctrlEnterToSend?: boolean;
		largeTextAsFile?: boolean;
		enableMessageQueue?: boolean;
		showFormattingToolbar?: boolean;
		richTextInput?: boolean;
		promptAutocomplete?: boolean;
		imageCompression?: boolean;
		imageCompressionSize?: { width: string; height: string };
		lastUserMessage?: string;
		speechAutoSend?: boolean;
		webSearchAlways?: boolean;
		/** 输入 `#` 时可选的知识库（笔记本）列表；「+」菜单里引用知识库也用它 */
		knowledgeOptions?: { id: string; name: string }[];
		noteOptions?: { id: string; name: string }[];
		chatOptions?: { id: string; name: string }[];
		modelName?: string;
		onSubmit?: (content: string) => void;
		onStop?: () => void;
		onPasteAsFile?: (file: File) => void;
		onEditLastMessage?: (content: string) => void;
		onToast?: (message: string) => void;
		/**
		 * 论文模式才传：显示「交稿批改」，把输入框里的**原始正文**交出去。
		 * 不走 buildPayload——那个会加「[附件:…]」之类的前缀，批注下标就对不上原文了。
		 */
		onReview?: ((text: string) => void) | null;
		/** 本机有范例论文时才传：显示「填入范例」，演示批改用 */
		onFillSample?: (() => void) | null;
		/** 输入 `@` 时可选的模型列表 */
		modelOptions?: { id: string; name: string }[];
		onSelectKnowledge?: (id: string, name: string) => void;
		onSelectModel?: (id: string, name: string) => void;
	};

	let {
		prompt = $bindable(''),
		placeholder = $i18n.t('Send a Message'),
		disabled = false,
		generating = false,
		ctrlEnterToSend = false,
		largeTextAsFile = false,
		enableMessageQueue = true,
		showFormattingToolbar = false,
		richTextInput = true,
		promptAutocomplete = false,
		imageCompression = false,
		imageCompressionSize = { width: '', height: '' },
		lastUserMessage = '',
		speechAutoSend = false,
		webSearchAlways = false,
		knowledgeOptions = [],
		noteOptions = [],
		chatOptions = [],
		modelName = '',
		onSubmit = () => {},
		onStop = () => {},
		onPasteAsFile = () => {},
		onEditLastMessage = () => {},
		onToast = () => {},
		onReview = null,
		onFillSample = null,
		modelOptions = [],
		onSelectKnowledge = () => {},
		onSelectModel = () => {}
	}: Props = $props();

	let textareaElement = $state<HTMLTextAreaElement | null>(null);
	let attachments = $state<InputAttachment[]>([]);
	let webSearchEnabled = $state(false);
	let imageGenerationEnabled = $state(false);
	let codeInterpreterEnabled = $state(false);
	let selectedToolIds = $state<string[]>([]);
	let selectedFilterIds = $state<string[]>([]);
	let recording = $state(false);
	let callOpen = $state(false);
	let commandIndex = $state(0);
	let valvesTarget = $state<{ type: 'tool' | 'filter'; id: string; name: string } | null>(null);
	let valvesDraft = $state('');
	let valvesSaved = $state('');

	const tools = listTools().map((tool) => ({
		id: tool.id,
		name: tool.name,
		description: tool.description
	}));
	const filters = listSkills().map((skill) => ({
		id: skill.id,
		name: skill.name,
		description: skill.description
	}));
	const valvesStorageKey = (target: { type: string; id: string }) =>
		`tagentnote.valves.${target.type}.${target.id}`;
	const defaultValves = (target: { type: string; id: string }) =>
		JSON.stringify(
			target.type === 'tool'
				? { priority: 0, timeout: 30, allow_network: false }
				: { priority: 0, enabled: true, model: '' },
			null,
			2
		);

	const openValves = (target: { type: 'tool' | 'filter'; id: string; name: string }) => {
		valvesTarget = target;
		valvesDraft = localStorage.getItem(valvesStorageKey(target)) ?? defaultValves(target);
		valvesSaved = '';
	};

	const saveValves = () => {
		if (!valvesTarget) return;
		try {
			const parsed: unknown = JSON.parse(valvesDraft || '{}');
			if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object')
				throw new Error('invalid');
			localStorage.setItem(valvesStorageKey(valvesTarget), JSON.stringify(parsed, null, 2));
			valvesSaved = 'Valves 已保存（本地 mock）';
		} catch {
			valvesSaved = '请输入有效的 JSON 对象';
		}
	};

	const canSendWhileGenerating = $derived(enableMessageQueue && generating);
	const showVoiceMode = $derived(!prompt.trim() && attachments.length === 0 && !generating);

	$effect(() => {
		if (webSearchAlways) webSearchEnabled = true;
	});

	const suggestions = $derived([
		$i18n.t('Summarize the key points of this lesson'),
		$i18n.t('Explain in simpler terms'),
		$i18n.t('Provide related exercises'),
		$i18n.t('Compare related concepts')
	]);

	const autocompleteHint = $derived.by(() => {
		if (!promptAutocomplete || !prompt.trim()) return '';
		const q = prompt.trim();
		return suggestions.find((s) => s.startsWith(q) && s !== q) ?? '';
	});

	const slashQuery = $derived.by(() => {
		const m = prompt.match(/^\/([^\s]*)$/);
		return m ? m[1].toLowerCase() : null;
	});

	const slashCommands = $derived.by(() => {
		if (slashQuery === null) return [];
		return listPrompts()
			.filter((p) => p.isActive !== false)
			.filter((p) => p.command.replace(/^\/+/, '').toLowerCase().includes(slashQuery))
			.sort((a, b) => a.title.localeCompare(b.title, 'zh-CN'));
	});

	$effect(() => {
		void slashCommands;
		commandIndex = 0;
	});

	const applySlashPrompt = (item: (typeof slashCommands)[number]) => {
		let content = item.content || '';
		// Simple {{var}} → leave for user to fill; replace common system vars
		const now = new Date();
		content = content
			.replaceAll('{{CURRENT_DATE}}', now.toLocaleDateString())
			.replaceAll('{{CURRENT_TIME}}', now.toLocaleTimeString())
			.replaceAll('{{CURRENT_DATETIME}}', now.toLocaleString());
		prompt = content;
		queueMicrotask(() => {
			const el = textareaElement;
			if (!el) return;
			el.focus();
			const len = el.value.length;
			el.setSelectionRange(len, len);
		});
	};

	// 输入 `#` 或 `@` 触发：# 列出知识库（笔记本）、@ 列出模型。
	// 只认「句子末尾、前面是行首或空白」的那个 token，避免把正文里的 #/@ 也当触发。
	const trigger = $derived.by(() => {
		const m = prompt.match(/(?:^|\s)([#@])([^\s]*)$/);
		if (!m) return null;
		return { symbol: m[1] as '#' | '@', query: m[2].toLowerCase() };
	});

	const triggerItems = $derived.by(() => {
		if (!trigger) return [] as { id: string; name: string }[];
		const source = trigger.symbol === '#' ? knowledgeOptions : modelOptions;
		return source.filter((item) => item.name.toLowerCase().includes(trigger.query));
	});

	// 打了 # / @ 而对应的列表是空的：模板里给一句提示；Esc 和有菜单时一样，删掉这段、提示随之消失
	const triggerEmpty = $derived(
		trigger !== null && (trigger.symbol === '#' ? knowledgeOptions : modelOptions).length === 0
	);

	$effect(() => {
		void triggerItems;
		commandIndex = 0;
	});

	const applyTrigger = (item: { id: string; name: string }) => {
		const t = trigger;
		if (!t) return;
		if (t.symbol === '#') onSelectKnowledge(item.id, item.name);
		else onSelectModel(item.id, item.name);
		// 把输入框里的 `#frag` / `@frag` 这一段去掉
		prompt = prompt.replace(/[#@][^\s]*$/, '');
		queueMicrotask(() => textareaElement?.focus());
	};

	// 字数按后端的算法（去空白后的码点数），和交稿时的长度闸是同一个数
	const reviewChars = $derived(onReview ? countCharacters(prompt) : 0);
	const reviewReady = $derived(reviewChars >= ESSAY_MIN_CHARS && reviewChars <= ESSAY_MAX_CHARS);
	const reviewTitle = $derived(
		reviewChars < ESSAY_MIN_CHARS
			? `正文至少 ${ESSAY_MIN_CHARS} 字才能批改（现在 ${reviewChars} 字）`
			: reviewChars > ESSAY_MAX_CHARS
				? `超过单次批改上限 ${ESSAY_MAX_CHARS} 字，请删减或分段交`
				: '把输入框里的正文交给批改：三个维度打分 + 逐句批注'
	);

	const submitReview = () => {
		if (!onReview || disabled || generating) return;
		onReview(prompt);
	};

	const buildPayload = (content: string) => {
		const parts: string[] = [];
		if (webSearchEnabled || webSearchAlways) parts.push('[联网搜索]');
		if (imageGenerationEnabled) parts.push('[图像生成]');
		if (codeInterpreterEnabled) parts.push('[代码解释器]');
		if (selectedToolIds.length) parts.push(`[工具:${selectedToolIds.join(',')}]`);
		if (selectedFilterIds.length) parts.push(`[过滤器:${selectedFilterIds.join(',')}]`);
		if (attachments.length) {
			parts.push(`[附件:${attachments.map((a) => a.name).join(' | ')}]`);
		}
		const prefix = parts.length ? `${parts.join(' ')}\n` : '';
		return `${prefix}${content}`.trim();
	};

	const submit = () => {
		const content = prompt.trim();
		if ((!content && attachments.length === 0) || disabled) return;
		if (generating && !enableMessageQueue) return;
		onSubmit(buildPayload(content || '请结合附件回答'));
		attachments = [];
	};

	const handleKeydown = (event: KeyboardEvent) => {
		if (event.key === 'Escape' && generating) {
			event.preventDefault();
			onStop();
			return;
		}

		if (triggerItems.length > 0) {
			if (event.key === 'ArrowDown') {
				event.preventDefault();
				commandIndex = Math.min(commandIndex + 1, triggerItems.length - 1);
				return;
			}
			if (event.key === 'ArrowUp') {
				event.preventDefault();
				commandIndex = Math.max(commandIndex - 1, 0);
				return;
			}
			if (event.key === 'Enter' || event.key === 'Tab') {
				event.preventDefault();
				const item = triggerItems[commandIndex];
				if (item) applyTrigger(item);
				return;
			}
			if (event.key === 'Escape') {
				event.preventDefault();
				prompt = prompt.replace(/[#@][^\s]*$/, '');
				return;
			}
		}

		if (triggerEmpty && event.key === 'Escape') {
			event.preventDefault();
			prompt = prompt.replace(/[#@][^\s]*$/, '');
			return;
		}

		if (slashCommands.length > 0) {
			if (event.key === 'ArrowDown') {
				event.preventDefault();
				commandIndex = Math.min(commandIndex + 1, slashCommands.length - 1);
				return;
			}
			if (event.key === 'ArrowUp') {
				event.preventDefault();
				commandIndex = Math.max(commandIndex - 1, 0);
				return;
			}
			if (event.key === 'Enter' || event.key === 'Tab') {
				event.preventDefault();
				const item = slashCommands[commandIndex];
				if (item) applySlashPrompt(item);
				return;
			}
			if (event.key === 'Escape') {
				event.preventDefault();
				prompt = '';
				return;
			}
		}

		if (event.key === 'ArrowUp' && !prompt.trim() && lastUserMessage) {
			event.preventDefault();
			prompt = lastUserMessage;
			onEditLastMessage(lastUserMessage);
			queueMicrotask(() => {
				const el = textareaElement;
				if (!el) return;
				el.focus();
				const len = el.value.length;
				el.setSelectionRange(len, len);
			});
			return;
		}

		if (event.key === 'Tab' && autocompleteHint) {
			event.preventDefault();
			prompt = autocompleteHint;
			return;
		}

		if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && event.shiftKey) {
			event.preventDefault();
			submit();
			return;
		}

		if (event.key !== 'Enter') return;
		if (ctrlEnterToSend) {
			if (event.ctrlKey || event.metaKey) {
				event.preventDefault();
				submit();
			}
			return;
		}
		if (!event.shiftKey) {
			event.preventDefault();
			submit();
		}
	};

	const wrapSelection = (prefix: string, suffix = prefix) => {
		const el = textareaElement;
		if (!el) {
			prompt = `${prefix}${prompt}${suffix}`;
			return;
		}
		const start = el.selectionStart;
		const end = el.selectionEnd;
		const selected = prompt.slice(start, end) || '文本';
		prompt = `${prompt.slice(0, start)}${prefix}${selected}${suffix}${prompt.slice(end)}`;
		queueMicrotask(() => {
			el.focus();
			el.setSelectionRange(start + prefix.length, start + prefix.length + selected.length);
		});
	};

	const compressImageFile = async (file: File): Promise<File> => {
		if (!imageCompression || !file.type.startsWith('image/')) return file;
		const maxW = Number(imageCompressionSize.width) || 1280;
		const maxH = Number(imageCompressionSize.height) || 1280;
		const bitmap = await createImageBitmap(file);
		const scale = Math.min(1, maxW / bitmap.width, maxH / bitmap.height);
		const w = Math.max(1, Math.round(bitmap.width * scale));
		const h = Math.max(1, Math.round(bitmap.height * scale));
		const canvas = document.createElement('canvas');
		canvas.width = w;
		canvas.height = h;
		const ctx = canvas.getContext('2d');
		if (!ctx) return file;
		ctx.drawImage(bitmap, 0, 0, w, h);
		const blob = await new Promise<Blob | null>((resolve) =>
			canvas.toBlob(resolve, 'image/jpeg', 0.82)
		);
		if (!blob) return file;
		return new File([blob], file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' });
	};

	const handlePaste = async (event: ClipboardEvent) => {
		const items = event.clipboardData?.items;
		if (items) {
			for (const item of items) {
				if (item.type.startsWith('image/')) {
					event.preventDefault();
					const raw = item.getAsFile();
					if (!raw) return;
					const file = await compressImageFile(raw);
					onPasteAsFile(file);
					attachments = [
						...attachments,
						{ id: `paste-${Date.now()}`, type: 'file', name: file.name }
					];
					onToast('内容已转为本地文件引用');
					return;
				}
			}
		}

		if (!largeTextAsFile) return;
		const text = event.clipboardData?.getData('text/plain') ?? '';
		if (text.length < 1500) return;
		event.preventDefault();
		const file = new File([text], `paste-${Date.now()}.txt`, { type: 'text/plain' });
		onPasteAsFile(file);
		attachments = [
			...attachments,
			{ id: `paste-text-${Date.now()}`, type: 'file', name: file.name }
		];
		onToast('内容已转为本地文件引用');
	};

	const startDictate = async () => {
		try {
			const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
			stream.getTracks().forEach((track) => track.stop());
			recording = true;
		} catch {
			onToast('无法访问麦克风');
		}
	};

	const startVoiceMode = async () => {
		try {
			const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
			stream.getTracks().forEach((track) => track.stop());
			callOpen = true;
		} catch {
			onToast('无法访问麦克风，语音模式未开启');
		}
	};

	const focus = () => {
		textareaElement?.focus();
	};
</script>

<div
	id="message-input-container"
	class="relative flex w-full flex-1 flex-col rounded-3xl border border-white/[0.08] bg-white/[0.035] px-1 text-gray-100 backdrop-blur-sm transition focus-within:border-white/[0.16] hover:border-white/[0.12]"
>
	{#if recording}
		<VoiceRecording
			bind:recording
			{speechAutoSend}
			onCancel={() => {
				recording = false;
			}}
			onConfirm={(text) => {
				prompt = `${prompt}${prompt ? ' ' : ''}${text}`.trim();
				recording = false;
				if (speechAutoSend) {
					queueMicrotask(() => submit());
				} else {
					focus();
				}
			}}
		/>
	{:else}
		{#if showFormattingToolbar && richTextInput}
			<div class="flex items-center gap-1 border-b border-white/[0.06] px-2 pt-2 pb-1">
				<button
					type="button"
					class="rounded px-1.5 py-0.5 text-xs text-gray-400 hover:bg-white/[0.06] hover:text-white"
					onclick={() => wrapSelection('**')}
					title="粗体">B</button
				>
				<button
					type="button"
					class="rounded px-1.5 py-0.5 text-xs text-gray-400 italic hover:bg-white/[0.06] hover:text-white"
					onclick={() => wrapSelection('*')}
					title="斜体">I</button
				>
				<button
					type="button"
					class="rounded px-1.5 py-0.5 text-xs text-gray-400 hover:bg-white/[0.06] hover:text-white"
					onclick={() => wrapSelection('`')}
					title="代码">`</button
				>
				<button
					type="button"
					class="rounded px-1.5 py-0.5 text-xs text-gray-400 hover:bg-white/[0.06] hover:text-white"
					onclick={() => wrapSelection('[', '](url)')}
					title="链接">链接</button
				>
			</div>
		{/if}

		{#if attachments.length > 0}
			<div class="flex flex-wrap gap-1.5 px-2.5 pt-2.5">
				{#each attachments as item (item.id)}
					<span
						class="inline-flex max-w-full items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-gray-300"
					>
						<span class="truncate">{item.name}</span>
						<button
							type="button"
							class="shrink-0 text-gray-500 hover:text-white"
							aria-label={`移除 ${item.name}`}
							onclick={() => {
								attachments = attachments.filter((a) => a.id !== item.id);
							}}
						>
							×
						</button>
					</span>
				{/each}
			</div>
		{/if}

		{#if webSearchEnabled || imageGenerationEnabled || codeInterpreterEnabled || selectedToolIds.length || selectedFilterIds.length}
			<div class="flex flex-wrap gap-1.5 px-2.5 pt-2">
				{#if webSearchEnabled}
					<span class="rounded-full bg-sky-500/15 px-2 py-0.5 text-[11px] text-sky-300"
						>联网搜索</span
					>
				{/if}
				{#if imageGenerationEnabled}
					<span class="rounded-full bg-violet-500/15 px-2 py-0.5 text-[11px] text-violet-300"
						>图像</span
					>
				{/if}
				{#if codeInterpreterEnabled}
					<span class="rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] text-amber-300"
						>代码解释器</span
					>
				{/if}
				{#each selectedFilterIds as filterId (filterId)}
					<span
						class="inline-flex items-center gap-1 rounded-full bg-fuchsia-500/15 px-2 py-0.5 text-[11px] text-fuchsia-300"
					>
						<span class="max-w-40 truncate"
							>{filters.find((item) => item.id === filterId)?.name ?? filterId}</span
						>
						<button
							type="button"
							class="shrink-0 text-fuchsia-400/70 hover:text-fuchsia-200"
							aria-label="移除该过滤器"
							onclick={() =>
								(selectedFilterIds = selectedFilterIds.filter((id) => id !== filterId))}>×</button
						>
					</span>
				{/each}
				{#each selectedToolIds as toolId (toolId)}
					<span
						class="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-300"
					>
						<span class="max-w-40 truncate"
							>{tools.find((item) => item.id === toolId)?.name ?? toolId}</span
						>
						<button
							type="button"
							class="shrink-0 text-emerald-400/70 hover:text-emerald-200"
							aria-label="移除该工具"
							onclick={() => (selectedToolIds = selectedToolIds.filter((id) => id !== toolId))}
							>×</button
						>
					</span>
				{/each}
			</div>
		{/if}

		<!-- 菜单放在滚动区外面：放在里面会被 overflow 裁掉，看不见（文娜 dd7df37） -->
		{#if slashCommands.length > 0}
			<div
				class="bg-gray-850 absolute bottom-full left-0 z-20 mb-2 max-h-56 w-full max-w-md overflow-y-auto rounded-xl border border-gray-800 py-1 shadow-lg"
			>
				<div class="px-3 py-1 text-xs text-gray-500">提示词</div>
				{#each slashCommands as item, idx (item.id)}
					<button
						type="button"
						class="flex w-full flex-col px-3 py-1.5 text-left transition {idx === commandIndex
							? 'bg-gray-800'
							: 'hover:bg-gray-800/70'}"
						onclick={() => applySlashPrompt(item)}
						onmousemove={() => {
							commandIndex = idx;
						}}
					>
						<div class="flex items-center gap-2 text-sm text-white">
							<span class="font-medium">{item.title}</span>
							<span class="text-xs text-gray-500">/{item.command.replace(/^\/+/, '')}</span>
						</div>
						{#if item.content}
							<div class="line-clamp-1 text-xs text-gray-500">{item.content}</div>
						{/if}
					</button>
				{/each}
			</div>
		{/if}
		{#if triggerItems.length > 0}
			<div
				class="bg-gray-850 absolute bottom-full left-0 z-20 mb-2 max-h-56 w-full max-w-md overflow-y-auto rounded-xl border border-gray-800 py-1 shadow-lg"
			>
				<div class="px-3 py-1 text-xs text-gray-500">
					{trigger?.symbol === '#' ? '引用知识库' : '选择模型'}
				</div>
				{#each triggerItems as item, idx (item.id)}
					<button
						type="button"
						class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-white transition {idx ===
						commandIndex
							? 'bg-gray-800'
							: 'hover:bg-gray-800/70'}"
						onclick={() => applyTrigger(item)}
						onmousemove={() => {
							commandIndex = idx;
						}}
					>
						<span class="font-medium">{item.name}</span>
					</button>
				{/each}
			</div>
		{:else if trigger && triggerEmpty}
			<!-- 打了 # / @ 却一个可选的都没有：说一声，别让人以为功能坏了（2026-10-11 Windows 测试报告）。
			     列表为空也可能是没连上（读取失败时页面把列表置空），所以两种原因都提。 -->
			<div
				class="bg-gray-850 absolute bottom-full left-0 z-20 mb-2 w-full max-w-md rounded-xl border border-gray-800 px-3 py-2 text-xs text-gray-500 shadow-lg"
				role="status"
			>
				{trigger.symbol === '#'
					? '没有可选的笔记本：从侧栏「笔记」进去新建一个；建过的话，看看 OpenNotebook 是否在运行'
					: '没有可选的模型：在顶栏模型下拉里点「去登记模型」；登记过的话，看看 basic-agent 是否在运行'}
			</div>
		{/if}
		<div class="relative max-h-[18rem] min-h-[3rem] overflow-y-auto">
			{#if autocompleteHint}
				<div
					class="pointer-events-none absolute top-3 right-3 left-3 truncate text-sm leading-6 text-gray-600"
					aria-hidden="true"
				>
					<span class="invisible">{prompt}</span><span>{autocompleteHint.slice(prompt.length)}</span
					>
				</div>
			{/if}
			<textarea
				id="chat-input"
				bind:this={textareaElement}
				bind:value={prompt}
				rows="1"
				class="relative z-[1] block min-h-[52px] w-full resize-none bg-transparent px-3 pt-3 pb-1 text-sm leading-6 text-gray-100 outline-none placeholder:text-gray-500 disabled:cursor-not-allowed disabled:opacity-50"
				{placeholder}
				{disabled}
				onkeydown={handleKeydown}
				onpaste={handlePaste}
				aria-label={placeholder}></textarea>
		</div>

		<div class="mx-0.5 mt-0.5 mb-2.5 flex max-w-full items-end justify-between" dir="ltr">
			<div class="ml-1 flex max-w-[80%] flex-1 items-center gap-0.5 self-end">
				<InputMenu
					bind:attachments
					{knowledgeOptions}
					{noteOptions}
					{chatOptions}
					{onToast}
					onClose={focus}
				>
					<PlusAlt className="size-[22px]" />
				</InputMenu>

				<span class="mx-0.5 h-4 w-px bg-white/10" aria-hidden="true"></span>

				<IntegrationsMenu
					bind:webSearchEnabled
					bind:imageGenerationEnabled
					bind:codeInterpreterEnabled
					bind:selectedToolIds
					bind:selectedFilterIds
					{tools}
					{filters}
					onShowValves={openValves}
					onClose={focus}
				>
					<ComponentIcon className="size-[18px]" strokeWidth="1.5" />
				</IntegrationsMenu>

				{#if canSendWhileGenerating}
					<span class="ml-2 text-[11px] text-gray-500">生成中 · 发送将加入队列</span>
				{/if}
			</div>

			<div class="mr-1 flex shrink-0 items-center gap-1 self-end">
				{#if generating}
					<button
						type="button"
						class="flex size-8 items-center justify-center rounded-full bg-white text-black transition hover:bg-gray-200"
						onclick={onStop}
						title="停止生成"
						aria-label="停止生成"
					>
						<span class="size-2.5 rounded-[2px] bg-black"></span>
					</button>
					{#if enableMessageQueue && (prompt.trim() || attachments.length)}
						<button
							type="button"
							class="flex size-8 items-center justify-center rounded-full border border-white/20 text-white transition hover:bg-white/[0.08]"
							onclick={submit}
							{disabled}
							title="加入队列"
							aria-label="加入队列"
						>
							<svg
								class="size-[18px]"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
								aria-hidden="true"
							>
								<path d="M12 19V5"></path>
								<path d="m5 12 7-7 7 7"></path>
							</svg>
						</button>
					{/if}
				{:else}
					{#if onReview}
						{#if onFillSample && !prompt.trim()}
							<button
								type="button"
								class="rounded-full px-2.5 py-1 text-xs text-gray-400 transition hover:bg-white/[0.06] hover:text-white"
								onclick={onFillSample}
								title="把本机的范例论文填进输入框，演示批改用"
							>
								填入范例
							</button>
						{/if}
						{#if prompt.trim()}
							<span
								class={`text-[11px] tabular-nums ${reviewReady ? 'text-gray-500' : 'text-amber-300/80'}`}
							>
								{reviewChars.toLocaleString()} 字
							</span>
						{/if}
						<button
							type="button"
							class="rounded-full border border-amber-300/40 px-3 py-1 text-xs font-medium text-amber-100 transition hover:bg-amber-300/10 disabled:cursor-not-allowed disabled:border-white/15 disabled:text-gray-500"
							onclick={submitReview}
							disabled={disabled || !reviewReady}
							title={reviewTitle}
						>
							交稿批改
						</button>
					{/if}
					<button
						type="button"
						class="flex size-8 items-center justify-center rounded-full text-white transition outline-none hover:bg-gray-800"
						title="语音输入"
						aria-label="语音输入"
						onclick={() => void startDictate()}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 20 20"
							fill="currentColor"
							class="size-5 translate-y-[0.5px]"
						>
							<path d="M7 4a3 3 0 016 0v6a3 3 0 11-6 0V4z" />
							<path
								d="M5.5 9.643a.75.75 0 00-1.5 0V10c0 3.06 2.29 5.585 5.25 5.954V17.5h-1.5a.75.75 0 000 1.5h4.5a.75.75 0 000-1.5h-1.5v-1.546A6.001 6.001 0 0016 10v-.357a.75.75 0 00-1.5 0V10a4.5 4.5 0 01-9 0v-.357z"
							/>
						</svg>
					</button>

					{#if showVoiceMode}
						<button
							type="button"
							class="flex items-center self-center rounded-full bg-white p-1.5 text-black transition hover:bg-gray-100"
							title="语音模式"
							aria-label="语音模式"
							onclick={() => void startVoiceMode()}
						>
							<VoiceIcon className="size-5" strokeWidth="2.5" />
						</button>
					{:else}
						<button
							type="button"
							id="send-message-button"
							class="flex size-8 items-center justify-center rounded-full bg-white text-black transition hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-30"
							onclick={submit}
							disabled={disabled || (!prompt.trim() && attachments.length === 0)}
							title="发送消息"
							aria-label="发送消息"
						>
							<svg
								class="size-[18px]"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
								aria-hidden="true"
							>
								<path d="M12 19V5"></path>
								<path d="m5 12 7-7 7 7"></path>
							</svg>
						</button>
					{/if}
				{/if}
			</div>
		</div>
	{/if}
</div>

<CallOverlay
	bind:open={callOpen}
	{modelName}
	onClose={() => {
		callOpen = false;
	}}
	onSubmit={(content) => {
		onSubmit(content);
	}}
/>

{#if valvesTarget}
	<div
		class="fixed inset-0 z-[130] flex items-center justify-center bg-black/60 p-4"
		role="presentation"
		onclick={(event) => {
			if (event.target === event.currentTarget) valvesTarget = null;
		}}
	>
		<div
			class="w-full max-w-lg rounded-2xl border border-gray-700 bg-gray-900 p-5 text-gray-100 shadow-2xl"
			role="dialog"
			aria-modal="true"
			aria-labelledby="input-valves-title"
			tabindex="-1"
		>
			<div class="flex items-start justify-between gap-3">
				<div>
					<h2 id="input-valves-title" class="text-lg font-semibold">Valves 设置</h2>
					<p class="mt-1 text-xs text-gray-400">
						{valvesTarget.name} · {valvesTarget.type === 'tool'
							? '工具'
							: '过滤器'}配置，仅保存在本地
					</p>
				</div>
				<button
					class="rounded-lg p-1 text-gray-400 hover:bg-gray-800 hover:text-white"
					onclick={() => (valvesTarget = null)}
					aria-label="关闭">×</button
				>
			</div>
			<textarea
				class="mt-4 min-h-48 w-full resize-y rounded-lg border border-gray-700 bg-[#111827] p-3 font-mono text-xs text-gray-100 outline-none focus:border-blue-500"
				bind:value={valvesDraft}
				spellcheck="false"
				aria-label="Valves JSON"></textarea>
			{#if valvesSaved}<p
					class="mt-2 text-xs {valvesSaved.includes('无效') ? 'text-red-400' : 'text-emerald-400'}"
					role="status"
				>
					{valvesSaved}
				</p>{/if}
			<div class="mt-4 flex justify-end gap-2">
				<button
					type="button"
					class="rounded-lg px-3 py-2 text-sm text-gray-300 hover:bg-gray-800"
					onclick={() => {
						if (!valvesTarget) return;
						valvesDraft = defaultValves(valvesTarget);
						valvesSaved = '';
					}}>恢复默认</button
				>
				<button
					type="button"
					class="rounded-lg bg-white px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-200"
					onclick={saveValves}>保存 Valves</button
				>
			</div>
		</div>
	</div>
{/if}
