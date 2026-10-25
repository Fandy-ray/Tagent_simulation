<script lang="ts">
	type Props = {
		state?: string;
		indeterminate?: boolean;
		disabled?: boolean;
		disabledClassName?: string;
		/** 兼容 open-webui `on:change`（接收带 detail 的类事件对象） */
		onchange?: (e: { detail: string }) => void;
		onChange?: (state: string) => void;
	};

	let {
		state = $bindable('unchecked'),
		indeterminate = false,
		disabled = false,
		disabledClassName = 'opacity-50 cursor-not-allowed',
		onchange,
		onChange
	}: Props = $props();

	const emit = (next: string) => {
		state = next;
		onchange?.({ detail: next });
		onChange?.(next);
	};
</script>

<button
	class="relative inline-block h-3.5 w-3.5 rounded-sm text-white outline outline-[1.5px] -outline-offset-1 outline-gray-200 transition-all dark:outline-gray-600 {state !==
	'unchecked'
		? 'bg-black outline-black '
		: 'hover:bg-gray-50 hover:outline-gray-500 dark:hover:bg-gray-800'} {disabled
		? disabledClassName
		: ''}"
	onclick={() => {
		if (disabled) return;
		if (state === 'unchecked') {
			emit('checked');
		} else if (state === 'checked') {
			if (!indeterminate) emit('unchecked');
			else emit('unchecked');
		} else if (indeterminate) {
			emit('checked');
		}
	}}
	type="button"
	{disabled}
>
	<div class="absolute top-0 left-0 flex w-full justify-center">
		{#if state === 'checked'}
			<svg
				class="h-3.5 w-3.5"
				aria-hidden="true"
				xmlns="http://www.w3.org/2000/svg"
				fill="none"
				viewBox="0 0 24 24"
			>
				<path
					stroke="currentColor"
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="3"
					d="m5 12 4.7 4.5 9.3-9"
				/>
			</svg>
		{:else if indeterminate}
			<svg
				class="h-3.5 w-3 text-gray-800 dark:text-white"
				aria-hidden="true"
				xmlns="http://www.w3.org/2000/svg"
				fill="none"
				viewBox="0 0 24 24"
			>
				<path
					stroke="currentColor"
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="3"
					d="M5 12h14"
				/>
			</svg>
		{/if}
	</div>
</button>
