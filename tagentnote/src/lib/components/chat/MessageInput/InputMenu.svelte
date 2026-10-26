<script lang="ts">
	import { isTextFile, MAX_ATTACHMENT_BYTES, unsupportedReason } from '$lib/data/attachments';

	export type InputAttachment = {
		id: string;
		type: 'file' | 'webpage' | 'knowledge' | 'note' | 'chat';
		name: string;
		url?: string;
		/** 笔记、知识库、对话在原处的编号（发送时按它去取内容） */
		refId?: string;
		/** 读出来的文字（文本文件、粘贴的长文） */
		content?: string;
		/** 读不了的原因：发送时不带它，并告诉学生 */
		unsupported?: string;
	};

	type ListItem = { id: string; name: string; description?: string };

	type Props = {
		attachments?: InputAttachment[];
		knowledgeOptions?: ListItem[];
		noteOptions?: ListItem[];
		chatOptions?: ListItem[];
		onAttachmentsChange?: (items: InputAttachment[]) => void;
		onToast?: (message: string) => void;
		onClose?: () => void;
		children?: import('svelte').Snippet;
	};

	let {
		attachments = $bindable([] as InputAttachment[]),
		knowledgeOptions = [],
		noteOptions = [],
		chatOptions = [],
		onAttachmentsChange = () => {},
		onToast = () => {},
		onClose = () => {},
		children
	}: Props = $props();

	type Tab = 'main' | 'notes' | 'knowledge' | 'chats';
	let open = $state(false);
	let tab = $state<Tab>('main');
	let webpageOpen = $state(false);
	let webpageUrls = $state('');
	let rootEl = $state<HTMLDivElement | null>(null);
	let menuEl = $state<HTMLDivElement | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);
	let menuStyle = $state('');
	let selectedIdx = $state(0);

	const updateMenuPosition = () => {
		if (!rootEl) return;
		const rect = rootEl.getBoundingClientRect();
		const width = 280;
		let left = rect.left;
		left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
		menuStyle = `position:fixed;left:${left}px;bottom:${window.innerHeight - rect.top + 8}px;width:${width}px;z-index:120;`;
	};

	const addAttachment = (item: InputAttachment) => {
		if (attachments.some((a) => a.id === item.id)) return;
		attachments = [...attachments, item];
		onAttachmentsChange(attachments);
	};

	/** 文本文件把内容读出来带上；读不了的照样列出来，但记下原因（发送时不带、并提示） */
	const addFiles = async (files: File[], idPrefix: string) => {
		for (const file of files) {
			const readable = isTextFile(file) && file.size <= MAX_ATTACHMENT_BYTES;
			let content: string | undefined;
			if (readable) {
				content = await file.text().catch(() => undefined);
			}
			addAttachment({
				id: `${idPrefix}-${file.name}-${file.size}-${Date.now()}`,
				type: 'file',
				name: file.name,
				content,
				unsupported: content === undefined ? unsupportedReason(file) : undefined
			});
		}
	};

	const close = () => {
		open = false;
		tab = 'main';
		selectedIdx = 0;
		onClose();
	};

	const goMain = () => {
		tab = 'main';
		selectedIdx = 0;
	};

	const portal = (node: HTMLElement) => {
		document.body.appendChild(node);
		return {
			destroy() {
				node.remove();
			}
		};
	};

	const detectMobile = () => {
		const ua = navigator.userAgent || '';
		return /android|iphone|ipad|ipod|windows phone/i.test(ua);
	};

	const captureScreen = async () => {
		try {
			if (detectMobile()) {
				document.getElementById('camera-input')?.click();
				return;
			}
			const mediaStream = await navigator.mediaDevices.getDisplayMedia({
				video: true,
				audio: false
			});
			const video = document.createElement('video');
			video.srcObject = mediaStream;
			await video.play();
			const canvas = document.createElement('canvas');
			canvas.width = video.videoWidth;
			canvas.height = video.videoHeight;
			const ctx = canvas.getContext('2d');
			ctx?.drawImage(video, 0, 0);
			mediaStream.getTracks().forEach((t) => t.stop());
			video.pause();
			video.srcObject = null;
			const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
			const name = `截图-${new Date().toLocaleTimeString()}.png`;
			addAttachment({
				id: `capture-${Date.now()}`,
				type: 'file',
				name,
				unsupported: blob ? '图片目前还不能识别，没有发送' : '截图失败'
			});
			onToast('已添加截图');
			close();
		} catch {
			onToast('截图已取消或失败');
		}
	};

	const submitWebpages = () => {
		const urls = [
			...new Set(
				webpageUrls
					.split('\n')
					.map((u) => u.trim())
					.filter((u) => /^https?:\/\//i.test(u))
			)
		];
		if (urls.length === 0) {
			onToast('请输入有效的网址');
			return;
		}
		for (const url of urls) {
			addAttachment({
				id: `web-${url}-${Date.now()}`,
				type: 'webpage',
				name: url,
				url,
				// 浏览器里取不到别的网站的内容（跨域），后端也还没有抓网页
				unsupported: '网页内容目前还不能抓取，可以复制正文粘贴进来'
			});
		}
		onToast(urls.length === 1 ? '已引用网页' : `已引用 ${urls.length} 个网页`);
		webpageOpen = false;
		webpageUrls = '';
	};

	$effect(() => {
		if (!open) return;
		const onPointerDown = (event: PointerEvent) => {
			const target = event.target as Node;
			if (rootEl?.contains(target) || menuEl?.contains(target)) return;
			close();
		};
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Escape') close();
		};
		const timer = window.setTimeout(() => {
			window.addEventListener('pointerdown', onPointerDown, true);
			window.addEventListener('keydown', onKeyDown);
		}, 0);
		return () => {
			window.clearTimeout(timer);
			window.removeEventListener('pointerdown', onPointerDown, true);
			window.removeEventListener('keydown', onKeyDown);
		};
	});
