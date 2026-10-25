<script lang="ts">
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	onMount(() => {
		goto(resolve('/admin/users/overview'));
	});
</script>

<svelte:head>
	<title>管理员面板 | TAgent</title>
</svelte:head>
