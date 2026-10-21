<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	onMount(() => {
		goto('/admin/users/overview');
	});
</script>

<svelte:head>
	<title>管理员面板 | TAgent</title>
</svelte:head>
