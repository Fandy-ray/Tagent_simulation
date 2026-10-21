<script lang="ts">
	import { fade } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';

	type Props = {
		show?: boolean;
		title?: string;
		message?: string;
		cancelLabel?: string;
		confirmLabel?: string;
		onConfirm?: () => void | Promise<void>;
		onCancel?: () => void;
		children?: import('svelte').Snippet;
	};

	let {
		show = $bindable(false),
		title = '确认操作',
		message = '此操作无法撤销，是否继续？',
		cancelLabel = '取消',
		confirmLabel = '确认',
		onConfirm = () => {},
		onCancel = () => {},
		children
	}: Props = $props();

	let mounted = $state(false);

	function scaleFly(_node: Element, { duration = 120 }: { duration?: number } = {}) {
		return {
			duration,
			easing: cubicOut,
			css: (t: number) => `
				transform: translateY(${(1 - t) * 6}px) scale(${0.985 + 0.015 * t});
				opacity: ${t};
			`
		};
	}

	$effect(() => {
		mounted = true;
	});

	$effect(() => {
		if (mounted && show) {
			const prev = document.body.style.overflow;
			document.body.style.overflow = 'hidden';
			const onKey = (event: KeyboardEvent) => {
				if (event.key === 'Escape') {
					event.preventDefault();
					show = false;
					onCancel();
				}
				if (event.key === 'Enter') {
					event.preventDefault();
					void handleConfirm();
				}
			};
			window.addEventListener('keydown', onKey);
			return () => {
				document.body.style.overflow = prev;
				window.removeEventListener('keydown', onKey);
			};
		}
	});

	const handleConfirm = async () => {
		show = false;
		await onConfirm();
	};
</script>

{#if show}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 right-0 left-0 bottom-0 z-[99999999] flex h-screen max-h-[100dvh] w-full justify-center overflow-hidden overscroll-contain bg-black/60"
		transition:fade={{ duration: 10 }}
		onmousedown={() => {
			show = false;
			onCancel();
		}}
	>
		<div
			class="modal-content m-auto mx-2 w-[32rem] max-w-full rounded-4xl border border-white/10 bg-gray-950/95 shadow-3xl backdrop-blur-sm"
			in:scaleFly
			onmousedown={(e) => e.stopPropagation()}
		>
			<div class="flex flex-col px-7 py-6">
				<div class="mb-2.5 text-lg font-medium text-gray-200">{title}</div>
				{#if children}
					<div class="flex-1">{@render children()}</div>
				{:else}
					<div class="flex-1 text-sm text-gray-400">{message}</div>
				{/if}
				<div class="mt-6 flex justify-between gap-1.5">
					<button
						type="button"
						class="w-full rounded-3xl bg-gray-850 py-2 text-sm font-medium text-white transition hover:bg-gray-800"
						onclick={() => {
							show = false;
							onCancel();
						}}
					>
						{cancelLabel}
					</button>
					<button
						type="button"
						class="w-full rounded-3xl bg-gray-100 py-2 text-sm font-medium text-gray-800 transition hover:bg-white"
						onclick={() => {
							void handleConfirm();
						}}
					>
						{confirmLabel}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}
