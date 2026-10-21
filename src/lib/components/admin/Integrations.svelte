<script lang="ts">
	import AddToolServerModal from '$lib/components/chat/Settings/Tools/AddToolServerModal.svelte';
	import ToolConnection from '$lib/components/chat/Settings/Tools/Connection.svelte';
	import AddTerminalServerModal from '$lib/components/chat/Settings/Integrations/Terminals/AddTerminalServerModal.svelte';
	import TerminalConnection from '$lib/components/chat/Settings/Integrations/Terminals/Connection.svelte';

	const TOOL_KEY = 'admin-mock-tool-servers';
	const TERMINAL_KEY = 'admin-mock-terminal-connections';

	type ToolServer = { id: string; type: string; url: string; key: string; config: Record<string, unknown> };
	type TerminalServer = { id: string; name: string; url: string; key: string; auth_type: string; path: string; enabled: boolean };

	const load = <T,>(key: string, fallback: T): T => {
		if (typeof localStorage === 'undefined') return fallback;
		try {
			const raw = localStorage.getItem(key);
			return raw ? (JSON.parse(raw) as T) : fallback;
		} catch {
			return fallback;
		}
	};

	let toolServers = $state<ToolServer[]>(load<ToolServer[]>(TOOL_KEY, []));
	let terminalConnections = $state<TerminalServer[]>(load<TerminalServer[]>(TERMINAL_KEY, []));
	let showToolModal = $state(false);
	let showTerminalModal = $state(false);
	let editingTerminalIdx = $state<number | null>(null);
	let notice = $state('');

	function inform(message: string) {
		notice = message;
		setTimeout(() => notice = '', 2300);
	}

	function persist() {
		try {
			localStorage.setItem(TOOL_KEY, JSON.stringify(toolServers.map(({ id, type, url, key, config }) => ({ id, type, url, key, config }))));
			localStorage.setItem(TERMINAL_KEY, JSON.stringify(terminalConnections));
		} catch {
			inform('无法保存到浏览器本地存储');
		}
	}

	function addToolServer(server: ToolServer) {
		toolServers = [...toolServers, { ...server, id: server.id || crypto.randomUUID() }];
		persist();
	}

	function updateToolServer(index: number, updated: ToolServer) {
		toolServers = toolServers.map((server, idx) => idx === index ? { ...server, ...updated } : server);
		persist();
	}

	function removeToolServer(index: number) {
		toolServers = toolServers.filter((_, idx) => idx !== index);
		persist();
	}

	function submitTerminal(server: TerminalServer) {
		if (editingTerminalIdx !== null) {
			terminalConnections = terminalConnections.map((connection, idx) => idx === editingTerminalIdx ? { ...connection, ...server, id: server.id || connection.id } : connection);
			editingTerminalIdx = null;
		} else {
			terminalConnections = [...terminalConnections, { ...server, id: server.id || crypto.randomUUID() }];
		}
		persist();
	}

	function toggleTerminal(index: number) {
		terminalConnections = terminalConnections.map((connection, idx) => idx === index ? { ...connection, enabled: !connection.enabled } : connection);
		persist();
	}

	function removeTerminal(index: number) {
		terminalConnections = terminalConnections.filter((_, idx) => idx !== index);
		persist();
	}

	function save() {
		persist();
		inform('集成连接已保存（本地 mock）');
	}
</script>

<AddToolServerModal
	bind:show={showToolModal}
	onSubmit={(server) => {
		addToolServer(server);
		inform('工具服务器连接已添加（本地 mock）');
	}}
/>

<AddTerminalServerModal
	bind:show={showTerminalModal}
	edit={editingTerminalIdx !== null}
	connection={editingTerminalIdx !== null ? terminalConnections[editingTerminalIdx] : null}
	onSubmit={(server) => {
		submitTerminal(server);
		inform(editingTerminalIdx !== null ? '终端连接已更新（本地 mock）' : '终端连接已添加（本地 mock）');
	}}
	onDelete={() => {
		if (editingTerminalIdx !== null) removeTerminal(editingTerminalIdx);
		editingTerminalIdx = null;
	}}
