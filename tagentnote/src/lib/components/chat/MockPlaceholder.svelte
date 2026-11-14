<script lang="ts">
	import OrbitMark from '$lib/components/icons/OrbitMark.svelte';
	import MockMessageInput from './MockMessageInput.svelte';
	import type { InputAttachment } from './MessageInput/InputMenu.svelte';
	import MockSuggestions from './MockSuggestions.svelte';

	type AssistMode = 'qa' | 'paper';

	type Props = {
		modelName?: string;
		prompt?: string;
		generating?: boolean;
		mode?: AssistMode;
		temporaryChat?: boolean;
		landingPageMode?: string;
		ctrlEnterToSend?: boolean;
		largeTextAsFile?: boolean;
		enableMessageQueue?: boolean;
		showFormattingToolbar?: boolean;
		richTextInput?: boolean;
		promptAutocomplete?: boolean;
		imageCompression?: boolean;
		imageCompressionSize?: { width: string; height: string };
		insertSuggestionPrompt?: boolean;
		lastUserMessage?: string;
		speechAutoSend?: boolean;
		webSearchAlways?: boolean;
		noteOptions?: { id: string; name: string }[];
		chatOptions?: { id: string; name: string }[];
		onSubmit?: (content: string, display?: string, retrievalQuery?: string) => void;
		resolveAttachment?: (attachment: InputAttachment) => Promise<string | undefined>;
		onStop?: () => void;
		onInsertSuggestion?: (content: string) => void;
		onToast?: (message: string) => void;
		/** 论文模式的「交稿批改」「填入范例」，原样转给输入框（见 MockMessageInput） */
		onReview?: ((text: string) => void) | null;
		onFillSample?: (() => void) | null;
		knowledgeOptions?: { id: string; name: string }[];
		modelOptions?: { id: string; name: string }[];
		onSelectKnowledge?: (id: string, name: string) => void;
		onSelectModel?: (id: string, name: string) => void;
	};

	let {
		modelName = '',
		prompt = $bindable(''),
		generating = false,
		mode = 'qa',
		temporaryChat = false,
		landingPageMode = '',
		ctrlEnterToSend = false,
		largeTextAsFile = false,
		enableMessageQueue = true,
		showFormattingToolbar = false,
		richTextInput = true,
		promptAutocomplete = false,
		imageCompression = false,
		imageCompressionSize = { width: '', height: '' },
		insertSuggestionPrompt = false,
		lastUserMessage = '',
		speechAutoSend = false,
		webSearchAlways = false,
		noteOptions = [],
		chatOptions = [],
		onSubmit = () => {},
		resolveAttachment = async () => undefined,
		onStop = () => {},
		onInsertSuggestion = () => {},
		onToast = () => {},
		onReview = null,
		onFillSample = null,
		knowledgeOptions = [],
		modelOptions = [],
		onSelectKnowledge = () => {},
		onSelectModel = () => {}
	}: Props = $props();

	const chatLanding = $derived(landingPageMode === 'chat');

	const selectSuggestion = (content: string) => {
		if (insertSuggestionPrompt) {
			prompt = content;
			onInsertSuggestion(content);
			return;
		}
		prompt = content;
		onSubmit(content);
	};
</script>

<div class="qa-start m-auto w-full max-w-3xl px-4 py-8 sm:px-6">
	<div class="flex w-full flex-col">
		{#if temporaryChat}
			<div
				class="mb-3 flex items-center gap-2 text-base text-gray-500"
				title="此对话不会出现在历史记录中，消息也不会被保存。"
			>
				<svg
					class="size-4"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2.5"
					aria-hidden="true"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.522 10.522 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88"
					></path>
				</svg>
				临时对话
			</div>
		{/if}

		{#if !chatLanding}
			<div class="qa-intro">
				<span class="qa-orbit-mark"><OrbitMark /></span>
				<h1>{mode === 'qa' ? '课程答疑' : '论文助手'}</h1>
				<p>
					{mode === 'qa'
						? '围绕系统建模与仿真提问，结合教材和笔记理解课程内容。'
						: '从选题到交稿，逐步完成课程论文。'}
				</p>
			</div>
		{/if}

		<div class="w-full">
			<MockMessageInput
				bind:prompt
				placeholder={mode === 'qa' ? '输入你的课程问题…' : '有什么我能帮您的吗？'}
				{generating}
				{ctrlEnterToSend}
				{largeTextAsFile}
				{enableMessageQueue}
				{showFormattingToolbar}
				{richTextInput}
				{promptAutocomplete}
				{imageCompression}
				{imageCompressionSize}
				{lastUserMessage}
				{speechAutoSend}
				{webSearchAlways}
				{noteOptions}
				{chatOptions}
				{modelName}
				{onSubmit}
				{resolveAttachment}
				{onStop}
				{onToast}
				{onReview}
				{onFillSample}
				{knowledgeOptions}
				{modelOptions}
				{onSelectKnowledge}
				{onSelectModel}
			/>
		</div>
	</div>

	{#if !chatLanding && mode === 'qa'}
		<MockSuggestions inputValue={prompt} {mode} onSelect={selectSuggestion} />
	{/if}
</div>
