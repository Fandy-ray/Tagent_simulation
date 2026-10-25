<script lang="ts">
	import UserStatusModal from './UserStatusModal.svelte';
	import UserCircle from '$lib/components/icons/UserCircle.svelte';
	import { getI18nContext } from '$lib/i18n';

	const i18n = getI18nContext();

	type Props = {
		/** navbar=右上角帮助菜单；sidebar=左下角资料+状态菜单 */
		variant?: 'navbar' | 'sidebar';
		className?: string;
		align?: 'start' | 'end';
		placement?: 'top' | 'bottom';
		userRole?: 'admin' | 'user';
		/** 兼容旧用法；variant 优先 */
		profile?: boolean;
		help?: boolean;
		showPlayground?: boolean;
		showAdmin?: boolean;
		userName?: string;
		avatarText?: string;
		activeUsers?: number;
		isActive?: boolean;
		statusEmoji?: string;
		statusMessage?: string;
		triggerClassName?: string;
		onSettings?: () => void;
		onArchivedChats?: () => void;
		onPlayground?: () => void;
		onAdmin?: () => void;
		onShortcuts?: () => void;
		onSignOut?: () => void;
		onStatusSave?: (value: { emoji: string; message: string }) => void;
		onToast?: (message: string) => void;
		children?: import('svelte').Snippet;
	};

	let {
		variant = undefined,
		className = 'w-[240px]',
		align = 'end',
		placement = 'bottom',
		userRole = 'admin',
		profile = true,
		help = false,
		showPlayground = true,
		showAdmin = true,
		userName = 'Tagent',
		avatarText = 'T',
		activeUsers = 1,
		isActive = true,
		statusEmoji = '',
		statusMessage = '',
		triggerClassName = 'flex select-none rounded-xl p-1.5 transition hover:bg-gray-850',
		onSettings = () => {},
		onArchivedChats = () => {},
		onPlayground = () => {},
		onAdmin = () => {},
		onShortcuts = () => {},
		onSignOut = () => {},
		onStatusSave = () => {},
		onToast = () => {},
		children
	}: Props = $props();

	const showProfile = $derived(
		variant === 'navbar' ? false : variant === 'sidebar' ? true : profile
	);
	const showHelp = $derived(variant === 'navbar' ? true : variant === 'sidebar' ? false : help);

	let open = $state(false);
	let statusModalOpen = $state(false);
	let rootEl = $state<HTMLDivElement | null>(null);
	let menuEl = $state<HTMLDivElement | null>(null);
	let menuStyle = $state('');

	const close = () => {
		open = false;
	};

	const run = (action: () => void) => {
		action();
		close();
	};

	const portal = (node: HTMLElement) => {
		document.body.appendChild(node);
		return {
			destroy() {
				node.remove();
			}
		};
	};

	const updateMenuPosition = () => {
		if (!rootEl) return;
		const rect = rootEl.getBoundingClientRect();
		const gap = 8;
		const widthMatch = className.match(/w-\[(\d+)px\]/);
		const width = widthMatch ? Number(widthMatch[1]) : 240;

		let left = align === 'end' ? rect.right - width : rect.left;
		left = Math.max(8, Math.min(left, window.innerWidth - width - 8));

		if (placement === 'top') {
			menuStyle = `position:fixed;left:${left}px;bottom:${window.innerHeight - rect.top + gap}px;width:${width}px;z-index:100;`;
		} else {
			menuStyle = `position:fixed;left:${left}px;top:${rect.bottom + gap}px;width:${width}px;z-index:100;`;
		}
	};

	const toggle = (event: MouseEvent) => {
		event.preventDefault();
		event.stopPropagation();
		open = !open;
		if (open) updateMenuPosition();
	};

	$effect(() => {
		if (!open) return;
		updateMenuPosition();

		const onPointerDown = (event: PointerEvent) => {
			const target = event.target as Node;
			if (rootEl?.contains(target) || menuEl?.contains(target)) return;
			close();
		};
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Escape') close();
		};
		const onReposition = () => updateMenuPosition();

		const timer = window.setTimeout(() => {
			window.addEventListener('pointerdown', onPointerDown, true);
			window.addEventListener('keydown', onKeyDown);
			window.addEventListener('resize', onReposition);
			window.addEventListener('scroll', onReposition, true);
		}, 0);

		return () => {
			window.clearTimeout(timer);
			window.removeEventListener('pointerdown', onPointerDown, true);
			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('resize', onReposition);
			window.removeEventListener('scroll', onReposition, true);
		};
	});
</script>