</script>

<div class="relative" bind:this={rootEl}>
	<button
		type="button"
		id="input-menu-button"
		class="flex size-8 items-center justify-center rounded-full text-white transition outline-none hover:bg-gray-800"
		title="更多"
		aria-label="更多"
		aria-expanded={open}
		onclick={(e) => {
			e.preventDefault();
			e.stopPropagation();
			open = !open;
			if (open) updateMenuPosition();
			else {
				tab = 'main';
				selectedIdx = 0;
			}
		}}
	>
		{#if children}
			{@render children()}
		{:else}
			<span class="sr-only">更多</span>
		{/if}
	</button>
</div>

<input
	bind:this={fileInput}
	type="file"
	class="hidden"
	multiple
	onchange={async () => {
		const files = Array.from(fileInput?.files ?? []);
		if (fileInput) fileInput.value = '';
		if (!files.length) return;
		close();
		await addFiles(files, 'file');
		const unreadable = files.filter(
			(file) => !isTextFile(file) || file.size > MAX_ATTACHMENT_BYTES
		);
		onToast(
			unreadable.length
				? `已添加 ${files.length} 个文件，其中 ${unreadable.length} 个目前读不了（PDF、Word、图片等），发送时不会带上内容`
				: `已添加 ${files.length} 个文件`
		);
	}}
/>

<input
	id="camera-input"
	type="file"
	accept="image/*"
	capture="environment"
	class="hidden"
	onchange={async (e) => {
		const input = e.currentTarget as HTMLInputElement;
		const files = Array.from(input.files ?? []);
		input.value = '';
		if (!files.length) return;
		close();
		await addFiles(files, 'camera');
		onToast('已添加照片（图片目前还不能识别，发送时不会带上）');
	}}
/>

{#if open}
	<div
		bind:this={menuEl}
		use:portal
		class="bg-gray-850 fixed z-[120] max-h-72 overflow-x-hidden overflow-y-auto rounded-2xl border border-gray-800 px-1 py-1 text-sm text-white shadow-lg transition"
		style={menuStyle}
		tabindex="-1"
		role="menu"
		aria-label="更多"
	>
		{#if tab === 'main'}
			<div>
				<button
					type="button"
					class="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-1.5 text-left select-none hover:bg-gray-800/50"
					onclick={() => fileInput?.click()}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						aria-hidden="true"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M21.4383 11.6622L12.2483 20.8522C11.1225 21.9781 9.59552 22.6106 8.00334 22.6106C6.41115 22.6106 4.88418 21.9781 3.75834 20.8522C2.63249 19.7264 2 18.1994 2 16.6072C2 15.015 2.63249 13.4881 3.75834 12.3622L12.9483 3.17222C13.6989 2.42166 14.7169 2 15.7783 2C16.8398 2 17.8578 2.42166 18.6083 3.17222C19.3589 3.92279 19.7806 4.94077 19.7806 6.00222C19.7806 7.06368 19.3589 8.08166 18.6083 8.83222L9.40834 18.0222C9.03306 18.3975 8.52406 18.6083 7.99334 18.6083C7.46261 18.6083 6.95362 18.3975 6.57834 18.0222C6.20306 17.6469 5.99222 17.138 5.99222 16.6072C5.99222 16.0765 6.20306 15.5675 6.57834 15.1922L15.0683 6.71222"
						></path>
					</svg>
					<div class="line-clamp-1">上传文件</div>
				</button>

				<button
					type="button"
					class="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-1.5 text-left select-none hover:bg-gray-800/50"
					onclick={() => void captureScreen()}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						aria-hidden="true"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M2 19V9C2 7.89543 2.89543 7 4 7H4.5C5.12951 7 5.72229 6.70361 6.1 6.2L8.32 3.24C8.43331 3.08892 8.61115 3 8.8 3H15.2C15.3889 3 15.5667 3.08892 15.68 3.24L17.9 6.2C18.2777 6.70361 18.8705 7 19.5 7H20C21.1046 7 22 7.89543 22 9V19C22 20.1046 21.1046 21 20 21H4C2.89543 21 2 20.1046 2 19Z"
						></path>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M12 17C14.2091 17 16 15.2091 16 13C16 10.7909 14.2091 9 12 9C9.79086 9 8 10.7909 8 13C8 15.2091 9.79086 17 12 17Z"
						></path>
					</svg>
					<div class="line-clamp-1">截图</div>
				</button>

				<button
					type="button"
					class="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-1.5 text-left select-none hover:bg-gray-800"
					onclick={() => {
						webpageUrls = '';
						webpageOpen = true;
						close();
					}}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						aria-hidden="true"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418"
						></path>
					</svg>
					<div class="line-clamp-1">引用网页</div>
				</button>

				<button
					type="button"
					class="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-1.5 text-left select-none hover:bg-gray-800/50"
					onclick={() => {
						tab = 'notes';
						selectedIdx = 0;
					}}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						aria-hidden="true"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M20 12V5.74853C20 5.5894 19.9368 5.43679 19.8243 5.32426L16.6757 2.17574C16.5632 2.06321 16.4106 2 16.2515 2H4.6C4.26863 2 4 2.26863 4 2.6V21.4C4 21.7314 4.26863 22 4.6 22H11"
						></path>
						<path stroke-linecap="round" stroke-linejoin="round" d="M8 10H16M8 6H12M8 14H11"></path>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M17.9541 16.9394L18.9541 15.9394C19.392 15.5015 20.102 15.5015 20.5399 15.9394V15.9394C20.9778 16.3773 20.9778 17.0873 20.5399 17.5252L19.5399 18.5252M17.9541 16.9394L14.963 19.9305C14.8131 20.0804 14.7147 20.2741 14.6821 20.4835L14.4394 22.0399L15.9957 21.7973C16.2052 21.7646 16.3988 21.6662 16.5487 21.5163L19.5399 18.5252M17.9541 16.9394L19.5399 18.5252"
						></path>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M16 2V5.4C16 5.73137 16.2686 6 16.6 6H20"
						></path>
					</svg>
					<div class="flex w-full items-center justify-between">
						<div class="line-clamp-1">引用笔记</div>
						<div class="text-gray-500">
							<svg
								class="size-4"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.8"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5"
								></path>
							</svg>
						</div>
					</div>
				</button>

				<button
					type="button"
					class="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-1.5 text-left hover:bg-gray-800/50"
					onclick={() => {
						tab = 'knowledge';
						selectedIdx = 0;
					}}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						aria-hidden="true"
					>
						<path d="M5 12V18C5 18 5 21 12 21C19 21 19 18 19 18V12"></path>
						<path d="M5 6V12C5 12 5 15 12 15C19 15 19 12 19 12V6"></path>
						<path d="M12 3C19 3 19 6 19 6C19 6 19 9 12 9C5 9 5 6 5 6C5 6 5 3 12 3Z"></path>
					</svg>
					<div class="flex w-full items-center justify-between">
						<div class="line-clamp-1">引用知识库</div>
						<div class="text-gray-500">
							<svg
								class="size-4"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.8"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5"
								></path>
							</svg>
						</div>
					</div>
				</button>

				<button
					type="button"
					class="flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-1.5 text-left hover:bg-gray-800/50"
					onclick={() => {
						tab = 'chats';
						selectedIdx = 0;
					}}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						aria-hidden="true"
					>
						<path d="M12 6L12 12L18 12" stroke-linecap="round" stroke-linejoin="round"></path>
						<path
							d="M21.8883 10.5C21.1645 5.68874 17.013 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22C16.1006 22 19.6248 19.5318 21.1679 16"
							stroke-linecap="round"
							stroke-linejoin="round"
						></path>
						<path
							d="M17 16H21.4C21.7314 16 22 16.2686 22 16.6V21"
							stroke-linecap="round"
							stroke-linejoin="round"
						></path>
					</svg>
					<div class="flex w-full items-center justify-between">
						<div class="line-clamp-1">引用其他对话</div>
						<div class="text-gray-500">
							<svg
								class="size-4"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.8"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5"
								></path>
							</svg>
						</div>
					</div>
				</button>
			</div>
		{:else if tab === 'notes'}
			<div>
				<button
					type="button"
					class="flex w-full cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-1.5 text-left select-none hover:bg-gray-800/50"
					onclick={goMain}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.8"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5"
						></path>
					</svg>
					<div class="flex w-full items-center justify-between">
						<div>笔记</div>
					</div>
				</button>
				{#if noteOptions.length === 0}
					<div class="py-3 text-center text-xs text-gray-500">未找到笔记</div>
				{:else}
					<div class="flex flex-col gap-0.5">
						{#each noteOptions as item, idx (item.id)}
							<button
								type="button"
								class={`flex w-full items-center justify-between rounded-xl px-2.5 py-1 text-left text-sm ${
									idx === selectedIdx ? 'bg-gray-800 text-gray-100' : ''
								}`}
								onmousemove={() => {
									selectedIdx = idx;
								}}
								onclick={() => {
									addAttachment({
										id: `note-${item.id}`,
										type: 'note',
										name: item.name,
										refId: item.id
									});
									onToast(`已引用笔记「${item.name}」`);
									close();
								}}
							>
								<div class="flex items-center gap-1.5 text-gray-100">
									<svg
										class="size-4 shrink-0"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.5"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M20 12V5.74853C20 5.5894 19.9368 5.43679 19.8243 5.32426L16.6757 2.17574C16.5632 2.06321 16.4106 2 16.2515 2H4.6C4.26863 2 4 2.26863 4 2.6V21.4C4 21.7314 4.26863 22 4.6 22H11"
										></path>
										<path stroke-linecap="round" stroke-linejoin="round" d="M8 10H16M8 6H12M8 14H11"
										></path>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M17.9541 16.9394L18.9541 15.9394C19.392 15.5015 20.102 15.5015 20.5399 15.9394V15.9394C20.9778 16.3773 20.9778 17.0873 20.5399 17.5252L19.5399 18.5252M17.9541 16.9394L14.963 19.9305C14.8131 20.0804 14.7147 20.2741 14.6821 20.4835L14.4394 22.0399L15.9957 21.7973C16.2052 21.7646 16.3988 21.6662 16.5487 21.5163L19.5399 18.5252M17.9541 16.9394L19.5399 18.5252"
										></path>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M16 2V5.4C16 5.73137 16.2686 6 16.6 6H20"
										></path>
									</svg>
									<div class="line-clamp-1 flex-1">{item.name}</div>
								</div>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		{:else if tab === 'knowledge'}
			<div>
				<button
					type="button"
					class="flex w-full cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-1.5 text-left select-none hover:bg-gray-800/50"
					onclick={goMain}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.8"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5"
						></path>
					</svg>
					<div class="flex w-full items-center justify-between">
						<div>知识库</div>
					</div>
				</button>
				{#if knowledgeOptions.length === 0}
					<div class="py-3 text-center text-xs text-gray-500">未找到知识库</div>
				{:else}
					<div class="flex flex-col gap-0.5">
						{#each knowledgeOptions as item, idx (item.id)}
							<button
								type="button"
								class={`flex w-full items-center justify-between rounded-xl px-2.5 py-1 text-left text-sm ${
									idx === selectedIdx ? 'bg-gray-800 text-gray-100' : ''
								}`}
								onmousemove={() => {
									selectedIdx = idx;
								}}
								onclick={() => {
									addAttachment({
										id: `knowledge-${item.id}`,
										type: 'knowledge',
										name: item.name,
										refId: item.id
									});
									onToast(`已引用知识库「${item.name}」`);
									close();
								}}
							>
								<div class="flex items-center gap-1.5 text-gray-100">
									<svg
										class="size-4 shrink-0"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.5"
									>
										<path d="M5 12V18C5 18 5 21 12 21C19 21 19 18 19 18V12"></path>
										<path d="M5 6V12C5 12 5 15 12 15C19 15 19 12 19 12V6"></path>
										<path d="M12 3C19 3 19 6 19 6C19 6 19 9 12 9C5 9 5 6 5 6C5 6 5 3 12 3Z"></path>
									</svg>
									<div class="line-clamp-1 flex-1">{item.name}</div>
								</div>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		{:else}
			<div>
				<button
					type="button"
					class="flex w-full cursor-pointer items-center justify-between gap-2 rounded-xl px-3 py-1.5 text-left select-none hover:bg-gray-800/50"
					onclick={goMain}
				>
					<svg
						class="size-4 shrink-0"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.8"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5"
						></path>
					</svg>
					<div class="flex w-full items-center justify-between">
						<div>对话</div>
					</div>
				</button>
				{#if chatOptions.length === 0}
					<div class="py-3 text-center text-xs text-gray-500">未找到对话</div>
				{:else}
					<div class="flex flex-col gap-0.5">
						{#each chatOptions as item, idx (item.id)}
							<button
								type="button"
								class={`flex w-full items-center justify-between rounded-xl px-2.5 py-1 text-left text-sm ${
									idx === selectedIdx ? 'bg-gray-800 text-gray-100' : ''
								}`}
								onmousemove={() => {
									selectedIdx = idx;
								}}
								onclick={() => {
									addAttachment({
										id: `chat-${item.id}`,
										type: 'chat',
										name: item.name,
										refId: item.id
									});
									onToast(`已引用对话「${item.name}」`);
									close();
								}}
							>
								<div class="line-clamp-1 flex-1 text-gray-100">{item.name}</div>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		{/if}
	</div>
{/if}

{#if webpageOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-[130] flex items-center justify-center bg-black/60 px-4"
		onclick={() => {
			webpageOpen = false;
		}}
	>
		<div
			class="bg-gray-850 flex h-full max-h-[22rem] w-full max-w-sm flex-col rounded-2xl border border-gray-800 text-white shadow-2xl"
			onclick={(e) => e.stopPropagation()}
			tabindex="-1"
			role="dialog"
			aria-modal="true"
			aria-label="引用网页"
		>
			<div class="flex items-center justify-between px-5 pt-4 pb-1.5 text-gray-100">
				<h1 class="self-center text-lg font-medium">引用网页</h1>
				<button
					type="button"
					class="self-center"
					aria-label="关闭"
					onclick={() => {
						webpageOpen = false;
					}}
				>
					<svg
						class="size-5"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.8"
					>
						<path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"></path>
					</svg>
				</button>
			</div>

			<form
				class="px-5 pb-4"
				onsubmit={(e) => {
					e.preventDefault();
					submitWebpages();
				}}
			>
				<div class="mb-0.5 flex justify-between">
					<label for="webpage-url" class="text-xs text-gray-500">网页网址</label>
				</div>
				<textarea
					id="webpage-url"
					class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-700"
					bind:value={webpageUrls}
					rows="3"
					placeholder="https://example.com"
					autocomplete="off"
					required></textarea>
				<div class="flex justify-end gap-2 bg-gray-900/50 pt-3">
					<button
						type="submit"
						class="rounded-full bg-white px-3.5 py-1.5 text-sm font-medium text-black transition hover:bg-gray-100"
					>
						添加
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
