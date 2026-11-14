<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';

	onMount(() => {
		void goto(resolve('/space-exploration'), { replaceState: true });
	});
</script>

<svelte:head>
	<title>系统建模与仿真智能教学平台</title>
</svelte:head>

<div class="flex min-h-screen items-center justify-center bg-gray-950 text-gray-300">
	正在进入平台……
</div>