/>

<form class="flex min-h-full flex-col justify-between text-sm" onsubmit={(event) => { event.preventDefault(); save(); }}>
	<div class="min-h-0 flex-1 overflow-y-auto pr-0.5">
		<div class="mb-3">
			<div class="mb-2.5 mt-0.5 text-base font-medium">常规</div>
			<hr class="my-2 border-gray-100/30 dark:border-gray-850/30" />

			<div class="mb-2.5 flex w-full flex-col justify-between">
				<div class="mb-0.5 flex items-center justify-between">
					<div class="font-medium">管理工具服务器</div>
					<button type="button" class="rounded-lg p-1 text-gray-500 transition hover:bg-gray-100 dark:hover:bg-gray-850" aria-label="添加工具服务器连接" title="添加连接" onclick={() => showToolModal = true}>
						<svg viewBox="0 0 20 20" fill="currentColor" class="size-4" aria-hidden="true"><path d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z" /></svg>
					</button>
				</div>

				<div class="flex flex-col gap-1">
					{#each toolServers as server, index (server.id)}
						<ToolConnection
							bind:connection={toolServers[index]}
							onSubmit={(updated) => updateToolServer(index, updated)}
							onDelete={() => removeToolServer(index)}
						/>
					{/each}
				</div>

				{#if toolServers.length === 0}
					<div class="text-xs text-gray-400 dark:text-gray-500">尚未配置任何工具服务器连接。</div>
				{/if}

				<div class="my-1.5 text-xs text-gray-500">连接您自己的 OpenAPI 兼容外部工具服务器。</div>
			</div>

			<hr class="my-4 border-gray-100/30 dark:border-gray-850/30" />

			<div class="mb-2.5 flex w-full flex-col">
				<div class="mb-1 flex items-center justify-between">
					<div class="flex items-center gap-2">
						<div class="font-medium">打开终端</div>
						<span class="rounded-full bg-gray-100 px-1.5 py-0.5 text-[0.65rem] font-medium uppercase text-gray-500 dark:bg-gray-800 dark:text-gray-400">实验性</span>
					</div>
					<button type="button" class="rounded-lg p-1 text-gray-500 transition hover:bg-gray-100 dark:hover:bg-gray-850" aria-label="添加终端连接" title="添加连接" onclick={() => { editingTerminalIdx = null; showTerminalModal = true; }}>
						<svg viewBox="0 0 20 20" fill="currentColor" class="size-4" aria-hidden="true"><path d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z" /></svg>
					</button>
				</div>

				<div class="flex flex-col gap-1.5">
					{#each terminalConnections as connection, index (connection.id)}
						<TerminalConnection
							bind:connection={terminalConnections[index]}
							onSubmit={(updated) => { terminalConnections = terminalConnections.map((item, idx) => idx === index ? { ...item, ...updated } : item); persist(); }}
							onDelete={() => removeTerminal(index)}
							onEnable={() => toggleTerminal(index)}
							onDisable={() => toggleTerminal(index)}
						/>
					{/each}
				</div>

				{#if terminalConnections.length === 0}
					<div class="text-xs text-gray-400 dark:text-gray-500">尚未配置任何终端连接。</div>
				{/if}

				<div class="mt-1.5">
					<div class="text-xs text-gray-500">连接到 Open Terminal 实例。所有用户都将通过这些服务器获得文件浏览和终端工具。</div>
					<div class="mt-1 text-xs text-gray-600 dark:text-gray-300"><a class="underline" href="https://github.com/open-webui/open-terminal" target="_blank" rel="noreferrer">了解 Open Terminal ↗</a></div>
				</div>
			</div>
		</div>
	</div>

	<div class="flex justify-end pt-3 text-sm font-medium">
		<button class="rounded-full bg-black px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-gray-900 dark:bg-white dark:text-black dark:hover:bg-gray-100" type="submit">保存</button>
	</div>
</form>

{#if notice}<div class="fixed bottom-5 right-5 z-[100] max-w-sm rounded-xl bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg dark:bg-white dark:text-gray-900" role="status">{notice}</div>{/if}
