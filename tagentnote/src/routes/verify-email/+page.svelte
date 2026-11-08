<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { resolve } from '$app/paths';
	import { verifyEmail } from '$lib/apis/auth';
	let verificationStatus = $state<'working' | 'done' | 'error'>('working');
	let message = $state('');
	onMount(async () => {
		const token = $page.url.searchParams.get('token');
		if (!token) {
			verificationStatus = 'error';
			message = '验证链接不完整。';
			return;
		}
		try {
			await verifyEmail(token);
			verificationStatus = 'done';
		} catch (cause) {
			verificationStatus = 'error';
			message = cause instanceof Error ? cause.message : '验证失败。';
		}
	});
</script>

<svelte:head
	><title>验证邮箱 | TAgent</title><meta name="referrer" content="no-referrer" /></svelte:head
>
<main class="flex min-h-screen items-center justify-center bg-slate-950 p-5 text-white">
	<section class="w-full max-w-md rounded-2xl border border-white/15 bg-slate-900 p-8 text-center">
		<h1 class="text-2xl font-semibold">邮箱验证</h1>
		<p role="status" class="mt-5 text-slate-300">
			{verificationStatus === 'working'
				? '正在验证…'
				: verificationStatus === 'done'
					? '邮箱已验证，可以登录。'
					: message}
		</p>
		<a href={resolve('/login')} class="mt-6 inline-block rounded-lg bg-blue-500 px-4 py-2"
			>前往登录</a
		>
	</section>
</main>
