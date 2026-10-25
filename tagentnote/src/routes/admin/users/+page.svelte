<script>
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	onMount(async () => {
		await goto(resolve('/admin/users/overview'));
	});
</script>
