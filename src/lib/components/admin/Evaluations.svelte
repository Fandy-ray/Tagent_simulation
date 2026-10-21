<script lang="ts">
	import { page } from '$app/stores';
	import Leaderboard from './evaluations/Leaderboard.svelte';
	import Feedbacks from './evaluations/Feedbacks.svelte';

	let selectedTab = $derived($page.url.pathname.endsWith('/feedback') ? 'feedback' : 'leaderboard');
</script>

<div class="flex h-full w-full flex-col pb-2 lg:flex-row lg:gap-2">
	<nav class="mx-2 flex max-w-full flex-row gap-3 overflow-x-auto text-left text-sm font-medium scrollbar-none lg:mx-0 lg:w-28 lg:flex-none lg:flex-col lg:gap-1 lg:pt-1" aria-label="评估管理">
		<a href="/admin/evaluations/leaderboard" aria-current={selectedTab === 'leaderboard' ? 'page' : undefined} class="flex min-w-fit select-none items-center gap-2 rounded-lg px-2 py-2 transition {selectedTab === 'leaderboard' ? 'text-gray-900 dark:text-white' : 'text-gray-500 hover:text-gray-800 dark:text-gray-500 dark:hover:text-gray-200'}">
			<svg viewBox="0 0 16 16" fill="currentColor" class="size-4 shrink-0" aria-hidden="true"><path fill-rule="evenodd" d="M4 2a1.5 1.5 0 0 0-1.5 1.5v9A1.5 1.5 0 0 0 4 14h8a1.5 1.5 0 0 0 1.5-1.5V6.62a1.5 1.5 0 0 0-.44-1.06L9.94 2.44A1.5 1.5 0 0 0 8.88 2H4Zm6 5.75a.75.75 0 0 1 1.5 0v3.5a.75.75 0 0 1-1.5 0v-3.5Zm-2.75 1.5a.75.75 0 0 1 1.5 0v2a.75.75 0 0 1-1.5 0v-2Zm-2 .75a.75.75 0 0 0-.75.75v.5a.75.75 0 0 0 1.5 0V10Z" clip-rule="evenodd" /></svg>
			<span>排行榜</span>
		</a>
		<a href="/admin/evaluations/feedback" aria-current={selectedTab === 'feedback' ? 'page' : undefined} class="flex min-w-fit select-none items-center gap-2 rounded-lg px-2 py-2 transition {selectedTab === 'feedback' ? 'text-gray-900 dark:text-white' : 'text-gray-500 hover:text-gray-800 dark:text-gray-500 dark:hover:text-gray-200'}">
			<svg viewBox="0 0 16 16" fill="currentColor" class="size-4 shrink-0" aria-hidden="true"><path fill-rule="evenodd" d="M5.25 2A2.25 2.25 0 0 0 3 4.25v9a.75.75 0 0 0 1.18.61l1.7-1.2 1.69 1.2a.75.75 0 0 0 .86 0l1.7-1.2 1.69 1.2a.75.75 0 0 0 1.18-.61v-9A2.25 2.25 0 0 0 10.75 2h-5.5Zm3.03 3.28a.75.75 0 0 0-1.06-1.06L4.97 6.47a.75.75 0 0 0 0 1.06l2.25 2.25a.75.75 0 0 0 1.06-1.06l-.97-.97h1.31c.76 0 1.38.62 1.38 1.38a.75.75 0 0 0 1.5 0 2.88 2.88 0 0 0-2.88-2.88H7.31l.97-.97Z" clip-rule="evenodd" /></svg>
			<span>反馈</span>
		</a>
	</nav>
	<div class="mt-1 min-w-0 flex-1 overflow-y-auto px-2 lg:mt-0 lg:px-2">
		{#if selectedTab === 'feedback'}<Feedbacks />{:else}<Leaderboard />{/if}
	</div>
</div>
