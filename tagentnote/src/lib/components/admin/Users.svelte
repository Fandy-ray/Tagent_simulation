<script lang="ts">
	import { resolve } from '$app/paths';
	import { getI18nContext } from '$lib/i18n';
	import { page } from '$app/stores';
	import UserList from './users/UserList.svelte';
	import Groups from './users/Groups.svelte';

	const i18n = getI18nContext();
	let selectedTab = $derived($page.url.pathname.endsWith('/groups') ? 'groups' : 'overview');
</script>

<div class="flex h-full w-full flex-col pb-2 lg:flex-row lg:gap-2">
	<nav
		class="mx-2 flex max-w-full scrollbar-none flex-row gap-3 overflow-x-auto text-left text-sm font-medium lg:mx-0 lg:w-28 lg:flex-none lg:flex-col lg:gap-1 lg:pt-1"
		aria-label="用户管理"
	>
		<a
			href={resolve('/admin/users/overview')}
			aria-current={selectedTab === 'overview' ? 'page' : undefined}
			class="flex min-w-fit items-center gap-2 rounded-lg px-2 py-2 transition select-none {selectedTab ===
			'overview'
				? 'text-gray-900 dark:text-white'
				: 'text-gray-500 hover:text-gray-800 dark:text-gray-500 dark:hover:text-gray-200'}"
		>
			<svg viewBox="0 0 24 24" fill="currentColor" class="size-4 shrink-0" aria-hidden="true"
				><path
					d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 19a6 6 0 0 1 12 0v1H4v-1ZM17.5 11a3 3 0 1 0-1.5-5.598 5.5 5.5 0 0 1 0 8.196A4.98 4.98 0 0 1 19 18v1h-2v-1a5 5 0 0 0-1.4-3.46A5.48 5.48 0 0 0 17.5 11Z"
				/></svg
			>
			<span>{$i18n.t('Overview')}</span>
		</a>
		<a
			href={resolve('/admin/users/groups')}
			aria-current={selectedTab === 'groups' ? 'page' : undefined}
			class="flex min-w-fit items-center gap-2 rounded-lg px-2 py-2 transition select-none {selectedTab ===
			'groups'
				? 'text-gray-900 dark:text-white'
				: 'text-gray-500 hover:text-gray-800 dark:text-gray-500 dark:hover:text-gray-200'}"
		>
			<svg viewBox="0 0 24 24" fill="currentColor" class="size-4 shrink-0" aria-hidden="true"
				><path
					d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 20a5 5 0 0 1 10 0v1H5v-1ZM18 11a3 3 0 1 0-1.5-5.598 5.5 5.5 0 0 1 0 8.196A5 5 0 0 1 20 18v1h-2v-1a5 5 0 0 0-1.4-3.46A5.48 5.48 0 0 0 18 11ZM4.5 6a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM2 18a4.5 4.5 0 0 1 2.5-4.03 6.9 6.9 0 0 0-1.2 3.53V19H2v-1Z"
				/></svg
			>
			<span>{$i18n.t('Groups')}</span>
		</a>
	</nav>
	<div class="mt-1 min-w-0 flex-1 overflow-y-auto px-2 lg:mt-0 lg:px-2">
		{#if selectedTab === 'groups'}<Groups />{:else}<UserList />{/if}
	</div>
</div>
