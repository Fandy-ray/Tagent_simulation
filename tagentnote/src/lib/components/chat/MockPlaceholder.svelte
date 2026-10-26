<script lang="ts">
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

<div
	class={`m-auto w-full max-w-6xl px-2 text-center min-[640px]:px-20 ${chatLanding ? 'translate-y-0 py-10' : 'translate-y-6 py-24'}`}
>
	<div class="flex w-full items-center gap-4 text-center text-3xl text-gray-100">
		<div class="flex w-full flex-col items-center justify-center">
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
				<div class="flex w-fit flex-row justify-center gap-3 px-5">
					<div class="flex shrink-0 justify-center">
						<div class="flex -space-x-4">
							<div
								class="flex size-10 items-center justify-center rounded-full bg-white text-base font-black text-black"
								aria-hidden="true"
							>
								T
							</div>
						</div>
					</div>

					<div class="flex items-center text-3xl">
						<span class="line-clamp-1">
							{modelName}
						</span>
					</div>
				</div>

				<div class="mt-1 mb-2 flex min-h-3"></div>
			{/if}

			<div class="w-full py-3 text-base font-normal md:max-w-3xl">
				<MockMessageInput
					bind:prompt
					placeholder="有什么我能帮您的吗？"
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
	</div>

	{#if !chatLanding && mode === 'qa'}
		<div class="mx-auto mt-2 max-w-2xl">
			<div class="mx-5">
				<MockSuggestions inputValue={prompt} {mode} onSelect={selectSuggestion} />
			</div>
		</div>
	{/if}
</div>
