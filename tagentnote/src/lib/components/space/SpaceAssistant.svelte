<script lang="ts">
	import { tick } from 'svelte';
	import { resolve } from '$app/paths';
	import { getAgentModels, streamAgentChat } from '$lib/apis/agent';
	import { learningContextParams, spaceStages, type SpaceStage } from '$lib/data/spaceLearning';
	import { saveSpaceRecord } from '$lib/data/spaceRecords';
	import MarkdownContent from '$lib/components/chat/MarkdownContent.svelte';
	import SatelliteFace from './SatelliteFace.svelte';

	let {
		stage,
		topic,
		topicId,
		lesson,
		lessonId,
		preferredModel
	}: {
		stage?: SpaceStage;
		topic?: string;
		topicId?: string;
		lesson?: string;
		lessonId?: string;
		preferredModel?: string;
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
	let input: HTMLTextAreaElement;
	let dialog: HTMLDialogElement;
	let thread: HTMLDivElement;
	let request: AbortController | undefined;
	const context = $derived(
		[stage && spaceStages[stage].label, topic, lesson].filter(Boolean).join(' · ')
	);
	const qaHref = $derived(
		stage && topicId
			? `${resolve('/qa')}?${learningContextParams(stage, topicId, lessonId)}`
			: resolve('/qa')
	);

	async function openChat() {
		dialog.showModal();
		opened = true;
		await tick();
		input.focus();
	}

	async function send(event: SubmitEvent) {
		event.preventDefault();
		const question = draft.trim();
		if (!question || pending) return;
		const controller = new AbortController();
		request = controller;
		const ids = crypto.randomUUID();
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

	$effect(() => () => request?.abort());
</script>

<div class="space-theme assistant">
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
		onclose={() => (opened = false)}
	>
		<div class="chat">
			<header>
				{#if opened}<SatelliteFace compact thinking={pending} greeting />{/if}
				<div class="identity">
					<h2 id="space-assistant-title">小轨</h2>
					<p>{context || '航天学习助手'}</p>
				</div>
				<button class="close" type="button" aria-label="关闭小轨对话" onclick={() => dialog.close()}
					>×</button
				>
			</header>
			<div class="thread" bind:this={thread} role="log" aria-label="对话记录" aria-busy={pending}>
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
			<form onsubmit={send}>
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
				<a class="text-button" href={qaHref} onclick={() => dialog.close()}>打开完整答疑 ↗</a>
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
		color-scheme: dark;
	}
	dialog::backdrop {
		background: #08061255;
	}
	.chat {
		display: grid;
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
		background: #342844;
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
		display: flex;
		align-items: end;
		gap: 8px;
	}
	textarea {
		width: 100%;
		min-width: 0;
		padding: 8px;
		resize: none;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 10px;
		background: var(--m3-background);
		font-size: 16px;
	}
	.send {
		min-height: 42px;
		flex: none;
		padding-inline: 12px;
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
		color: #ffb4ab;
		font-size: 13px;
	}
	:is(button, a, textarea):focus-visible {
		outline: 2px solid var(--m3-primary);
		outline-offset: 2px;
	}
</style>
