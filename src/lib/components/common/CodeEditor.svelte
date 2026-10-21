<script lang="ts">
	import { untrack } from 'svelte';
	type Props = {
		value?: string;
		lang?: string;
		boilerplate?: string;
		readOnly?: boolean;
		onChange?: (value: string) => void;
		onSave?: () => void;
	};

	let {
		value = $bindable(''),
		lang = 'python',
		boilerplate = '',
		readOnly = false,
		onChange = () => {},
		onSave = () => {}
	}: Props = $props();

	const indent = '    ';

	let text = $state(untrack(() => value || boilerplate));
	let textareaEl = $state<HTMLTextAreaElement | null>(null);
	let gutterEl = $state<HTMLDivElement | null>(null);
	let cursor = $state({ line: 1, column: 1 });

	const lines = $derived(text.split('\n'));
	const lineNumbers = $derived(lines.map((_, index) => index + 1));

	// 参考实现：新建函数时 value 为空则载入模板，并把模板同步给父组件
	let initialized = false;
	$effect(() => {
		if (initialized) return;
		initialized = true;
		if (!value && text) {
			value = text;
			onChange(text);
		}
	});

	// 外部重置（例如切换到另一个函数）时同步内容
	$effect(() => {
		if (value !== text) text = value;
	});

	const syncScroll = () => {
		if (gutterEl && textareaEl) gutterEl.scrollTop = textareaEl.scrollTop;
	};

	const updateCursor = () => {
		const el = textareaEl;
		if (!el) return;
		const before = el.value.slice(0, el.selectionStart ?? 0);
		const rows = before.split('\n');
		cursor = { line: rows.length, column: (rows[rows.length - 1]?.length ?? 0) + 1 };
	};

	const handleInput = (event: Event) => {
		text = (event.currentTarget as HTMLTextAreaElement).value;
		value = text;
		updateCursor();
		onChange(text);
		syncScroll();
	};

	const applyEdit = (next: string, selectionStart: number, selectionEnd = selectionStart) => {
		text = next;
		value = next;
		onChange(next);
		requestAnimationFrame(() => {
			const el = textareaEl;
			if (!el) return;
			el.selectionStart = selectionStart;
			el.selectionEnd = selectionEnd;
			updateCursor();
		});
	};

	const handleKeydown = (event: KeyboardEvent) => {
		const el = textareaEl;
		if (!el || readOnly) return;

		if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
			event.preventDefault();
			onSave();
			return;
		}

		const start = el.selectionStart ?? 0;
		const end = el.selectionEnd ?? 0;

		if (event.key === 'Tab') {
			event.preventDefault();
			const hasSelection = start !== end;

			if (!hasSelection && !event.shiftKey) {
				applyEdit(`${text.slice(0, start)}${indent}${text.slice(end)}`, start + indent.length);
				return;
			}

			// 多行（或无选区）整块缩进 / 反缩进
			const lineStart = text.lastIndexOf('\n', start - 1) + 1;
			const lineEnd = end > start && text[end - 1] === '\n' ? end - 1 : end;
			const blockEnd = text.indexOf('\n', Math.max(lineEnd, start)) === -1 ? text.length : text.indexOf('\n', Math.max(lineEnd, start));
			const block = text.slice(lineStart, blockEnd);
			const updated = block
				.split('\n')
				.map((row) => (event.shiftKey ? row.replace(new RegExp(`^( {1,${indent.length}}|\t)`), '') : `${indent}${row}`))
				.join('\n');
			const next = `${text.slice(0, lineStart)}${updated}${text.slice(blockEnd)}`;
			const delta = updated.length - block.length;
			applyEdit(next, Math.max(lineStart, start + (event.shiftKey ? Math.min(0, delta) : indent.length)), Math.max(lineStart, end + delta));
			return;
		}

		if (event.key === 'Enter' && start === end) {
			const lineStart = text.lastIndexOf('\n', start - 1) + 1;
			const currentLine = text.slice(lineStart, start);
			const leading = currentLine.match(/^[ \t]*/)?.[0] ?? '';
			const extra = currentLine.trimEnd().endsWith(':') ? indent : '';
			if (leading || extra) {
				event.preventDefault();
				const insert = `\n${leading}${extra}`;
				applyEdit(`${text.slice(0, start)}${insert}${text.slice(end)}`, start + insert.length);
			}
		}
	};

	const focus = () => textareaEl?.focus();
</script>

<div
	class="flex h-full min-h-0 w-full flex-col overflow-hidden rounded-lg border border-gray-800 bg-[#282c34] font-mono text-[13px] leading-6 text-[#abb2bf]"
>
	<div class="flex min-h-0 flex-1">
		<div
			bind:this={gutterEl}
			class="shrink-0 select-none overflow-hidden border-r border-white/5 bg-[#21252b] py-3 pr-2.5 pl-3 text-right text-[#4b5263]"
			aria-hidden="true"
		>
			{#each lineNumbers as number (number)}
				<div>{number}</div>
			{/each}
		</div>

		<textarea
			bind:this={textareaEl}
			bind:value={text}
			class="h-full min-h-0 w-full flex-1 resize-none overflow-auto bg-transparent px-3 py-3 outline-none placeholder:text-[#5c6370] disabled:opacity-70"
			spellcheck="false"
			autocapitalize="off"
			autocomplete="off"
			readonly={readOnly}
			placeholder={`${lang === 'python' ? '#' : '//'} Enter your code here...`}
			oninput={handleInput}
			onkeydown={handleKeydown}
			onkeyup={updateCursor}
			onclick={updateCursor}
			onscroll={syncScroll}
			aria-label="代码编辑器"
		></textarea>
	</div>

	<div
		class="flex shrink-0 items-center justify-between border-t border-white/5 bg-[#21252b] px-3 py-1 text-[11px] text-[#5c6370]"
	>
		<span>{lang}</span>
		<span>行 {cursor.line}，列 {cursor.column} · Ctrl/⌘ + S 保存</span>
	</div>
</div>
