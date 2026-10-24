<script lang="ts">
	import MarkdownContent from '$lib/components/chat/MarkdownContent.svelte';
	import PaperReviewCard from '$lib/components/chat/PaperReviewCard.svelte';
	import PaperTopicCard from '$lib/components/chat/PaperTopicCard.svelte';
	import CitationLinks from '$lib/components/sources/CitationLinks.svelte';
	import type { EssayTopic } from '$lib/data/essay';
	import type { QaMessage } from '$lib/data/qaConversations';

	export type MockMessage = QaMessage;

	type Props = {
		messages?: MockMessage[];
		generating?: boolean;
		modelName?: string;
		/** 把 served_model_id 换成登记时填的显示名；认不出来就原样显示 */
		resolveModelName?: (id: string | undefined) => string;
		userName?: string;
		chatBubble?: boolean;
		widescreenMode?: boolean;
		showUsername?: boolean;
		regenerateMenu?: boolean;
		collapseCodeBlocks?: boolean;
		fadeStreaming?: boolean;
		expandDetails?: boolean;
		detectArtifacts?: boolean;
		iframeSandboxAllowSameOrigin?: boolean;
		iframeSandboxAllowForms?: boolean;
		showFloatingActionButtons?: boolean;
		floatingActionButtons?: { id: string; label: string; input: boolean; prompt: string }[] | null;
		copyFormatted?: boolean;
		keepFollowUpPrompts?: boolean;
		insertFollowUpPrompt?: boolean;
		onCopy?: (content: string) => void;
		onRegenerate?: (messageId: string) => void;
		onContinue?: (messageId: string) => void;
		continueLabel?: string;
		onEditMessage?: (messageId: string, content: string) => void;
		onSaveToNotebook?: (messageId: string) => void;
		onQuickAction?: (prompt: string, displayContent?: string) => void;
		onFollowUp?: (prompt: string, insertOnly?: boolean) => void;
		onToast?: (message: string) => void;
		/** 任务卡上当前的论文题目，题目卡据此显示「已设为本次题目」 */
		currentTopic?: string;
		onAdoptTopic?: (topic: EssayTopic) => void;
		/** 出题卡 / 批改卡上的「重新出题」「重新批改」 */
		onRetryPaperCard?: (messageId: string) => void;
	};

	let {
		messages = [],
		generating = false,
		modelName = '',
		resolveModelName = undefined,
		userName = '',
		chatBubble = true,
		widescreenMode = false,
		showUsername = false,
		regenerateMenu = true,
		collapseCodeBlocks = false,
		fadeStreaming = true,
		expandDetails = false,
		detectArtifacts = true,
		iframeSandboxAllowSameOrigin = false,
		iframeSandboxAllowForms = false,
		showFloatingActionButtons = true,
		floatingActionButtons = null,
		copyFormatted = true,
		keepFollowUpPrompts = false,
		insertFollowUpPrompt = false,
		onCopy = () => {},
		onRegenerate = () => {},
		onContinue = () => {},
		continueLabel = '继续回答',
		onEditMessage = () => {},
		onSaveToNotebook = () => {},
		onQuickAction = () => {},
		onFollowUp = () => {},
		onToast = () => {},
		currentTopic = '',
		onAdoptTopic = () => {},
		onRetryPaperCard = () => {}
	}: Props = $props();

	let feedback = $state<Record<string, 'up' | 'down' | undefined>>({});
	let editingId = $state<string | null>(null);
	let editDraft = $state('');
	let speakingId = $state<string | null>(null);

	const defaultActions = [
		{
			id: 'ask',
			label: '提问',
			input: true,
			prompt: '{{SELECTED_CONTENT}}\n\n\n{{INPUT_CONTENT}}'
		},
		{ id: 'explain', label: '解释', input: false, prompt: '{{SELECTED_CONTENT}}\n\n\n解释' }
	];

	const actions = $derived(floatingActionButtons?.length ? floatingActionButtons : defaultActions);
	const lastAssistantId = $derived(
		[...messages].reverse().find((m) => m.role === 'assistant' && !m.streaming)?.id
	);

	const stopSpeak = () => {
		try {
			window.speechSynthesis?.cancel();
		} catch {
			/* ignore */
		}
		speakingId = null;
	};

	const speakMessage = (messageId: string, content: string) => {
		const text = content
			.replace(/```[\s\S]*?```/g, ' ')
			.replace(/[#>*_`]/g, '')
			.trim();
		if (!text) {
			onToast('没有可朗读的内容');
			return;
		}
		if (speakingId === messageId) {
			stopSpeak();
			return;
		}
		stopSpeak();
		if (!window.speechSynthesis) {
			onToast('当前浏览器不支持朗读');
			return;
		}
		const utter = new SpeechSynthesisUtterance(text);
		utter.lang = 'zh-CN';
		utter.onend = () => {
			if (speakingId === messageId) speakingId = null;
		};
		utter.onerror = () => {
			speakingId = null;
		};
		speakingId = messageId;
		window.speechSynthesis.speak(utter);
	};

	const startEdit = (message: MockMessage) => {
		editingId = message.id;
		editDraft = message.content;
	};

	const cancelEdit = () => {
		editingId = null;
		editDraft = '';
	};

	const confirmEdit = () => {
		if (!editingId) return;
		onEditMessage(editingId, editDraft);
		editingId = null;
		editDraft = '';
	};

	const copyMessage = async (content: string) => {
		try {
			if (copyFormatted) {
				await navigator.clipboard.write([
					new ClipboardItem({
						'text/plain': new Blob([content], { type: 'text/plain' }),
						'text/html': new Blob(
							[`<pre>${content.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>`],
							{ type: 'text/html' }
						)
					})
				]);
			} else {
				await navigator.clipboard.writeText(content);
			}
			onToast('已复制');
		} catch {
			try {
				await navigator.clipboard.writeText(content);
				onToast('已复制');
			} catch {
				onCopy(content);
			}
		}
	};

	// 拖选的文字优先；没有拖选时，批改卷子里点中的那一句也算：画线的句子点一下会高亮
	// （AnnotatedText 的 mark:focus），学生看来就是「选中了这句」，可它不是文字选区，getSelection 读出来是空的。
	// 点中的句子只认按钮所在的这条消息：解释完那句仍高亮着，换到别的回答下面点按钮不该又拿它。
	const selectedText = (button: Element) => {
		const text = window.getSelection()?.toString()?.trim();
		if (text) {
			return text;
		}
		const focused = document.activeElement;
		return focused instanceof HTMLElement &&
			focused.matches('mark[data-note]') &&
			button.closest('article')?.contains(focused)
			? (focused.textContent?.trim() ?? '')
			: '';
	};

	// 按下按钮那一刻先记下来：点击会挪走焦点（Chrome 给按钮、Safari 清空），点中的那句到 click 时就不算了。
	// 按钮上的 mousedown 也拦掉，选区和点中那句的高亮都留在原处，看得见解释的是哪句。
	let pressedSelection = '';

	const hasPaperReview = $derived(messages.some((m) => m.paperCard?.kind === 'review'));

	const runQuickAction = (
		action: { prompt: string; input: boolean; label: string },
		event: MouseEvent & { currentTarget: HTMLButtonElement }
	) => {
		// 键盘触发的 click 没有按下这一步（detail 为 0），记下的可能是上回右键、按住拖走留下的
		const selected =
			(event.detail > 0 ? pressedSelection : '') || selectedText(event.currentTarget);
		pressedSelection = '';
		if (!selected && action.prompt.includes('{{SELECTED_CONTENT}}')) {
			onToast(
				hasPaperReview
					? '先选中回答里的一段文字，或点一下批改里画线的句子'
					: '先选中回答里的一段文字'
			);
			return;
		}
		let prompt = action.prompt.replaceAll('{{SELECTED_CONTENT}}', selected);
		if (action.input) {
			const input = window.prompt(`补充输入（${action.label}）`, '');
			if (input === null) {
				return; // 点了取消：什么都不发
			}
			prompt = prompt.replaceAll('{{INPUT_CONTENT}}', input);
		} else {
			prompt = prompt.replaceAll('{{INPUT_CONTENT}}', '');
		}
		// 展示用：以选中文字开头的快捷操作，把它渲染成「粗竖条 + 灰字」单独一行，后面换行接其余内容
		// （「提问」接补充的问题，「解释」接“解释”）。只影响聊天气泡显示，发给模型的仍是 prompt 里干净的内容。
		const remainder = prompt.slice(selected.length).replace(/^\n+/, '\n');
		// 选中的是好几行时，引用部分并成一行：气泡只把第一行画成灰色引用，不并的话后几行会混进提问里
		const display =
			selected && action.prompt.startsWith('{{SELECTED_CONTENT}}')
				? `▎${selected.replace(/\s+/g, ' ').trim()}${remainder}`.trimEnd()
				: undefined;
		onQuickAction(prompt.trim(), display);
	};

	$effect(() => {
		return () => stopSpeak();
	});
</script>

<div
	class={`mx-auto w-full px-4 pt-4 pb-28 md:px-6 ${widescreenMode ? 'max-w-full' : 'max-w-3xl'}`}
>
	<div class="flex flex-col gap-7">
		{#each messages as message (message.id)}
			{#if message.role === 'user'}
				<article
					class="group flex w-full justify-end"
					data-message-id={message.id}
					id={`message-${message.id}`}
				>
					<div class="max-w-[90%]">
						{#if showUsername && userName}
							<div class="mb-1 text-right text-xs text-gray-500">{userName}</div>
						{/if}
						<div
							class={`px-4 py-2 text-sm leading-6 text-gray-100 ${
								chatBubble ? 'rounded-3xl bg-gray-800' : 'bg-transparent'
							}`}
						>
							{#if message.content.startsWith('▎')}
								{@const selected = message.content.slice(1)}
								{@const newline = selected.indexOf('\n')}
								<p class="whitespace-pre-wrap">
									<span class="text-gray-400"
										>▎{newline >= 0 ? selected.slice(0, newline) : selected}</span
									>{newline >= 0 ? `\n${selected.slice(newline + 1)}` : ''}
								</p>
							{:else}
								<p class="whitespace-pre-wrap">{message.content}</p>
							{/if}
						</div>

						<div
							class="mt-1 flex justify-end text-gray-500 opacity-0 transition group-hover:opacity-100"
						>
							<button
								type="button"
								class="rounded-lg p-1.5 transition hover:bg-white/[0.06] hover:text-white"
								onclick={() => copyMessage(message.content)}
								title="复制"
								aria-label="复制用户消息"
							>
								<svg
									class="size-4"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.8"
									stroke-linecap="round"
									stroke-linejoin="round"
									aria-hidden="true"
								>
									<rect x="9" y="9" width="11" height="11" rx="2"></rect>
									<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
								</svg>
							</button>
						</div>
					</div>
				</article>
			{:else}
				<article
					class="group flex w-full"
					data-message-id={message.id}
					id={`message-${message.id}`}
				>
					<div class="mt-1 mr-3 hidden shrink-0 sm:flex">
						<div
							class="flex size-8 items-center justify-center rounded-full bg-white text-[9px] font-black text-black"
						>
							OI
						</div>
					</div>

					<div class="relative w-0 flex-auto pl-1">
						<div class="mb-1 flex items-center gap-2">
							<span class="line-clamp-1 text-sm font-medium text-white">
								{resolveModelName?.(message.model) || message.model || modelName}
							</span>
						</div>

						{#if editingId === message.id}
							<div class="w-full">
								<textarea
									bind:value={editDraft}
									rows="6"
									class="w-full resize-y rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm leading-6 text-gray-100 outline-none"
									aria-label="编辑回答"></textarea>
								<div class="mt-2 flex justify-end gap-2">
									<button
										type="button"
										class="rounded-full px-3 py-1 text-xs text-gray-400 hover:bg-white/[0.06] hover:text-white"
										onclick={cancelEdit}
									>
										取消
									</button>
									<button
										type="button"
										class="rounded-full bg-white px-3 py-1 text-xs font-medium text-black hover:bg-gray-100"
										onclick={confirmEdit}
									>
										保存
									</button>
								</div>
							</div>
						{:else}
							<div class="w-full min-w-full">
								{#if message.paperCard?.kind === 'review'}
									<PaperReviewCard
										id={message.id}
										card={message.paperCard}
										pending={!!message.streaming}
										onRetry={() => onRetryPaperCard(message.id)}
									/>
								{:else if message.paperCard?.kind === 'topic'}
									<PaperTopicCard
										card={message.paperCard}
										pending={!!message.streaming}
										adopted={!!message.paperCard.topic &&
											message.paperCard.topic.title === currentTopic.trim()}
										onAdopt={onAdoptTopic}
										onRetry={() => onRetryPaperCard(message.id)}
									/>
								{:else}
									<MarkdownContent
										content={message.content}
										streaming={message.streaming}
										{collapseCodeBlocks}
										{fadeStreaming}
										{expandDetails}
										{detectArtifacts}
										{iframeSandboxAllowSameOrigin}
										{iframeSandboxAllowForms}
									/>
									<CitationLinks citations={message.citations ?? []} />
									{#if message.interrupted && !message.streaming}
										<p class="mt-2 text-xs leading-5 text-amber-300/80">
											这次回答没有完成（中途停止、刷新、关闭页面或断网了）。点下面的「重新生成」再答一次。
										</p>
									{/if}
								{/if}
							</div>

							{#if (message.followUps?.length ?? 0) > 0 && (keepFollowUpPrompts || message.id === lastAssistantId) && !message.streaming}
								<div class="mt-2 flex flex-wrap gap-1">
									<!-- 存在浏览器里的旧对话可能有重复项：key 带上序号，重复了也不至于整条消息渲染出错 -->
									{#each message.followUps ?? [] as followUp, index (`${index}:${followUp}`)}
										<button
											type="button"
											class="rounded-full bg-white/[0.06] px-2 py-0.5 text-left text-xs text-gray-400 transition hover:text-white"
											onclick={() => onFollowUp(followUp, insertFollowUpPrompt)}
										>
											{followUp}
										</button>
									{/each}
								</div>
							{/if}

							{#if (message.tags?.length ?? 0) > 0 && !message.streaming}
								<div class="mt-1.5 flex flex-wrap gap-1">
									{#each message.tags ?? [] as tag, index (`${index}:${tag}`)}
										<span class="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-gray-400"
											>#{tag}</span
										>
									{/each}
								</div>
							{/if}

							{#if !message.streaming}
								{@const isLast = message.id === lastAssistantId}
								<div
									class={`mt-0.5 flex flex-wrap items-center whitespace-nowrap text-gray-500 ${
										isLast ? 'visible' : 'invisible group-hover:visible'
									}`}
								>
									{#if !message.paperCard}
										<button
											type="button"
											class="rounded-lg p-1.5 transition hover:bg-white/[0.06] hover:text-white"
											onclick={() => startEdit(message)}
											title="编辑"
											aria-label="编辑回答"
										>
											<svg
												class="size-4"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												stroke-width="2.3"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487zm0 0L19.5 7.125"
												></path>
											</svg>
										</button>
									{/if}

									<button
										type="button"
										class="copy-response-button rounded-lg p-1.5 transition hover:bg-white/[0.06] hover:text-white"
										onclick={() => copyMessage(message.content)}
										title="复制"
										aria-label="复制回答"
									>
										<svg
											class="size-4"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="2.3"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184"
											></path>
										</svg>
									</button>

									<button
										type="button"
										id={`speak-button-${message.id}`}
										class="rounded-lg p-1.5 transition hover:bg-white/[0.06] hover:text-white"
										onclick={() => speakMessage(message.id, message.content)}
										title={speakingId === message.id ? '停止朗读' : '朗读'}
										aria-label={speakingId === message.id ? '停止朗读' : '朗读回答'}
									>
										{#if speakingId === message.id}
											<svg
												class="size-4"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												stroke-width="2.3"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M17.25 9.75 19.5 12m0 0 2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6 4.72-4.72a.75.75 0 0 1 1.28.53v15.88a.75.75 0 0 1-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.009 9.009 0 0 1 2.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75Z"
												></path>
											</svg>
										{:else}
											<svg
												class="size-4"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												stroke-width="2.3"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z"
												></path>
											</svg>
										{/if}
									</button>

									<button
										type="button"
										class={`rounded-lg p-1.5 transition hover:bg-white/[0.06] hover:text-white ${
											feedback[message.id] === 'up' ? 'bg-white/[0.08] text-white' : ''
										}`}
										onclick={() => {
											feedback[message.id] = feedback[message.id] === 'up' ? undefined : 'up';
										}}
										title="有帮助"
										aria-label="有帮助"
									>
										<svg
											class="size-4"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="2.3"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"
											></path>
										</svg>
									</button>

									<button
										type="button"
										class={`rounded-lg p-1.5 transition hover:bg-white/[0.06] hover:text-white ${
											feedback[message.id] === 'down' ? 'bg-white/[0.08] text-white' : ''
										}`}
										onclick={() => {
											feedback[message.id] = feedback[message.id] === 'down' ? undefined : 'down';
										}}
										title="没有帮助"
										aria-label="没有帮助"
									>
										<svg
											class="size-4"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="2.3"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"
											></path>
										</svg>
									</button>

									{#if isLast && !generating && !message.paperCard}
										<button
											type="button"
											id="continue-response-button"
											class="rounded-lg p-1.5 transition hover:bg-white/[0.06] hover:text-white"
											onclick={() => onContinue(message.id)}
											title={continueLabel}
											aria-label={continueLabel}
										>
											<svg
												class="size-4"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												stroke-width="2.3"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
												></path>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M15.91 11.672a.375.375 0 0 1 0 .656l-5.603 3.113a.375.375 0 0 1-.557-.328V8.887c0-.286.307-.466.557-.327l5.603 3.112Z"
												></path>
											</svg>
										</button>
									{/if}

									{#if regenerateMenu}
										<button
											type="button"
											class="regenerate-response-button rounded-lg p-1.5 transition hover:bg-white/[0.06] hover:text-white"
											onclick={() => onRegenerate(message.id)}
											title="重新生成"
											aria-label="重新生成回答"
											disabled={generating}
										>
											<svg
												class="size-4"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												stroke-width="2.3"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182"
												></path>
											</svg>
										</button>
									{/if}

									<button
										type="button"
										class="ml-0.5 inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs transition hover:bg-white/[0.06] hover:text-white"
										onclick={() => onSaveToNotebook(message.id)}
										title="加入笔记本"
										aria-label="将这轮问答加入笔记本"
									>
										<svg
											class="size-4"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="1.8"
										>
											<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
											<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"
											></path>
											<path d="M12 7v6"></path>
											<path d="M9 10h6"></path>
										</svg>
										加入笔记本
									</button>

									{#if showFloatingActionButtons}
										<!-- 「提问」「解释」挪进操作栏后，窄屏放不下时整组换到下一行，不再把「加入笔记本」挤成三行 -->
										<div class="ml-1 flex gap-1">
											{#each actions as action (action.id)}
												<button
													type="button"
													class="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs transition hover:bg-white/[0.06] hover:text-white"
													onpointerdown={(event) =>
														(pressedSelection = selectedText(event.currentTarget))}
													onmousedown={(event) => event.preventDefault()}
													onclick={(event) => runQuickAction(action, event)}
												>
													{#if action.id === 'ask'}
														<svg
															class="size-3.5 shrink-0"
															viewBox="0 0 24 24"
															fill="none"
															stroke="currentColor"
															stroke-width="3.2"
															stroke-linecap="round"
															stroke-linejoin="round"
															aria-hidden="true"
														>
															<path
																d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827"
															></path>
															<path d="M12 21h.01"></path>
														</svg>
													{:else if action.id === 'explain'}
														<svg
															class="size-3.5 shrink-0"
															viewBox="0 0 24 24"
															fill="none"
															stroke="currentColor"
															stroke-width="1.8"
															aria-hidden="true"
														>
															<path
																stroke-linecap="round"
																stroke-linejoin="round"
																d="M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18"
															></path>
														</svg>
													{/if}
													{action.label}
												</button>
											{/each}
										</div>
									{/if}
								</div>
							{/if}
						{/if}
					</div>
				</article>
			{/if}
		{/each}

		{#if generating && !messages.some((message) => message.streaming)}
			<article class="flex w-full">
				<div class="mt-1 mr-3 hidden shrink-0 sm:flex">
					<div
						class="flex size-8 items-center justify-center rounded-full bg-white text-[9px] font-black text-black"
					>
						OI
					</div>
				</div>

				<div class="relative w-0 flex-auto pl-1">
					<div class="mb-2 flex items-center gap-2">
						<span class="text-sm font-medium text-white">
							{modelName}
						</span>
					</div>

					<div class="flex items-center gap-1.5 py-2">
						<span class="thinking-dot size-1.5 rounded-full bg-gray-400"></span>
						<span class="thinking-dot size-1.5 rounded-full bg-gray-400 [animation-delay:150ms]"
						></span>
						<span class="thinking-dot size-1.5 rounded-full bg-gray-400 [animation-delay:300ms]"
						></span>
					</div>
				</div>
			</article>
		{/if}
	</div>
</div>

<style>
	@keyframes thinking {
		0%,
		80%,
		100% {
			opacity: 0.25;
			transform: translateY(0);
		}

		40% {
			opacity: 1;
			transform: translateY(-3px);
		}
	}

	.thinking-dot {
		animation: thinking 1.2s infinite ease-in-out;
	}
</style>
