<script lang="ts">
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	onMount(() => {
		goto(resolve('/admin/settings/general'));
	});
</script>
