<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { resolve } from '$app/paths';
	import { getAgentModels, streamAgentChat } from '$lib/apis/agent';
	import { learningContextParams, spaceStages, type SpaceStage } from '$lib/data/spaceLearning';
	import { saveSpaceRecord } from '$lib/data/spaceRecords';
	import MarkdownContent from '$lib/components/chat/MarkdownContent.svelte';
	import SatelliteFace from './SatelliteFace.svelte';
	import Cog6 from '$lib/components/icons/Cog6.svelte';

	let {
		stage,
		topic,
		topicId,
		lesson,
		lessonId,
		preferredModel,
		resourceTitle,
		autoOpen = false
	}: {
		stage?: SpaceStage;
		topic?: string;
		topicId?: string;
		lesson?: string;
		lessonId?: string;
		preferredModel?: string;
		resourceTitle?: string;
		autoOpen?: boolean;
	} = $props();

	type Message = {
		id: string;
		role: 'user' | 'assistant';
		content: string;
		ready?: boolean;
		saved?: boolean;
	};
	let messages = $state<Message[]>([]);
	let draft = $state('');
	let pending = $state(false);
	let failure = $state('');
	let notice = $state('');
	let opened = $state(false);
	let embedded = $state(false);
	let showSettings = $state(false);
	let showNotes = $state(false);
	let noteTitle = $state('');
	let noteText = $state('');
	let noteError = $state('');
	let input: HTMLTextAreaElement;
	let dialog: HTMLDialogElement;
	let thread: HTMLDivElement;
	let request: AbortController | undefined;
	const context = $derived(
		[stage && spaceStages[stage].label, topic, lesson, resourceTitle].filter(Boolean).join(' · ')
	);
	function createId() {
		if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
			return crypto.randomUUID();
		}
		return `space-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
	}

	const qaHref = $derived.by(() => {
		const base = resolve('/qa');
		if (!stage || !topicId) {
			return preferredModel ? `${base}?model=${encodeURIComponent(preferredModel)}` : base;
		}
		const params = learningContextParams(stage, topicId, lessonId);
		if (preferredModel) params.set('model', preferredModel);
		return `${base}?${params}`;
	});

	async function openChat() {
		dialog.showModal();
		opened = true;
		await tick();
		input.focus();
	}

	onMount(() => {
		embedded = autoOpen && window.parent !== window;
		if (!autoOpen) return;
		void openChat().then(() => notifyEmbeddedHost('xiaogui-ready'));
	});

	function notifyEmbeddedHost(type: 'xiaogui-ready' | 'xiaogui-close') {
		if (autoOpen && window.parent !== window) {
			const origin =
				new URLSearchParams(window.location.search).get('parent_origin') ??
				'https://science.nasa.gov';
			if (
				/^https:\/\/(?:science\.nasa\.gov|svs\.gsfc\.nasa\.gov|plus\.nasa\.gov|www\.nasa\.gov|www\.cmse\.gov\.cn|www\.usgs\.gov)$/.test(
					origin
				)
			) {
				window.parent.postMessage({ type }, origin);
			}
		}
	}

	async function send(event: SubmitEvent) {
		event.preventDefault();
		const question = draft.trim();
		if (!question || pending) return;
		const controller = new AbortController();
		request = controller;
		const ids = createId();
		const history = messages
			.filter((item) => item.role === 'user' || item.ready)
			.slice(-12)
			.map(({ role, content }) => ({ role, content }));
		const system = [
			'你是航天探索实验室的学习助手小轨。用中文回答航天科普问题。',
			stage ? spaceStages[stage].description : '用中小学生容易理解的语言回答。',
			context ? `当前学习内容：${context}。` : '',
			'对不确定的内容明确说明，不编造出处。'
		]
			.filter(Boolean)
			.join(' ');
		draft = '';
		failure = '';
		notice = '';
		pending = true;
		messages.push(
			{ id: `${ids}-q`, role: 'user', content: question },
			{ id: ids, role: 'assistant', content: '' }
		);
		const update = async (content: string, ready = false) => {
			if (controller.signal.aborted || request !== controller) return;
			messages = messages.map((item) => (item.id === ids ? { ...item, content, ready } : item));
			await tick();
			thread?.scrollTo({ top: thread.scrollHeight });
		};

		try {
			const { data: models } = await getAgentModels();
			if (controller.signal.aborted) return;
			const model = models.find(({ id }) => id === preferredModel) ?? models[0];
			if (!model) throw new Error('missing model');
			const result = await streamAgentChat(
				question,
				model.id,
				(content) => void update(content),
				controller.signal,
				{ mode: 'chat', history, system }
			);
			if (!result.content.trim()) throw new Error('empty response');
			await update(result.content, true);
		} catch {
			if (!controller.signal.aborted) {
				messages = messages.filter((item) => item.id !== ids && item.id !== `${ids}-q`);
				draft = question;
				failure = '暂时无法回答，请检查模型服务后重试。';
			}
		} finally {
			if (request === controller) {
				request = undefined;
				pending = false;
			}
		}
	}

	function save(message: Message, index: number) {
		try {
			const question = messages[index - 1]?.content ?? '';
			saveSpaceRecord({
				id: `mascot/${message.id}`,
				kind: '问答',
				context: context || '航天探索',
				title: question || '小轨的回答',
				content: `问：${question}\n\n答：${message.content}`
			});
			messages = messages.map((item) => (item.id === message.id ? { ...item, saved: true } : item));
			notice = '已加入我的笔记本。';
		} catch {
			notice = '无法保存笔记，请检查浏览器存储设置。';
		}
	}

	function saveNote(event: SubmitEvent) {
		event.preventDefault();
		const content = noteText.trim();
		if (!content) return;
		try {
			saveSpaceRecord({
				id: `mascot/note/${createId()}`,
				kind: '笔记',
				context: context || '航天探索',
				title: noteTitle.trim() || resourceTitle || lesson || '小轨学习笔记',
				content
			});
			noteTitle = '';
			noteText = '';
			noteError = '';
			showNotes = false;
			notice = '学习笔记已保存。';
		} catch {
			noteError = '无法保存笔记，请检查浏览器存储设置。';
		}
	}

	$effect(() => () => request?.abort());
</script>

<div class="space-theme assistant" class:standalone={autoOpen}>
	<button
		class="launcher"
		type="button"
		aria-haspopup="dialog"
		aria-expanded={opened}
		onclick={openChat}
	>
		<SatelliteFace />
		<span>问小轨</span>
	</button>

	<dialog
		bind:this={dialog}
		aria-labelledby="space-assistant-title"
		onclose={() => {
			opened = false;
			showSettings = false;
			showNotes = false;
			notifyEmbeddedHost('xiaogui-close');
		}}
	>
		<div class="chat">
			<header>
				{#if opened}<SatelliteFace compact thinking={pending} greeting />{/if}
				<div class="identity">
					<h2 id="space-assistant-title">小轨</h2>
					<p>{context || '航天学习助手'}</p>
				</div>
				<button
					class="settings-button close"
					type="button"
					aria-label="小轨设置与扩展安装"
					title="扩展安装"
					aria-expanded={showSettings}
					onclick={() => {
						showNotes = false;
						showSettings = !showSettings;
					}}><Cog6 className="size-5" /></button
				>
				<button
					class="close"
					type="button"
					aria-label="关闭小轨对话"
					onclick={() => {
						if (autoOpen && window.parent === window && window.opener === null) window.close();
						dialog.close();
					}}>×</button
				>
			</header>
			{#if showSettings}
				<section class="extension-help" aria-labelledby="xiaogui-extension-title">
					<h3 id="xiaogui-extension-title">安装浏览器扩展</h3>
					<ol>
						<li>
							在地址栏打开 Edge 的 <code>edge://extensions</code> 或 Chrome 的
							<code>chrome://extensions</code>。
						</li>
						<li>
							开启「开发者模式」，点「加载已解压的扩展」，选择项目根目录下的 <code
								>browser-extension</code
							> 文件夹。
						</li>
						<li>
							保持本地 TAgent
							和模型服务运行。从空天资料库打开支持的外部资料，点原站右下角的小轨开始问答。
						</li>
					</ol>
					<p>扩展更新后，在扩展管理页点「重新加载」，再从资料库重新打开原站。</p>
					<p>非本机 HTTPS 部署首次嵌入时会请求允许；选择取消会在新标签页打开。</p>
					<button class="text-button" type="button" onclick={() => (showSettings = false)}
						>返回对话</button
					>
				</section>
			{/if}
			{#if showNotes}
				<section class="extension-help" aria-labelledby="xiaogui-note-title">
					<h3 id="xiaogui-note-title">记学习笔记</h3>
					<form class="note-form" onsubmit={saveNote}>
						<label>标题（可选）<input bind:value={noteTitle} maxlength="100" /></label>
						<label
							>笔记正文<textarea
								bind:value={noteText}
								rows="6"
								maxlength="5000"
								required
								placeholder="写下你的观察、疑问或收获…"></textarea></label
						>
						{#if noteError}<p class="error" role="alert">{noteError}</p>{/if}
						<div class="footer-actions">
							<button class="text-button" type="button" onclick={() => (showNotes = false)}
								>返回对话</button
							>
							<button class="send" type="submit" disabled={!noteText.trim()}>保存笔记</button>
						</div>
					</form>
				</section>
			{/if}
			<div
				class="thread"
				class:settings-hidden={showSettings || showNotes}
				bind:this={thread}
				role="log"
				aria-label="对话记录"
				aria-busy={pending}
			>
				{#if !messages.length}<p class="welcome">你好，我是小轨。你想了解什么航天问题？</p>{/if}
				{#each messages as message, index (message.id)}
					<div class="message" class:user-message={message.role === 'user'}>
						{#if message.role === 'user'}<p>{message.content}</p>
						{:else if message.content}<MarkdownContent content={message.content} />
						{:else}<p class="hint">小轨正在思考…</p>{/if}
						{#if message.ready}<button
								class="text-button"
								type="button"
								disabled={message.saved}
								onclick={() => save(message, index)}
								>{message.saved ? '已加入笔记本' : '加入笔记本'}</button
							>{/if}
					</div>
				{/each}
			</div>
			<form class:settings-hidden={showSettings || showNotes} onsubmit={send}>
				{#if failure}<p class="error" role="alert">{failure}</p>{/if}
				{#if notice}<p class="hint" role="status">{notice}</p>{/if}
				<div class="compose">
					<textarea
						bind:this={input}
						bind:value={draft}
						rows="2"
						maxlength="1200"
						aria-label="输入航天问题"
						placeholder={lesson || '输入你的航天问题…'}></textarea>
					<button class="send" type="submit" disabled={pending || !draft.trim()}>发送</button>
				</div>
				<div class="footer-actions">
					<!-- eslint-disable svelte/no-navigation-without-resolve -- qaHref is resolved above and includes the learning context. -->
					<a
						class="text-button"
						href={qaHref}
						target={embedded ? '_blank' : undefined}
						rel={embedded ? 'noopener noreferrer' : undefined}
						onclick={() => dialog.close()}>打开完整答疑 ↗</a
					>
					<button class="text-button" type="button" onclick={() => (showNotes = true)}
						>记笔记</button
					>
				</div>
			</form>
		</div>
	</dialog>
</div>

<style>
	.assistant {
		font-family: var(--space-font);
		color: var(--m3-on-surface);
	}
	.launcher {
		position: fixed;
		z-index: 36;
		right: max(16px, env(safe-area-inset-right));
		bottom: max(16px, env(safe-area-inset-bottom));
		display: grid;
		justify-items: center;
		gap: 5px;
		padding: 6px 5px 8px;
		border: 0;
		border-radius: 17px;
		background: transparent;
		color: var(--m3-primary);
		font-size: 12px;
		font-weight: 600;
	}
	.launcher > span:last-child {
		text-shadow: 0 1px 5px #090612;
	}
	@media (hover: hover) and (pointer: fine) {
		.launcher:hover {
			color: var(--m3-on-surface);
		}
	}
	dialog {
		position: fixed;
		inset: auto max(14px, env(safe-area-inset-right)) max(14px, env(safe-area-inset-bottom)) auto;
		width: min(402px, calc(100% - 28px));
		max-height: min(620px, calc(100dvh - 28px));
		margin: 0;
		padding: 0;
		overflow: hidden;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 16px;
		background: var(--m3-background);
		color: var(--m3-on-surface);
		color-scheme: inherit;
	}
	dialog::backdrop {
		background: #08061255;
	}
	.standalone dialog {
		inset: 0;
		width: 100%;
		max-width: none;
		max-height: none;
		border: 0;
		border-radius: 0;
	}
	.standalone .chat {
		height: 100dvh;
	}
	.chat {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		grid-template-rows: auto minmax(0, 1fr) auto;
		height: min(620px, calc(100dvh - 28px));
	}
	header {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 12px;
		border-bottom: 1px solid var(--m3-outline-variant);
		background: var(--m3-surface-low);
	}
	.identity {
		min-width: 0;
		flex: 1;
	}
	h2 {
		font-size: 17px;
		font-weight: 600;
	}
	header p,
	.hint {
		color: var(--m3-on-surface-variant);
		font-size: 12px;
	}
	header p {
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}
	.close {
		width: 36px;
		height: 36px;
		flex: none;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 10px;
		font-size: 22px;
	}
	.settings-button {
		display: grid;
		place-items: center;
	}
	.settings-button:hover,
	.settings-button[aria-expanded='true'] {
		background: var(--m3-surface-high);
		color: var(--m3-primary);
	}
	.thread.settings-hidden,
	form.settings-hidden {
		display: none;
	}
	.extension-help {
		grid-row: 2 / span 2;
		overflow: auto;
		padding: 16px;
		font-size: 14px;
		line-height: 1.65;
	}
	.extension-help h3 {
		font-weight: 650;
	}
	.extension-help ol {
		margin: 12px 0;
		padding-inline-start: 22px;
		list-style: decimal;
	}
	.extension-help li + li {
		margin-top: 8px;
	}
	.extension-help code {
		color: var(--m3-primary);
		overflow-wrap: anywhere;
	}
	.thread {
		display: flex;
		flex-direction: column;
		align-items: start;
		gap: 10px;
		overflow: auto;
		padding: 14px;
	}
	.welcome,
	.message {
		max-width: 100%;
		padding: 10px 12px;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 12px;
		background: var(--m3-surface-low);
		overflow-wrap: anywhere;
	}
	.user-message {
		align-self: end;
		background: var(--space-selected);
		white-space: pre-wrap;
	}
	form {
		display: grid;
		gap: 6px;
		padding: 10px 12px;
		border-top: 1px solid var(--m3-outline-variant);
		background: var(--m3-surface-low);
	}
	.compose {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: end;
		gap: 8px;
	}
	textarea,
	.note-form input {
		width: 100%;
		min-width: 0;
		padding: 8px;
		resize: none;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 10px;
		background: var(--m3-background);
		font-size: 16px;
	}
	.note-form {
		gap: 12px;
		margin-top: 12px;
		padding: 0;
		border: 0;
		background: transparent;
	}
	.note-form label {
		display: grid;
		gap: 4px;
	}
	.footer-actions {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 4px 12px;
	}
	.send {
		min-height: 42px;
		padding-inline: 12px;
		white-space: nowrap;
		border-radius: 9px;
		background: var(--m3-primary);
		color: var(--m3-on-primary);
		font-weight: 600;
	}
	.send:disabled {
		opacity: 0.42;
		cursor: default;
	}
	.text-button {
		justify-self: start;
		padding: 4px 0;
		color: var(--m3-primary);
		font-size: 12px;
	}
	.text-button:disabled {
		color: var(--m3-on-surface-variant);
		cursor: default;
	}
	.error {
		color: var(--space-error);
		font-size: 13px;
	}
	:is(button, a, textarea):focus-visible {
		outline: 2px solid var(--m3-primary);
		outline-offset: 2px;
	}
</style>
