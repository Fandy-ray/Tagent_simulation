<script lang="ts">
	type ShortcutItem = {
		label: string;
		keys: string[];
		tooltip?: string;
	};

	type Props = {
		open?: boolean;
		onClose?: () => void;
	};

	let { open = false, onClose = () => {} }: Props = $props();

	const isMac =
		typeof navigator !== 'undefined' ? /Mac|iPhone|iPad/i.test(navigator.userAgent) : false;

	const formatKey = (key: string) => {
		switch (key.toLowerCase()) {
			case 'mod':
				return isMac ? '⌘' : 'Ctrl';
			case 'shift':
				return isMac ? '⇧' : 'Shift';
			case 'alt':
				return isMac ? '⌥' : 'Alt';
			case 'escape':
			case 'esc':
				return 'Esc';
			case 'enter':
				return isMac ? '↩' : 'Enter';
			case 'tab':
				return isMac ? '⇥' : 'Tab';
			case 'arrowup':
				return '↑';
			case 'backspace':
			case 'delete':
				return isMac ? '⌫' : 'Delete';
			case 'quote':
				return "'";
			case 'period':
				return '.';
			case 'slash':
				return '/';
			case 'semicolon':
				return ';';
			default:
				return key.length === 1 ? key.toUpperCase() : key;
		}
	};

	const groups: { title: string; items: ShortcutItem[] }[] = [
		{
			title: '对话',
			items: [
				{ label: '新对话', keys: ['mod', 'shift', 'O'] },
				{ label: '创建临时对话', keys: ['mod', 'shift', 'quote'] },
				{ label: '删除对话记录', keys: ['mod', 'shift', 'Delete'] },
				{ label: '打开模型选择器', keys: ['mod', 'shift', 'M'] },
				{ label: '切换为听写模式', keys: ['mod', 'shift', 'L'] }
			]
		},
		{
			title: '全局',
			items: [
				{ label: '搜索', keys: ['mod', 'K'] },
				{ label: '打开设置页面', keys: ['mod', 'period'] },
				{ label: '显示快捷键', keys: ['mod', 'slash'] },
				{ label: '展开或收起侧边栏', keys: ['mod', 'shift', 'S'] },
				{ label: '关闭弹窗', keys: ['Escape'] }
			]
		},
		{
			title: '输入',
			items: [
				{ label: '聚焦对话框', keys: ['shift', 'Escape'] },
				{
					label: '接受自动补全 / 跳转提示词变量',
					keys: ['Tab']
				},
				{
					label: '阻止文件创建',
					keys: ['mod', 'shift', 'V'],
					tooltip: '仅在开启「将大段文本粘贴为文件」时生效'
				},
				{ label: '引用知识库中的文件', keys: ['#'] },
				{ label: '增加自定义提示词', keys: ['/'] },
				{ label: '与模型对话', keys: ['@'] }
			]
		},
		{
			title: '消息',
			items: [
				{
					label: '生成消息对',
					keys: ['mod', 'shift', 'Enter'],
					tooltip: '仅在对话框聚焦时可用'
				},
				{ label: '重新生成回答', keys: ['mod', 'R'] },
				{
					label: '停止生成',
					keys: ['Escape'],
					tooltip: '仅在对话框聚焦且正在生成时可用'
				},
				{
					label: '编辑最后一条消息',
					keys: ['ArrowUp'],
					tooltip: '仅在对话框聚焦且输入为空时可用'
				},
				{ label: '复制最后一个回答', keys: ['mod', 'shift', 'C'] },
				{ label: '复制最后一个代码块', keys: ['mod', 'shift', 'semicolon'] }
			]
		}
	];
</script>

{#if open}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-[80] flex items-center justify-center bg-black/55 px-4"
		onclick={onClose}
	>
		<div
			class="bg-gray-850 max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-gray-800 px-5 py-4 text-white shadow-2xl"
			onclick={(event) => event.stopPropagation()}
			tabindex="-1"
			role="dialog"
			aria-modal="true"
			aria-label="键盘快捷键"
		>
			<div class="mb-2 flex items-center justify-between pb-2 text-gray-300">
				<h2 class="text-lg font-medium text-white">键盘快捷键</h2>
				<button
					type="button"
					class="rounded-lg p-1 text-gray-400 transition hover:bg-gray-800 hover:text-white"
					onclick={onClose}
					aria-label="关闭"
				>
					<svg
						class="size-5"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.8"
					>
						<path stroke-linecap="round" d="M6 6l12 12M18 6L6 18"></path>
					</svg>
				</button>
			</div>

			{#each groups as group, groupIndex (group.title)}
				{#if groupIndex > 0}
					<div class="py-3">
						<div class="w-full border-t border-gray-800"></div>
					</div>
				{/if}

				<div class="mb-2 text-base text-gray-300">{group.title}</div>
				<div class="grid grid-cols-1 gap-2 gap-x-4 sm:grid-cols-2">
					{#each group.items as item (item.label)}
						<div class="col-span-1 flex w-full items-start justify-between gap-3">
							<div class="text-sm text-gray-200" title={item.tooltip}>
								{item.label}{#if item.tooltip}<span class="text-xs">&nbsp;*</span>{/if}
							</div>
							<div class="flex h-full shrink-0 items-start justify-end space-x-1 text-xs">
								{#each item.keys as key (key)}
									<kbd
										class="flex h-fit items-start justify-center rounded-sm border border-white/10 px-1 py-0.5 text-gray-300 capitalize"
									>
										{formatKey(key)}
									</kbd>
								{/each}
							</div>
						</div>
					{/each}
				</div>
			{/each}
		</div>
	</div>
{/if}