<div class="relative" bind:this={rootEl}>
	<button
		type="button"
		class={triggerClassName}
		aria-expanded={open}
		aria-haspopup="menu"
		aria-label={showProfile ? '打开用户资料菜单' : '打开用户菜单'}
		onclick={toggle}
	>
		{#if children}
			{@render children()}
		{:else}
			<div class="relative">
				<div
					class="flex size-7 items-center justify-center rounded-full bg-amber-500 text-[10px] font-semibold text-white"
				>
					{avatarText}
				</div>
				{#if showProfile}
					<span
						class="absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full border-2 border-gray-900 bg-green-500"
					></span>
				{/if}
			</div>
		{/if}
	</button>
</div>

{#if open}
	<div
		bind:this={menuEl}
		use:portal
		class={`bg-gray-850 z-50 rounded-2xl border border-gray-800 px-1 py-1 text-sm text-white shadow-lg ${className}`}
		style={menuStyle}
		tabindex="-1"
		role="menu"
		aria-label={`${userName} 的菜单`}
	>
		{#if showProfile}
			<div class="flex w-full items-center gap-3.5 p-2.5">
				<div class="flex shrink-0 items-center">
					<div
						class="flex size-10 items-center justify-center rounded-full bg-amber-500 text-sm font-semibold text-white"
					>
						{avatarText}
					</div>
				</div>
				<div class="flex w-full flex-1 flex-col">
					<div class="line-clamp-1 pr-2 font-medium">{userName}</div>
					<div class="flex items-center gap-2">
						<span class="relative flex size-2">
							<span
								class={`relative inline-flex size-2 rounded-full ${
									isActive ? 'bg-green-500' : 'bg-gray-500'
								}`}
							></span>
						</span>
						<span class="text-xs">{isActive ? '在线' : '离开'}</span>
					</div>
				</div>
			</div>

			{#if false}
				{#if statusEmoji || statusMessage}
					<div class="mx-1">
						<div
							class="mb-1 flex w-full items-center gap-2 rounded-xl bg-gray-900/50 px-2.5 py-1.5 text-xs text-white transition hover:bg-gray-800"
						>
							<button
								type="button"
								class="flex min-w-0 flex-1 items-center gap-2 text-left"
								onclick={() => {
									close();
									statusModalOpen = true;
								}}
							>
								{#if statusEmoji}
									<span class="shrink-0 self-center text-sm">{statusEmoji}</span>
								{/if}
								<span class="line-clamp-2 flex-1 self-center">
									{statusMessage || $i18n.t('Update your status')}
								</span>
							</button>
							<button
								type="button"
								class="self-start opacity-50 hover:opacity-100"
								aria-label={$i18n.t('Clear Status')}
								onclick={(e) => {
									e.preventDefault();
									e.stopPropagation();
									onStatusSave({ emoji: '', message: '' });
									onToast($i18n.t('Status cleared'));
								}}
							>
								<svg
									class="size-4"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
								>
									<path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"></path>
								</svg>
							</button>
						</div>
					</div>
				{:else}
					<div class="mx-1">
						<button
							type="button"
							class="mb-1 flex w-full items-center justify-center gap-1 rounded-xl bg-gray-900/50 px-3 py-1.5 text-xs text-white transition hover:bg-gray-800"
							onclick={() => {
								close();
								statusModalOpen = true;
							}}
						>
							<svg
								class="size-4"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.5"
								aria-hidden="true"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M15.182 15.182a4.5 4.5 0 0 1-6.364 0M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9.75 9.75c.008-.034.017-.067.026-.1a.15.15 0 0 1 .222-.062.15.15 0 0 1 .075.112c.01.033.018.066.026.1M14.25 9.75c.008-.034.017-.067.026-.1a.15.15 0 0 1 .222-.062.15.15 0 0 1 .075.112c.01.033.018.066.026.1"
								></path>
							</svg>
							<span class="self-center truncate">{$i18n.t('Update your status')}</span>
						</button>
					</div>
				{/if}
			{/if}

			<hr class="my-1.5 border-gray-800/30 p-0" />
		{/if}

		<button
			type="button"
			class="flex w-full cursor-pointer rounded-xl px-3 py-1.5 transition select-none hover:bg-gray-800"
			role="menuitem"
			onclick={() => run(onSettings)}
		>
			<span class="mr-3 self-center" aria-hidden="true">
				<svg
					class="size-5"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.174.1.34.215.5.346.27.22.637.28.96.16l1.237-.45a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.24-.438.613-.43.992a7.4 7.4 0 0 1 0 .547c-.008.378.137.75.43.99l1.004.828c.424.35.534.95.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.237-.45c-.323-.12-.69-.06-.96.16a6.5 6.5 0 0 1-.5.345c-.332.184-.582.496-.645.87l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.5 6.5 0 0 1-.5-.346c-.27-.22-.637-.28-.96-.16l-1.237.45a1.125 1.125 0 0 1-1.37-.49l-1.296-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.992a7.4 7.4 0 0 1 0-.547c.008-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.236.45c.323.12.69.06.96-.16.16-.13.326-.246.5-.345.332-.184.582-.496.645-.87l.213-1.28Z"
					></path>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
					></path>
				</svg>
			</span>
			<span class="self-center truncate">{$i18n.t('Settings')}</span>
		</button>

		<button
			type="button"
			class="flex w-full cursor-pointer rounded-xl px-3 py-1.5 transition select-none hover:bg-gray-800"
			role="menuitem"
			onclick={() => run(onArchivedChats)}
		>
			<span class="mr-3 self-center" aria-hidden="true">
				<svg
					class="size-5"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="m20.25 7.5-.625 10.632a2.25 2.25 0 0 1-2.247 2.118H6.622a2.25 2.25 0 0 1-2.247-2.118L3.75 7.5m8.25 3v6.75m0 0-3-3m3 3 3-3M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125Z"
					></path>
				</svg>
			</span>
			<span class="self-center truncate">{$i18n.t('Archived Chats')}</span>
		</button>

		{#if userRole === 'admin' && showPlayground}
			<button
				type="button"
				class="flex w-full cursor-pointer rounded-xl px-3 py-1.5 transition select-none hover:bg-gray-800"
				role="menuitem"
				onclick={() => run(onPlayground)}
			>
				<span class="mr-3 self-center" aria-hidden="true">
					<svg
						class="size-5"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5"
						></path>
					</svg>
				</span>
				<span class="self-center truncate">AI 对话探索区</span>
			</button>
		{/if}

		{#if userRole === 'admin' && showAdmin}
			<button
				type="button"
				class="flex w-full cursor-pointer rounded-xl px-3 py-1.5 transition select-none hover:bg-gray-800"
				role="menuitem"
				onclick={() => run(onAdmin)}
			>
				<span class="mr-3 self-center" aria-hidden="true">
					{#if showHelp}
						<UserCircle className="size-5" strokeWidth="1.5" />
					{:else}
						<svg
							class="size-5"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="1.5"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z"
							></path>
						</svg>
					{/if}
				</span>
				<span class="self-center truncate">{$i18n.t('Admin Panel')}</span>
			</button>
		{/if}

		{#if showHelp}
			{#if false}
				{#if userRole === 'admin'}
					<a
						href="https://docs.openwebui.com"
						target="_blank"
						rel="noreferrer"
						class="flex w-full cursor-pointer rounded-xl px-3 py-1.5 transition select-none hover:bg-gray-800"
						role="menuitem"
						onclick={close}
					>
						<span class="mr-3 self-center" aria-hidden="true">
							<svg
								class="size-5"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.5"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z"
								></path>
							</svg>
						</span>
						<span class="self-center truncate">{$i18n.t('Help')}</span>
					</a>

					<a
						href="https://github.com/open-webui/open-webui/releases"
						target="_blank"
						rel="noreferrer"
						class="flex w-full cursor-pointer rounded-xl px-3 py-1.5 transition select-none hover:bg-gray-800"
						role="menuitem"
						onclick={close}
					>
						<span class="mr-3 self-center" aria-hidden="true">
							<svg
								class="size-5"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.5"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M9 6.75V15m6-6v8.25m.503 3.498 4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0L9.503 3.252a1.125 1.125 0 0 0-1.006 0L3.622 5.689C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006l3.869-1.934c.317-.159.69-.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0Z"
								></path>
							</svg>
						</span>
						<span class="self-center truncate">发行版</span>
					</a>
				{/if}
			{/if}

			<button
				type="button"
				class="flex w-full cursor-pointer rounded-xl px-3 py-1.5 transition select-none hover:bg-gray-800"
				role="menuitem"
				onclick={() => run(onShortcuts)}
			>
				<span class="mr-3 self-center" aria-hidden="true">
					<svg
						class="size-5"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
					>
						<path
							d="M3 19V5C3 3.89543 3.89543 3 5 3H19C20.1046 3 21 3.89543 21 5V19C21 20.1046 20.1046 21 19 21H5C3.89543 21 3 20.1046 3 19Z"
						></path>
						<path d="M8 14L12 10L16 14" stroke-linecap="round" stroke-linejoin="round"></path>
					</svg>
				</span>
				<span class="self-center truncate">{$i18n.t('Keyboard Shortcuts')}</span>
			</button>
		{/if}

		{#if false}
			<button
				type="button"
				class="flex w-full cursor-pointer rounded-xl px-3 py-1.5 transition select-none hover:bg-gray-800"
				role="menuitem"
				onclick={() => run(onSignOut)}
			>
				<span class="mr-3 self-center" aria-hidden="true">
					<svg
						class="size-5"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9"
						></path>
					</svg>
				</span>
				<span class="self-center truncate">登出</span>
			</button>
		{/if}

		{#if false}
			<hr class="my-1 border-gray-800/30 p-0" />
			<div class="flex items-center gap-2.5 rounded-xl px-3 py-1 text-xs text-gray-300">
				<span class="relative flex size-2">
					<span class="relative inline-flex size-2 rounded-full bg-green-500"></span>
				</span>
				<span>
					{$i18n.t('Active users online')}:
					<span class="font-semibold text-white">{activeUsers}</span>
				</span>
			</div>
		{/if}
	</div>
{/if}

<UserStatusModal
	open={statusModalOpen}
	initialEmoji={statusEmoji}
	initialMessage={statusMessage}
	onClose={() => {
		statusModalOpen = false;
	}}
	onSave={onStatusSave}
	onToast={(message) => onToast(message)}
/>
